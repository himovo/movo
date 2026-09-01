"""Run scheduled Agent turns through the same formal DSH application boundary."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from bson import ObjectId

from app.core.db import get_db
from app.core.tenant import add_main_scope
from app.dsh_runtime.application import dsh_runtime_application
from app.dsh_runtime.chat_service import DshChatService, PreparedTurn
from app.dsh_runtime.turn_admission import admit_skill_selection

from .repository import JOBS, RUNS
from .schedule import utc_now


logger = logging.getLogger(__name__)


class ScheduledDshExecution:
    """Own scheduling metadata while DSH owns the Agent turn and projection."""

    def __init__(self, chat_provider: Callable[[], DshChatService] | None = None) -> None:
        self._chat_provider = chat_provider or dsh_runtime_application.require_chat
        self._observers: set[asyncio.Task[None]] = set()

    async def start(
        self,
        *,
        job: dict[str, Any],
        run: dict[str, Any],
        conversation_id: str | None,
        conversation_title: str | None,
        tenant_id: str,
        user_id: str,
    ) -> PreparedTurn:
        output_spec = dict(job.get("output_spec") or {})
        selected = str(
            output_spec.get("selected_skill_id")
            or output_spec.get("selectedSkillId")
            or ""
        ).strip()
        selection = await admit_skill_selection(
            tenant_id=tenant_id,
            user_id=user_id,
            selected_skill_id=selected,
        )
        chat = self._chat_provider()
        turn = await chat.prepare_turn(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            text=str(job.get("prompt") or "").strip(),
            model_instance_id=str(
                output_spec.get("model_id") or output_spec.get("modelId") or ""
            ).strip() or None,
            timezone_name=str(job.get("timezone") or "UTC"),
            images=[],
            documents=[],
            knowledge_qa_enabled=bool(
                output_spec.get("knowledge_qa_enabled")
                or output_spec.get("knowledgeQaEnabled")
            ),
            knowledge_base_ids=list(
                output_spec.get("knowledge_base_ids")
                or output_spec.get("knowledgeBaseIds")
                or []
            ),
            language_name=str(
                output_spec.get("language") or output_spec.get("locale") or ""
            ).strip() or None,
            selected_writing_skill_id=selection.selected_writing_skill_id,
            selected_skill_id=selection.selected_skill_id,
        )
        await self._mark_started(
            job=job,
            run=run,
            turn=turn,
            conversation_title=conversation_title,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        observer = asyncio.create_task(
            self._observe(
                chat=chat,
                job=job,
                run=run,
                turn=turn,
                tenant_id=tenant_id,
                user_id=user_id,
            ),
            name=f"scheduled-dsh-observer:{run.get('run_id')}",
        )
        self._observers.add(observer)
        observer.add_done_callback(self._observers.discard)
        return turn

    async def shutdown(self) -> None:
        observers = list(self._observers)
        for task in observers:
            task.cancel()
        if observers:
            await asyncio.gather(*observers, return_exceptions=True)
        self._observers.clear()

    async def _observe(
        self,
        *,
        chat: DshChatService,
        job: dict[str, Any],
        run: dict[str, Any],
        turn: PreparedTurn,
        tenant_id: str,
        user_id: str,
    ) -> None:
        try:
            outcome = await chat.wait_turn(turn.message_id)
            status = self._status(outcome)
            await self._mark_finished(
                job=job,
                run=run,
                turn=turn,
                status=status,
                error="" if status == "completed" else outcome,
                tenant_id=tenant_id,
                user_id=user_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "scheduled DSH turn observer failed",
                extra={"event": "scheduled.dsh_observer_failed", "run_id": run.get("run_id")},
            )
            await self._mark_finished(
                job=job,
                run=run,
                turn=turn,
                status="failed",
                error=str(exc) or type(exc).__name__,
                tenant_id=tenant_id,
                user_id=user_id,
            )

    async def _mark_started(
        self,
        *,
        job: dict[str, Any],
        run: dict[str, Any],
        turn: PreparedTurn,
        conversation_title: str | None,
        tenant_id: str,
        user_id: str,
    ) -> None:
        now = utc_now()
        db = get_db()
        if conversation_title and ObjectId.is_valid(turn.conversation_id):
            await db.chat_sessions.update_one(
                add_main_scope(
                    {"_id": ObjectId(turn.conversation_id), "user_id": user_id}, tenant_id
                ),
                {"$set": {"title": conversation_title[:160], "updated_at": now}},
            )
        schedule_fields = {
            "trigger_source": "scheduled",
            "scheduled_job_id": str(job.get("_id") or ""),
            "scheduled_run_id": str(run.get("run_id") or ""),
        }
        await db.chat_messages.update_one(
            add_main_scope(
                {"session_id": ObjectId(turn.conversation_id), "message_id": turn.message_id},
                tenant_id,
            ),
            {"$set": schedule_fields},
        )
        await db[RUNS].update_one(
            {"run_id": str(run.get("run_id") or ""), "main_id": tenant_id, "run_as_user_id": user_id},
            {"$set": {
                "status": "running",
                "session_id": turn.conversation_id,
                "message_id": turn.message_id,
                "started_at": now,
                "updated_at": now,
            }},
        )
        await db[JOBS].update_one(
            {"_id": job["_id"], "main_id": tenant_id},
            {"$set": {
                "last_run_status": "running",
                "last_session_id": turn.conversation_id,
                "updated_at": now,
            }},
        )

    async def _mark_finished(
        self,
        *,
        job: dict[str, Any],
        run: dict[str, Any],
        turn: PreparedTurn,
        status: str,
        error: str,
        tenant_id: str,
        user_id: str,
    ) -> None:
        now = utc_now()
        db = get_db()
        await db.chat_sessions.update_one(
            add_main_scope(
                {"_id": ObjectId(turn.conversation_id), "user_id": user_id}, tenant_id
            ),
            {"$set": {
                "scheduled_unread": True,
                "last_scheduled_run": {
                    "run_id": str(run.get("run_id") or ""),
                    "status": status,
                    "finished_at": now,
                },
                "updated_at": now,
            }},
        )
        await db[RUNS].update_one(
            {"run_id": str(run.get("run_id") or ""), "main_id": tenant_id, "run_as_user_id": user_id},
            {"$set": {
                "status": status,
                "error": str(error)[:1000],
                "finished_at": now,
                "updated_at": now,
            }},
        )
        await db[JOBS].update_one(
            {"_id": job["_id"], "main_id": tenant_id},
            {"$set": {
                "last_run_status": status,
                "last_session_id": turn.conversation_id,
                "last_error": str(error)[:1000],
                "updated_at": now,
            }},
        )

    @staticmethod
    def _status(outcome: str) -> str:
        value = str(outcome or "").strip().lower()
        if value == "completed":
            return "completed"
        if value == "cancelled":
            return "cancelled"
        if value.startswith("suspend") or "waiting_human" in value:
            return "suspended"
        return "failed"


scheduled_dsh_execution = ScheduledDshExecution()
