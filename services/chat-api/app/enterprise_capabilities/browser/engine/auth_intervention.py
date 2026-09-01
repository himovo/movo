"""Single entry point for suspending a desktop browser on authentication."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Protocol, Tuple

from app.enterprise_capabilities.browser.engine.auth_suspension import (
    BrowserAuthSuspension,
    BrowserAuthSuspensionStore,
    browser_auth_suspensions,
)


logger = logging.getLogger(__name__)
BrowserEvent = Tuple[Dict[str, Any], Dict[str, Any]]
CheckpointSaver = Callable[..., Awaitable[None]]
BLOCKING_AUTH_STATES = {
    "required",
    "registration_required",
    "authenticating",
    "failed",
}


class BrowserCommandBridge(Protocol):
    async def send_command(self, command: str, **kwargs: Any) -> None: ...


@dataclass(frozen=True)
class BrowserAuthIntervention:
    run_id: str
    node_id: str
    user_id: str
    chat_session_id: str
    browser_session_id: str
    subagent_id: str
    tab_id: str
    category: str
    url: str
    domain: str
    next_step: int
    source: str
    lang: str
    question: str = ""


def authentication_resume_is_blocked(
    *,
    auth_state: str,
    url_looks_blocked: bool,
    resume_signal: Dict[str, Any],
) -> bool:
    """Reject stale/manual resumes while allowing verified URL-only transitions."""
    state = str(auth_state or "")
    if state in BLOCKING_AUTH_STATES:
        return True
    signal_type = str((resume_signal or {}).get("type") or "")
    signal_source = str((resume_signal or {}).get("source") or "")
    transition_was_verified = (
        signal_type == "browser_auth_completed"
        or signal_source in {"local_auth_watch", "manual_return_to_agent"}
    )
    return not state and bool(url_looks_blocked) and not transition_was_verified


async def suspend_browser_authentication(
    *,
    bridge: BrowserCommandBridge,
    save_checkpoint: CheckpointSaver,
    request: BrowserAuthIntervention,
    store: BrowserAuthSuspensionStore = browser_auth_suspensions,
) -> AsyncIterator[BrowserEvent]:
    """Persist one resumable auth intervention and terminate the current run."""
    await bridge.send_command("set_owner", owner="human")
    await save_checkpoint(
        phase="waiting_auth",
        next_step=max(1, int(request.next_step)),
        status="suspended_waiting_approval",
    )
    suspension = await store.suspend_or_reuse(BrowserAuthSuspension(
        run_id=request.run_id,
        node_id=request.node_id,
        user_id=request.user_id,
        chat_session_id=request.chat_session_id,
        browser_session_id=request.browser_session_id,
        subagent_id=request.subagent_id,
        tab_id=request.tab_id,
        category=request.category,
        url=request.url,
    ))
    await bridge.send_command(
        "start_auth_watch",
        run_id=request.run_id,
        node_id=request.node_id,
        tab_id=request.tab_id,
        category=request.category,
        initially_blocked=True,
    )

    reason = (
        "等待你完成登录或注册，任务已暂停并会在登录后自动继续"
        if request.lang == "zh"
        else "Waiting for authentication; the task is suspended and will resume automatically"
    )
    resume_context = {
        "suspension_id": suspension.suspension_id,
        "run_id": request.run_id,
        "node_id": request.node_id,
        "browser_session_id": request.browser_session_id,
        "tab_id": request.tab_id,
        "resumable": True,
    }
    logger.info(
        "browser authentication suspended",
        extra={
            "event": "browser.auth_suspended",
            "source": request.source,
            "domain": request.domain,
            "url": request.url,
            "suspension_id": suspension.suspension_id,
        },
    )
    yield {
        "type": "intervention",
        "content": {
            "category": request.category,
            "reason": request.domain or request.question or request.url,
            "url": request.url,
            "domain": request.domain,
        },
    }, {}
    yield {
        "type": "activity",
        "content": {"kind": "analyze", "message": reason},
    }, {}
    yield {
        "type": "intervention_required",
        "content": {
            "category": request.category,
            "reason": reason,
            "url": request.url,
            "domain": request.domain,
            **resume_context,
        },
    }, {}
    yield {
        "type": "subagent_done",
        "content": {
            "subagent_id": request.subagent_id,
            "node_id": request.node_id,
            "status": "suspended_waiting_approval",
        },
    }, {
        "gateway": "SUSPEND",
        "browser_receipt": {"status": "intervention_required", "reason": reason},
        "auth_suspension": resume_context,
    }


__all__ = [
    "BrowserAuthIntervention",
    "authentication_resume_is_blocked",
    "suspend_browser_authentication",
]
