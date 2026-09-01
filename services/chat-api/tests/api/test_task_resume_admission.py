import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.endpoints import tasks
from app.governance.suspensions.contracts import SuspensionRecord, SuspensionStatus


def test_resume_endpoint_passes_a_scoped_browser_context_to_dsh(monkeypatch):
    observed = []

    async def resolve_user(_authorization=None):
        return {"user": {"_id": "user-1"}, "main_id": "main-1"}

    async def claim_resume(**_kwargs):
        return SimpleNamespace(
            suspension_id="suspension-1",
            run_id="run-1",
            node_id="node-1",
            task_id="session-1",
            ready_signal={"type": "approved"},
            context={},
        )

    async def fake_chat_completions(request, _authorization=None, *, trusted_turn_context=None):
        observed.append(trusted_turn_context)

        async def body():
            yield b"{}\n"

        return SimpleNamespace(
            headers={"X-Message-Id": "message-1"},
            status_code=200,
            body_iterator=body(),
        )

    monkeypatch.setattr(tasks, "_resolve_session_user", resolve_user)
    monkeypatch.setattr(tasks.suspension_service, "claim_resume", claim_resume)
    monkeypatch.setattr("app.api.endpoints.dsh_chat._start_chat_completions", fake_chat_completions)
    monkeypatch.setattr(
        "app.enterprise_capabilities.browser.resume_lifecycle.schedule_browser_resume",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.dsh_runtime.application.dsh_runtime_application.require_chat",
        lambda: SimpleNamespace(),
    )

    async def exercise():
        response = await tasks.resume_task(
            "run-1",
            tasks.TaskResumeRequest(
                suspension_id="suspension-1",
                node_id="node-1",
                messages=[{"role": "user", "content": "continue"}],
            ),
        )
        async for _chunk in response.body_iterator:
            pass

    asyncio.run(exercise())

    assert observed[0]["browser_resume"]["suspension_id"] == "suspension-1"
    assert observed[0]["browser_resume"]["run_id"] == "run-1"


def test_manual_browser_intervention_marks_only_browser_user_input_ready(monkeypatch):
    async def resolve_user(_authorization=None):
        return {"user": {"_id": "user-1"}, "main_id": "main-1"}

    suspended = SuspensionRecord(
        suspension_id="suspension-1",
        run_id="run-1",
        task_id="session-1",
        node_id="node-1",
        user_id="user-1",
        suspension_type="user_input",
        context={"browser_session_id": "session-1"},
    )
    observed = []

    async def get_record(_suspension_id):
        return suspended

    async def mark_ready(**kwargs):
        observed.append(kwargs)
        return suspended.model_copy(update={"status": SuspensionStatus.READY})

    monkeypatch.setattr(tasks, "_resolve_session_user", resolve_user)
    monkeypatch.setattr(tasks.suspension_service.store, "get", get_record)
    monkeypatch.setattr(tasks.suspension_service, "mark_ready", mark_ready)

    result = asyncio.run(tasks.mark_task_suspension_manual_ready(
        "suspension-1",
        tasks.TaskSuspensionReadyRequest(signal={"type": "forged", "source": "forged"}),
    ))

    assert result["data"]["status"] == "ready"
    assert observed[0]["signal"] == {
        "type": "human_intervention_completed",
        "source": "manual_return_to_agent",
    }


def test_manual_browser_intervention_cannot_approve_other_suspension_types(monkeypatch):
    async def resolve_user(_authorization=None):
        return {"user": {"_id": "user-1"}, "main_id": "main-1"}

    approval = SuspensionRecord(
        suspension_id="approval-1",
        run_id="run-1",
        task_id="session-1",
        node_id="node-1",
        user_id="user-1",
        suspension_type="approval",
    )

    async def get_record(_suspension_id):
        return approval

    monkeypatch.setattr(tasks, "_resolve_session_user", resolve_user)
    monkeypatch.setattr(tasks.suspension_service.store, "get", get_record)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(tasks.mark_task_suspension_manual_ready(
            "approval-1",
            tasks.TaskSuspensionReadyRequest(),
        ))
    assert exc.value.status_code == 409
