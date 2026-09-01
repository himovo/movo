import asyncio

from app.services.conversation_evidence_service import (
    ConversationEvidenceSelection,
    ConversationEvidenceService,
)


def test_exclude_current_request_removes_only_latest_matching_user_turn() -> None:
    rows = [
        {"seq": 1, "role": "user", "content": "Remember Atlas"},
        {"seq": 2, "role": "assistant", "content": "Atlas remembered"},
        {"seq": 3, "role": "user", "content": "Publish using Atlas"},
    ]

    prior = ConversationEvidenceService._exclude_current_request(
        rows,
        current_request="Publish   using Atlas",
    )

    assert [row["seq"] for row in prior] == [1, 2]


def test_collect_retries_unresolved_selection_and_uses_prior_rows_only() -> None:
    class RetryService(ConversationEvidenceService):
        def __init__(self) -> None:
            self.calls = []

        async def _load_rows(self, **_kwargs):
            return [
                {"seq": 1, "role": "user", "content": "Atlas is an enterprise assistant."},
                {"seq": 2, "role": "assistant", "content": "Atlas product summary."},
                {"seq": 3, "role": "user", "content": "Publish using Atlas"},
            ]

        async def _select_rows(self, *, rows, current_request, evidence_requirement="", attempt=1):
            self.calls.append(
                {
                    "seqs": [row["seq"] for row in rows],
                    "requirement": evidence_requirement,
                    "attempt": attempt,
                }
            )
            if attempt == 1:
                return ConversationEvidenceSelection(
                    selected_seqs=[],
                    rationale="uncertain",
                    sufficient=False,
                )
            return ConversationEvidenceSelection(
                selected_seqs=[1, 2],
                canonical_subject="Atlas",
                rationale="Relevant product context exists.",
                sufficient=True,
            )

    async def run_case():
        service = RetryService()
        artifacts = await service.collect(
            session_id="unused",
            user_id="user",
            main_id="main",
            current_request="Publish using Atlas",
            evidence_requirement="Use the prior Atlas product facts",
        )
        return service, artifacts

    service, artifacts = asyncio.run(run_case())

    assert service.calls == [
        {"seqs": [1, 2], "requirement": "Use the prior Atlas product facts", "attempt": 1},
        {"seqs": [1, 2], "requirement": "Use the prior Atlas product facts", "attempt": 2},
    ]
    assert artifacts["selected_content"]["title"] == "Atlas"


def test_build_artifacts_prefers_persisted_evidence() -> None:
    artifacts = ConversationEvidenceService._build_artifacts(
        selected=[
            {
                "seq": 2,
                "role": "assistant",
                "message_id": "msg_research",
                "content": "MOVO is the product described by movo.example.",
                "evidence_bundles": [
                    {
                        "confirmed_facts": ["MOVO provides enterprise AI assistant products."],
                        "sources": [
                            {
                                "title": "MOVO official site",
                                "snippet": "Enterprise AI assistant product information.",
                                "source_type": "web",
                                "source_url": "https://movo.example/",
                            }
                        ],
                    }
                ],
            }
        ],
        current_request="Turn the prior research into a social post",
        canonical_subject="MOVO from movo.example",
    )

    bundle = artifacts["evidence_bundle"]
    assert bundle["confirmed_facts"]
    assert bundle["results"][0]["source_url"] == "https://movo.example/"
    assert artifacts["selected_content"]["title"] == "MOVO from movo.example"


def test_build_artifacts_marks_assistant_only_fallback_as_derived() -> None:
    artifacts = ConversationEvidenceService._build_artifacts(
        selected=[
            {
                "seq": 2,
                "role": "assistant",
                "message_id": "msg_summary",
                "content": "A prior assistant summary with enough factual detail for rewriting.",
                "evidence_bundles": [],
            }
        ],
        current_request="Rewrite the prior answer",
        canonical_subject="Prior summary",
    )

    result = artifacts["evidence_bundle"]["results"][0]
    assert result["meta"]["provenance"] == "derived_assistant_summary"


def test_build_artifacts_keeps_historical_user_statements() -> None:
    artifacts = ConversationEvidenceService._build_artifacts(
        selected=[
            {
                "seq": 1,
                "role": "user",
                "message_id": "seq:1",
                "content": "Our product is named Atlas and launches in September.",
                "evidence_bundles": [],
            }
        ],
        current_request="Write the launch announcement",
        canonical_subject="Atlas",
    )

    result = artifacts["evidence_bundle"]["results"][0]
    assert result["meta"]["provenance"] == "historical_user_statement"
