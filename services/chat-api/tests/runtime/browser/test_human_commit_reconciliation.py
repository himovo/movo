from app.enterprise_capabilities.browser.engine.human_commit_reconciliation import (
    assess_human_commit_reconciliation,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _observation(url: str, *, editable: bool = False, page_text: str = "") -> Observation:
    return Observation(
        url=url,
        title="test",
        elements=[{
            "ref": "e1",
            "role": "textbox",
            "editable": True,
            "visible": True,
        }] if editable else [],
        page_text=page_text,
        revision="r2",
        fresh=True,
    )


def test_positive_post_human_url_requests_task_completion_confirmation() -> None:
    decision = assess_human_commit_reconciliation(
        capability_id="browser.publish_or_submit",
        assistance_kind="form_media",
        human_outcome="completed",
        before_url="https://creator.example/edit?id=1",
        after=_observation("https://creator.example/publish?published=true"),
        form_state={"fields": [{"field_key": "body", "status": "confirmed"}]},
        existing_receipts=[],
    )

    assert decision.should_ask
    assert "positive commit status" in decision.evidence[0]


def test_editor_still_open_does_not_infer_a_human_commit() -> None:
    decision = assess_human_commit_reconciliation(
        capability_id="browser.publish_or_submit",
        assistance_kind="form_media",
        human_outcome="completed",
        before_url="https://creator.example/edit?id=1",
        after=_observation("https://creator.example/edit?id=1", editable=True),
        form_state={"fields": [{"field_key": "body", "status": "confirmed"}]},
        existing_receipts=[],
    )

    assert not decision.should_ask


def test_existing_agent_receipt_suppresses_human_commit_reconciliation() -> None:
    decision = assess_human_commit_reconciliation(
        capability_id="browser.publish",
        assistance_kind="form_fill",
        human_outcome="completed",
        before_url="https://creator.example/edit",
        after=_observation("https://creator.example/success", page_text="发布成功"),
        form_state={"fields": []},
        existing_receipts=[{"status": "pending"}],
    )

    assert not decision.should_ask
