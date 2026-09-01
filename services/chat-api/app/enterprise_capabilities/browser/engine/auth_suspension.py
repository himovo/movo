from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.governance.suspensions import SuspensionStatus, SuspensionType, suspension_service
from app.governance.suspensions.contracts import SuspensionRecord


class BrowserAuthSuspension(BaseModel):
    suspension_id: str = ""
    run_id: str
    node_id: str
    user_id: str
    chat_session_id: str
    browser_session_id: str
    subagent_id: str = ""
    tab_id: str = ""
    category: str = "login"
    url: str = ""
    status: str = "waiting_human"
    ready_url: str = ""
    ready_source: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class BrowserAuthSuspensionStore:
    """Compatibility facade over the runtime-wide suspension service."""

    async def suspend_or_reuse(self, record: BrowserAuthSuspension) -> BrowserAuthSuspension:
        existing = await suspension_service.store.latest_active_for_node(
            user_id=record.user_id,
            run_id=record.run_id,
            node_id=record.node_id,
            suspension_type=SuspensionType.BROWSER_AUTH.value,
        )
        if existing and existing.task_id == record.chat_session_id:
            return self._browser_model(existing)
        return await self.suspend(record)

    async def suspend(self, record: BrowserAuthSuspension) -> BrowserAuthSuspension:
        stored = await suspension_service.suspend(
            run_id=record.run_id,
            task_id=record.chat_session_id,
            node_id=record.node_id,
            user_id=record.user_id,
            subagent_id=record.subagent_id,
            suspension_type=SuspensionType.BROWSER_AUTH.value,
            reason=record.category,
            resume_policy="automatic",
            context={
                "browser_session_id": record.browser_session_id,
                "tab_id": record.tab_id,
                "category": record.category,
                "url": record.url,
            },
        )
        return self._browser_model(stored)

    async def mark_ready(
        self,
        *,
        user_id: str,
        run_id: str,
        node_id: str,
        browser_session_id: str,
        tab_id: str,
        url: str,
        source: str,
    ) -> Optional[BrowserAuthSuspension]:
        current = await suspension_service.store.latest_active(
            user_id=user_id,
            task_id=browser_session_id,
            suspension_type=SuspensionType.BROWSER_AUTH.value,
        )
        if not current or current.run_id != run_id or current.node_id != node_id:
            return None
        context = dict(current.context or {})
        expected_session = str(context.get("browser_session_id") or "")
        expected_tab = str(context.get("tab_id") or "")
        if expected_session and expected_session != browser_session_id:
            return None
        if expected_tab and tab_id and expected_tab != tab_id:
            return None
        ready = await suspension_service.mark_ready(
            suspension_id=current.suspension_id,
            user_id=user_id,
            signal={"type": "browser_auth_completed", "url": url, "source": source, "tab_id": tab_id},
        )
        return self._browser_model(ready) if ready else None

    async def latest_for_session(
        self,
        *,
        user_id: str,
        chat_session_id: str,
    ) -> Optional[BrowserAuthSuspension]:
        row = await suspension_service.store.latest_active(
            user_id=user_id,
            task_id=chat_session_id,
            suspension_type=SuspensionType.BROWSER_AUTH.value,
        )
        return self._browser_model(row) if row else None

    @staticmethod
    def _browser_model(record: SuspensionRecord) -> BrowserAuthSuspension:
        context: Dict[str, Any] = dict(record.context or {})
        signal: Dict[str, Any] = dict(record.ready_signal or {})
        status = {
            SuspensionStatus.SUSPENDED: "waiting_human",
            SuspensionStatus.READY: "ready",
            SuspensionStatus.RESUMING: "resuming",
            SuspensionStatus.RESUMED: "resumed",
        }.get(record.status, record.status.value)
        return BrowserAuthSuspension(
            suspension_id=record.suspension_id,
            run_id=record.run_id,
            node_id=record.node_id,
            user_id=record.user_id,
            chat_session_id=record.task_id,
            browser_session_id=str(context.get("browser_session_id") or record.task_id),
            subagent_id=record.subagent_id,
            tab_id=str(context.get("tab_id") or ""),
            category=str(context.get("category") or record.reason or "login"),
            url=str(context.get("url") or ""),
            status=status,
            ready_url=str(signal.get("url") or ""),
            ready_source=str(signal.get("source") or ""),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


browser_auth_suspensions = BrowserAuthSuspensionStore()
