from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from .contracts import SuspensionRecord, SuspensionStatus
from .store import SuspensionStore


class SuspensionService:
    def __init__(self, store: Optional[SuspensionStore] = None) -> None:
        self.store = store or SuspensionStore()

    async def suspend(
        self,
        *,
        run_id: str,
        task_id: str,
        node_id: str,
        user_id: str,
        suspension_type: str,
        subagent_id: str = "",
        reason: str = "",
        resume_policy: str = "manual",
        context: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
        resume_token: str = "",
    ) -> SuspensionRecord:
        token_hash = self._hash_token(resume_token) if resume_token else ""
        record = SuspensionRecord(
            suspension_id=f"susp_{uuid.uuid4().hex}",
            run_id=run_id,
            task_id=task_id,
            node_id=node_id,
            user_id=user_id,
            subagent_id=subagent_id,
            suspension_type=suspension_type,
            reason=reason,
            resume_policy=resume_policy,
            context=dict(context or {}),
            expires_at=expires_at,
            resume_token_hash=token_hash,
        )
        return await self.store.create(record)

    async def mark_ready(
        self,
        *,
        suspension_id: str,
        user_id: str,
        signal: Dict[str, Any],
    ) -> Optional[SuspensionRecord]:
        return await self.store.transition(
            suspension_id=suspension_id,
            user_id=user_id,
            from_statuses=[SuspensionStatus.SUSPENDED],
            to_status=SuspensionStatus.READY,
            updates={"ready_signal": dict(signal or {})},
        )

    async def claim_resume(
        self,
        *,
        suspension_id: str,
        user_id: str,
        resume_token: str = "",
    ) -> Optional[SuspensionRecord]:
        current = await self.store.get(suspension_id)
        if not current or current.user_id != user_id or current.status != SuspensionStatus.READY:
            return None
        if current.expires_at and current.expires_at < datetime.utcnow():
            await self.store.transition(
                suspension_id=suspension_id,
                user_id=user_id,
                from_statuses=[SuspensionStatus.SUSPENDED, SuspensionStatus.READY],
                to_status=SuspensionStatus.EXPIRED,
            )
            return None
        if current.resume_token_hash and not secrets.compare_digest(
            current.resume_token_hash,
            self._hash_token(resume_token),
        ):
            return None
        return await self.store.transition(
            suspension_id=suspension_id,
            user_id=user_id,
            from_statuses=[SuspensionStatus.READY],
            to_status=SuspensionStatus.RESUMING,
        )

    async def complete_resume(self, *, suspension_id: str, user_id: str) -> Optional[SuspensionRecord]:
        return await self.store.transition(
            suspension_id=suspension_id,
            user_id=user_id,
            from_statuses=[SuspensionStatus.RESUMING],
            to_status=SuspensionStatus.RESUMED,
        )

    async def fail_resume(self, *, suspension_id: str, user_id: str, error: str) -> Optional[SuspensionRecord]:
        return await self.store.transition(
            suspension_id=suspension_id,
            user_id=user_id,
            from_statuses=[SuspensionStatus.RESUMING],
            to_status=SuspensionStatus.RESUME_FAILED,
            updates={"ready_signal.resume_error": str(error or "resume_failed")[:500]},
        )

    async def release_resume(self, *, suspension_id: str, user_id: str, error: str) -> Optional[SuspensionRecord]:
        return await self.store.transition(
            suspension_id=suspension_id,
            user_id=user_id,
            from_statuses=[SuspensionStatus.RESUMING],
            to_status=SuspensionStatus.READY,
            updates={"ready_signal.resume_error": str(error or "resume_start_failed")[:500]},
        )

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


suspension_service = SuspensionService()
