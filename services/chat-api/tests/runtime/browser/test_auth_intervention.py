from __future__ import annotations

import asyncio

from app.enterprise_capabilities.browser.engine import auth_suspension
from app.enterprise_capabilities.browser.engine.auth_intervention import (
    BrowserAuthIntervention,
    authentication_resume_is_blocked,
    suspend_browser_authentication,
)
from app.enterprise_capabilities.browser.engine.auth_suspension import BrowserAuthSuspension
from app.governance.suspensions.contracts import (
    SuspensionRecord,
    SuspensionStatus,
    SuspensionType,
)


class FakeBridge:
    def __init__(self) -> None:
        self.commands = []

    async def send_command(self, command: str, **kwargs) -> None:
        self.commands.append((command, kwargs))


class FakeStore:
    def __init__(self) -> None:
        self.records = []

    async def suspend_or_reuse(self, record: BrowserAuthSuspension) -> BrowserAuthSuspension:
        self.records.append(record)
        return record.model_copy(update={"suspension_id": "auth-suspension-1"})


def test_auth_intervention_persists_watcher_and_resumable_events_once() -> None:
    bridge = FakeBridge()
    store = FakeStore()
    checkpoints = []

    async def save_checkpoint(**kwargs) -> None:
        checkpoints.append(kwargs)

    request = BrowserAuthIntervention(
        run_id="run-1",
        node_id="node-1",
        user_id="user-1",
        chat_session_id="chat-1",
        browser_session_id="browser-1",
        subagent_id="agent-1",
        tab_id="tab-1",
        category="login",
        url="https://example.test/login",
        domain="example.test",
        next_step=7,
        source="ask_user",
        lang="zh",
    )

    async def collect():
        return [
            event
            async for event in suspend_browser_authentication(
                bridge=bridge,
                save_checkpoint=save_checkpoint,
                request=request,
                store=store,
            )
        ]

    events = asyncio.run(collect())

    assert checkpoints == [{
        "phase": "waiting_auth",
        "next_step": 7,
        "status": "suspended_waiting_approval",
    }]
    assert len(store.records) == 1
    assert bridge.commands == [
        ("set_owner", {"owner": "human"}),
        ("start_auth_watch", {
            "run_id": "run-1",
            "node_id": "node-1",
            "tab_id": "tab-1",
            "category": "login",
            "initially_blocked": True,
        }),
    ]
    event_types = [event[0]["type"] for event in events]
    assert event_types == [
        "intervention",
        "activity",
        "intervention_required",
        "subagent_done",
    ]
    intervention = events[2][0]["content"]
    assert intervention["resumable"] is True
    assert intervention["suspension_id"] == "auth-suspension-1"
    assert events[-1][1]["gateway"] == "SUSPEND"


def test_resume_validation_rejects_explicit_login_but_accepts_verified_url_only_transition() -> None:
    assert authentication_resume_is_blocked(
        auth_state="required",
        url_looks_blocked=True,
        resume_signal={"type": "browser_auth_completed"},
    )
    assert not authentication_resume_is_blocked(
        auth_state="",
        url_looks_blocked=True,
        resume_signal={"type": "browser_auth_completed", "source": "local_auth_watch"},
    )
    assert not authentication_resume_is_blocked(
        auth_state="",
        url_looks_blocked=True,
        resume_signal={"source": "manual_return_to_agent"},
    )
    assert authentication_resume_is_blocked(
        auth_state="",
        url_looks_blocked=True,
        resume_signal={},
    )


def test_auth_suspension_reuses_the_active_record_for_the_same_node(monkeypatch) -> None:
    existing = SuspensionRecord(
        suspension_id="existing-auth",
        run_id="run-1",
        task_id="chat-1",
        node_id="node-1",
        user_id="user-1",
        suspension_type=SuspensionType.BROWSER_AUTH.value,
        status=SuspensionStatus.SUSPENDED,
        context={
            "browser_session_id": "browser-1",
            "tab_id": "tab-1",
            "category": "login",
            "url": "https://example.test/login",
        },
    )

    class FakeRuntimeStore:
        async def latest_active_for_node(self, **kwargs):
            return existing

    class FakeRuntimeService:
        store = FakeRuntimeStore()

        async def suspend(self, **kwargs):
            raise AssertionError("an active auth suspension must be reused")

    monkeypatch.setattr(auth_suspension, "suspension_service", FakeRuntimeService())
    store = auth_suspension.BrowserAuthSuspensionStore()
    record = BrowserAuthSuspension(
        run_id="run-1",
        node_id="node-1",
        user_id="user-1",
        chat_session_id="chat-1",
        browser_session_id="browser-1",
        tab_id="tab-1",
        category="login",
        url="https://example.test/login",
    )

    reused = asyncio.run(store.suspend_or_reuse(record))

    assert reused.suspension_id == "existing-auth"
    assert reused.chat_session_id == "chat-1"
