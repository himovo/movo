from __future__ import annotations

import asyncio
from copy import deepcopy
from types import SimpleNamespace

from app.enterprise_capabilities.evidence.execution_scope import ExecutionEvidenceRepository
from app.enterprise_capabilities.research.evidence import (
    build_research_evidence_bundle,
    public_evidence_bundle,
)


def test_single_search_reuses_canonical_research_bundle_and_keeps_url() -> None:
    results = [{
        "provider": "test",
        "query": "DeepSeek Harness",
        "title": "Official page",
        "url": "https://example.test/harness",
        "snippet": "Harness is an agent runtime.",
        "score": 0.9,
    }]
    bundle = build_research_evidence_bundle(
        tool_name="external_search",
        query="DeepSeek Harness",
        results=results,
        raw_result={"results": results},
    )
    assert bundle["tools_used"] == ["external_search"]
    assert bundle["results"][0]["source_url"] == "https://example.test/harness"
    assert "Harness is an agent runtime." in bundle["confirmed_facts"]
    assert public_evidence_bundle(bundle)["sources"][0]["source_url"] == "https://example.test/harness"


def test_progressive_research_preserves_sufficiency_boundary() -> None:
    bundle = build_research_evidence_bundle(
        tool_name="progressive_research",
        query="compare runtimes",
        results=[{
            "tool": "progressive_research", "title": "Source A",
            "source_url": "https://example.test/a", "content": "Only one dimension was verified.",
        }],
        raw_result={"summary": "insufficient"},
        evidence_sufficient=False,
        budget_exhausted=True,
        stop_reason="budget_exhausted",
    )
    assert bundle["evidence_sufficient"] is False
    assert bundle["budget_exhausted"] is True
    assert bundle["stop_reason"] == "budget_exhausted"
    assert bundle["open_questions"]


def test_execution_evidence_scope_is_durable_and_tenant_isolated(monkeypatch) -> None:
    from app.enterprise_capabilities.evidence import execution_scope as module

    class Collection:
        def __init__(self):
            self.row = {
                "tenant_id": "tenant-a", "user_id": "user-a", "kernel_session_id": "session-a",
                "active_turn": {"message_id": "message-a", "status": "running", "evidence_bundles": []},
            }

        async def update_one(self, query, update):
            if not self._matches(query):
                return SimpleNamespace(matched_count=0)
            payload = update["$push"]["active_turn.evidence_bundles"]
            self.row["active_turn"]["evidence_bundles"].extend(deepcopy(payload["$each"]))
            self.row["active_turn"]["evidence_bundles"] = self.row["active_turn"]["evidence_bundles"][payload["$slice"]:]
            return SimpleNamespace(matched_count=1)

        async def find_one(self, query, _projection):
            return deepcopy(self.row) if self._matches(query) else None

        def _matches(self, query):
            active = self.row["active_turn"]
            actual = {
                **self.row,
                "active_turn.message_id": active["message_id"],
                "active_turn.status": active["status"],
            }
            return all(actual.get(key) == value for key, value in query.items())

    collection = Collection()
    monkeypatch.setattr(module, "get_db", lambda: {"agent_kernel_bindings": collection})

    async def run():
        repository = ExecutionEvidenceRepository()
        await repository.append(
            tenant_id="tenant-a", user_id="user-a", kernel_session_id="session-a",
            message_id="message-a", action_id="search-a",
            bundle={"results": [{
                "title": "Source", "source_url": "https://example.test/a", "content": "Grounded fact."
            }]},
        )
        owned = await repository.load(
            tenant_id="tenant-a", user_id="user-a", kernel_session_id="session-a", message_id="message-a",
        )
        assert owned["results"][0]["source_url"] == "https://example.test/a"
        foreign = await repository.load(
            tenant_id="tenant-b", user_id="user-a", kernel_session_id="session-a", message_id="message-a",
        )
        assert foreign == {}

    asyncio.run(run())
