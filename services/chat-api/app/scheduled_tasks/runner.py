"""Scheduled task admission; Agent execution is owned exclusively by DSH."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from bson import ObjectId

from app.core.db import get_db
from app.core.quota_policy import assert_quota_available
from app.core.tenant import add_main_scope, resolve_main_id

from .dsh_execution import scheduled_dsh_execution
from .repository import JOBS, RUNS
from .schedule import UTC, get_zone, utc_now


logger = logging.getLogger(__name__)


class ScheduledChatRunner:
    async def start(self, job: dict[str, Any], run: dict[str, Any]) -> None:
        tenant_id = resolve_main_id(job.get("main_id"))
        user_id = str(job.get("run_as_user_id") or job.get("owner_user_id") or "")
        if not ObjectId.is_valid(user_id):
            await self._fail_before_start(job, run, "执行用户不存在")
            return
        user = await get_db().end_users.find_one(
            add_main_scope({"_id": ObjectId(user_id), "status": "active"}, tenant_id)
        )
        if not user:
            await self._fail_before_start(job, run, "执行用户已停用或不属于当前租户")
            return
        try:
            await assert_quota_available(tenant_id, user)
            conversation_id, title = await self._resolve_target(
                job, run, tenant_id=tenant_id, user_id=user_id
            )
            await scheduled_dsh_execution.start(
                job=job,
                run=run,
                conversation_id=conversation_id,
                conversation_title=title,
                tenant_id=tenant_id,
                user_id=user_id,
            )
        except Exception as exc:
            logger.exception(
                "scheduled DSH start failed",
                extra={"event": "scheduled.dsh_start_failed", "run_id": run.get("run_id")},
            )
            await self._fail_before_start(job, run, str(exc) or type(exc).__name__)

    async def _resolve_target(
        self,
        job: dict[str, Any],
        run: dict[str, Any],
        *,
        tenant_id: str,
        user_id: str,
    ) -> tuple[str | None, str | None]:
        if str(job.get("session_mode") or "fixed") == "fixed":
            session_id = str(job.get("session_id") or "")
            if not ObjectId.is_valid(session_id):
                raise LookupError("目标会话不存在")
            exists = await get_db().chat_sessions.find_one(
                add_main_scope(
                    {"_id": ObjectId(session_id), "user_id": user_id}, tenant_id
                ),
                {"_id": 1},
            )
            if not exists:
                raise LookupError("目标会话不存在或无权访问")
            return session_id, None

        scheduled_for = run.get("scheduled_for") or utc_now()
        if not isinstance(scheduled_for, datetime):
            scheduled_for = utc_now()
        local_date = scheduled_for.replace(tzinfo=UTC).astimezone(
            get_zone(str(job.get("timezone") or "UTC"))
        ).strftime("%Y-%m-%d")
        template = str(job.get("session_title_template") or "{name} · {date}")
        try:
            title = template.format(name=str(job.get("name") or "定时任务"), date=local_date)
        except Exception:
            title = f"{str(job.get('name') or '定时任务')} · {local_date}"
        # DSH Chat creates the ASKAI Conversation and Kernel Binding as one
        # admitted operation. An empty legacy session has no execution identity.
        return None, title[:160]

    async def _fail_before_start(
        self, job: dict[str, Any], run: dict[str, Any], error: str
    ) -> None:
        now = utc_now()
        tenant_id = resolve_main_id(job.get("main_id"))
        await get_db()[RUNS].update_one(
            {"run_id": str(run.get("run_id") or ""), "main_id": tenant_id},
            {"$set": {
                "status": "failed",
                "error": str(error)[:1000],
                "finished_at": now,
                "updated_at": now,
            }},
        )
        await get_db()[JOBS].update_one(
            {"_id": job["_id"], "main_id": tenant_id},
            {"$set": {
                "last_run_status": "failed",
                "last_error": str(error)[:1000],
                "updated_at": now,
            }},
        )


scheduled_chat_runner = ScheduledChatRunner()
