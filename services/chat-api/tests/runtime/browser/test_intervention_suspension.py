from __future__ import annotations

import asyncio

from app.enterprise_capabilities.browser.engine import intervention_suspension
from app.governance.suspensions.contracts import SuspensionRecord, SuspensionStatus


class FakeSuspensionService:
    def __init__(self) -> None:
        self.kwargs = None

    async def suspend(self, **kwargs):
        self.kwargs = kwargs
        return SuspensionRecord(
            suspension_id="susp-1",
            run_id=kwargs["run_id"],
            task_id=kwargs["task_id"],
            node_id=kwargs["node_id"],
            user_id=kwargs["user_id"],
            subagent_id=kwargs["subagent_id"],
            suspension_type=kwargs["suspension_type"],
            status=SuspensionStatus.SUSPENDED,
            reason=kwargs["reason"],
            resume_policy=kwargs["resume_policy"],
            context=kwargs["context"],
        )


def test_browser_intervention_uses_runtime_suspension_contract(monkeypatch):
    fake = FakeSuspensionService()
    monkeypatch.setattr(intervention_suspension, "suspension_service", fake)

    record = asyncio.run(intervention_suspension.suspend_browser_intervention(
        run_id="run-1",
        task_id="task-1",
        node_id="node-1",
        user_id="user-1",
        subagent_id="agent-1",
        browser_session_id="browser-1",
        tab_id="tab-1",
        category="browser",
        reason="Complete the form manually",
        url="https://example.test/form",
    ))

    assert fake.kwargs["suspension_type"] == "user_input"
    assert fake.kwargs["resume_policy"] == "manual"
    assert fake.kwargs["context"]["browser_session_id"] == "browser-1"
    assert intervention_suspension.browser_resume_context(record) == {
        "suspension_id": "susp-1",
        "run_id": "run-1",
        "node_id": "node-1",
        "browser_session_id": "browser-1",
        "tab_id": "tab-1",
        "resumable": True,
    }


def test_resume_uses_server_stored_assistance_contract() -> None:
    record = SuspensionRecord(
        suspension_id="susp-1",
        run_id="run-1",
        task_id="task-1",
        node_id="node-1",
        user_id="user-1",
        suspension_type="user_input",
        status=SuspensionStatus.READY,
        context={
            "handoff": {
                "contract": {
                    "contract_id": "trusted",
                    "kind": "form_commit",
                },
            },
        },
    )

    signal = intervention_suspension.bind_browser_resume_signal(record, {
        "human_outcome": "completed",
        "assistance_contract": {"contract_id": "forged", "kind": "form_effect_verify"},
    })

    assert signal["human_outcome"] == "completed"
    assert signal["assistance_contract"] == {
        "contract_id": "trusted",
        "kind": "form_commit",
    }
