import asyncio

from app.enterprise_capabilities.browser.service import browser_task
from app.enterprise_capabilities.browser.session_identity import resolve_browser_session_id
from app.enterprise_capabilities.runtime import CapabilityExecutionContext


def test_new_dsh_browser_mission_uses_visible_askai_conversation() -> None:
    assert resolve_browser_session_id(
        conversation_id="conversation-visible",
        resume={},
    ) == "conversation-visible"


def test_browser_resume_preserves_the_checkpoint_session() -> None:
    assert resolve_browser_session_id(
        conversation_id="conversation-visible",
        resume={"browser_session_id": "checkpoint-browser-session"},
    ) == "checkpoint-browser-session"


def test_browser_identity_never_depends_on_dsh_kernel_session() -> None:
    # The resolver intentionally has no kernel_session_id argument.
    assert resolve_browser_session_id(conversation_id="", resume={}) == "default"


def test_browser_adapter_dispatches_to_the_visible_conversation_session(monkeypatch) -> None:
    captured = {}

    class _Checkpoint:
        def __init__(self, **_kwargs):
            self.checkpoint = None
            self.subagent_id = "subagent-visible"

        async def open(self):
            pass

        async def finish(self, status):
            captured["finish"] = status

    class _Executor:
        def __init__(self, _user_id, session_id, **_kwargs):
            captured["session_id"] = session_id

        async def execute(self, **_kwargs):
            yield {"type": "subagent_done", "content": {"status": "succeeded"}}, {
                "browser_result": {"summary": "visible"},
            }

    async def _no_pending(**_kwargs):
        return None

    monkeypatch.setattr("app.enterprise_capabilities.browser.service.agent_registry.get", lambda _user_id: object())
    monkeypatch.setattr("app.enterprise_capabilities.browser.service.pending_browser_result", _no_pending)
    monkeypatch.setattr("app.enterprise_capabilities.browser.service.BrowserCheckpointSession", _Checkpoint)
    monkeypatch.setattr("app.enterprise_capabilities.browser.service.DesktopAgentBrowserExecutor", _Executor)
    result = asyncio.run(browser_task(
        {"objective": "read", "operation": "read"},
        CapabilityExecutionContext(
            tenant_id="tenant-a",
            user_id="user-a",
            conversation_id="conversation-visible",
            kernel_session_id="dsh-hidden-kernel-session",
            profile_version="profile-a",
            action_id="action-a",
        ),
    ))
    assert captured["session_id"] == "conversation-visible"
    assert captured["finish"] == "succeeded"
    assert result["success"] is True
