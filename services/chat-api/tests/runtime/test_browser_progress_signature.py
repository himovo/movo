from app.enterprise_capabilities.browser.engine.progress_signature import browser_progress_signature
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _observation(page_text: str, ref: str) -> Observation:
    return Observation(
        url="https://example.test/post/1",
        title="Post",
        page_text=page_text,
        elements=[
            {"ref": ref, "role": "textbox", "name": "Comment", "editable": True, "value": page_text},
            {"ref": f"{ref}-send", "role": "button", "name": "Send", "disabled": False},
        ],
    )


def test_dynamic_text_and_ref_changes_do_not_fake_business_progress() -> None:
    ledger = {
        "phase": "general_awaiting_commit",
        "completed_signals": ["target_page_opened"],
        "remaining_signals": ["requested_operation_confirmed"],
    }

    assert browser_progress_signature(
        _observation("在线人数 18", "e1"),
        state_ledger=ledger,
    ) == browser_progress_signature(
        _observation("在线人数 19", "e91"),
        state_ledger=ledger,
    )


def test_mission_milestone_changes_progress_signature() -> None:
    observation = _observation("Body", "e1")
    before = {
        "phase": "general_awaiting_commit",
        "completed_signals": ["target_page_opened"],
        "remaining_signals": ["requested_operation_confirmed"],
    }
    after = {
        "phase": "general_ready_to_finish",
        "completed_signals": ["target_page_opened", "requested_operation_confirmed"],
        "remaining_signals": [],
    }

    assert browser_progress_signature(
        observation,
        state_ledger=before,
    ) != browser_progress_signature(
        observation,
        state_ledger=after,
    )
