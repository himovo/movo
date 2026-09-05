"""Application use case for the formal DSH-backed ASKAI Chat API."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.dsh_runtime.bindings import BindingReplacementConflict, KernelBindingRepository
from app.dsh_runtime.contracts import CancelSessionRequest
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.events import KernelEventRepository
from app.dsh_runtime.events.live_stream import LiveTurnStream
from app.dsh_runtime.events.projection_writer import ProjectionScope
from app.dsh_runtime.events.turn_channel import TurnEventRegistry
from app.dsh_runtime.gateway import DshAgentKernelGateway
from app.dsh_runtime.locale import resolve_turn_locale
from app.dsh_runtime.profile.service import RuntimeProfilePublisher
from app.dsh_runtime.profile.synchronizer import ConversationProfileSynchronizer
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator
from app.dsh_runtime.temporal_context import build_temporal_context
from app.dsh_runtime.turn_cancellation import TurnCancellationCoordinator
from app.dsh_runtime.turn_runner import DshTurnRunner
from app.dsh_runtime.turn_finalization import TurnStateFinalizer
from app.dsh_runtime.turn_recovery import TurnTerminalRecovery
from app.enterprise_capabilities.evidence import ExecutionEvidenceRepository
from app.dsh_runtime.events.authoritative_delivery import DeliveryStore


@dataclass(frozen=True)
class PreparedTurn:
    conversation_id: str
    message_id: str
    binding_id: str


class ConversationBusyError(RuntimeError):
    pass


class DshChatService:
    def __init__(
        self,
        *,
        gateway: DshAgentKernelGateway,
        coordinator: RuntimeCoordinator,
        conversations: ConversationRepository,
        bindings: KernelBindingRepository,
        events: KernelEventRepository,
        profiles: RuntimeProfilePublisher,
        kernel_version: str,
        turn_events: TurnEventRegistry | None = None,
        execution_evidence: ExecutionEvidenceRepository | None = None,
        authoritative_deliveries: DeliveryStore | None = None,
    ) -> None:
        self._gateway = gateway
        self._coordinator = coordinator
        self._conversations = conversations
        self._bindings = bindings
        self._events = events
        self._profiles = profiles
        self._profile_sync = ConversationProfileSynchronizer(profiles, coordinator)
        self._turn_events = turn_events
        self._turn_runner = DshTurnRunner(
            gateway=gateway,
            conversations=conversations,
            bindings=bindings,
            events=events,
            profiles=profiles,
            kernel_version=kernel_version,
            turn_events=turn_events,
            execution_evidence=execution_evidence,
            authoritative_deliveries=authoritative_deliveries,
        )
        self._tasks: dict[str, asyncio.Task[str]] = {}
        self._turn_outcomes: dict[str, str] = {}
        self._live_streams: dict[str, LiveTurnStream] = {}
        self._finalizer = TurnStateFinalizer(bindings, conversations)
        self._terminal_recovery = TurnTerminalRecovery(
            gateway=gateway,
            conversations=conversations,
            bindings=bindings,
            events=events,
            profiles=profiles,
            authoritative_deliveries=authoritative_deliveries,
        )
        self._cancellation = TurnCancellationCoordinator(
            gateway=gateway,
            runtime_coordinator=coordinator,
            conversations=conversations,
            bindings=bindings,
            recovery=self._terminal_recovery,
            task_for_message=self._tasks.get,
        )

    async def prepare_turn(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str | None,
        text: str,
        model_instance_id: str | None,
        timezone_name: str | None,
        images: list[dict[str, Any]],
        documents: list[dict[str, Any]],
        knowledge_qa_enabled: bool = False,
        knowledge_base_ids: list[str] | None = None,
        trusted_turn_context: dict[str, Any] | None = None,
        language_name: str | None = None,
        selected_writing_skill_id: str | None = None,
        selected_skill_id: str | None = None,
    ) -> PreparedTurn:
        temporal_context = build_temporal_context(timezone_name)
        locale = resolve_turn_locale(text, explicit=language_name)
        turn_context = {
            "knowledge_qa_enabled": bool(knowledge_qa_enabled),
            "knowledge_base_ids": list(dict.fromkeys(str(item) for item in list(knowledge_base_ids or []) if str(item))),
            "images": self._safe_attachments(images),
            "documents": self._safe_attachments(documents),
            # Server-only original request used to exclude the active user row
            # when a capability semantically selects prior-turn evidence. The
            # DSH Host allowlist deliberately filters this field.
            "user_request": text,
        }
        # Trusted selection references. The Host resolves these opaque IDs
        # only against its immutable Runtime Profile; arbitrary instructions
        # and the server-only user_request field never cross that contract.
        if selected_writing_skill_id:
            turn_context["selected_writing_skill_id"] = str(selected_writing_skill_id)
        if selected_skill_id:
            turn_context["selected_skill_id"] = str(selected_skill_id)
        turn_metadata = {
            "language": "zh" if locale.startswith("zh") else "en",
            "locale": locale,
        }
        turn_context["language"] = turn_metadata["language"]
        # This argument is only supplied by internal authenticated endpoints
        # (for example browser resume). It is never copied from ChatRequest.
        if trusted_turn_context:
            browser_resume = trusted_turn_context.get("browser_resume")
            if isinstance(browser_resume, dict):
                turn_context["browser_resume"] = dict(browser_resume)
        binding: dict[str, Any] | None = None
        if conversation_id:
            await self._conversations.owned(conversation_id, tenant_id=tenant_id, user_id=user_id)
            binding = await self._bindings.current(conversation_id, tenant_id=tenant_id, user_id=user_id)
            if binding is None:
                # Conversations created before the DSH cut-over (and empty
                # scheduled-task targets) are ASKAI business records without
                # a Kernel Binding. Continue them by creating the first DSH
                # binding; never route them through the legacy Runtime.
                profile = await self._profiles.publish_model_profile(
                    tenant_id=tenant_id,
                    actor_id=user_id,
                    user_id=user_id,
                    model_instance_id=model_instance_id,
                    activate=False,
                )
                binding = await self._coordinator.create_binding(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    profile_version=profile.profile_version,
                    model_instance_id=profile.model_instance_id,
                )
            if str(binding.get("execution_location") or "server") != "server":
                raise ValueError("this Code task must continue on its bound desktop Runtime")
            if model_instance_id and model_instance_id != str(binding["model_instance_id"]):
                raise ValueError("a Conversation keeps its immutable model profile; create a new Conversation to switch model")
            active_status = str((binding.get("active_turn") or {}).get("status") or "")
            if active_status and active_status not in {"completed", "failed", "cancelled"}:
                binding = await self._terminal_recovery.recover(binding)
                active_status = str((binding.get("active_turn") or {}).get("status") or "")
            elif active_status in {"completed", "failed", "cancelled"}:
                terminal_message_id = str((binding.get("active_turn") or {}).get("message_id") or "")
                if terminal_message_id:
                    await self._finalizer.finalize(
                        binding=binding,
                        message_id=terminal_message_id,
                        status=active_status,
                    )
            if active_status and active_status not in {"completed", "failed", "cancelled"}:
                raise ConversationBusyError("another DSH turn is already running for this Conversation")
            try:
                binding = (await self._profile_sync.synchronize(
                    binding,
                    tenant_id=tenant_id,
                    user_id=user_id,
                )).binding
            except BindingReplacementConflict as exc:
                raise ConversationBusyError(
                    "another turn refreshed this Conversation; retry on the current binding"
                ) from exc
        else:
            profile = await self._profiles.publish_model_profile(
                tenant_id=tenant_id,
                actor_id=user_id,
                user_id=user_id,
                model_instance_id=model_instance_id,
                # Conversation profiles include the user's visible Tool set;
                # they are immutable execution snapshots, not tenant defaults.
                activate=False,
            )
            conversation = await self._conversations.create(
                tenant_id=tenant_id,
                user_id=user_id,
                title=text[:120],
            )
            conversation_id = str(conversation["_id"])
            try:
                binding = await self._coordinator.create_binding(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    profile_version=profile.profile_version,
                    model_instance_id=profile.model_instance_id,
                )
            except Exception:
                await self._conversations.delete_if_empty(
                    conversation_id, tenant_id=tenant_id, user_id=user_id
                )
                raise

        message_id = f"msg-{uuid4()}"
        request_id = f"turn-{uuid4()}"
        claimed = await self._bindings.claim_turn(
            str(binding["binding_id"]), message_id=message_id, request_id=request_id,
            turn_context=turn_context,
            turn_metadata=turn_metadata,
        )
        if claimed is None:
            raise ConversationBusyError("another DSH turn is already running for this Conversation")
        try:
            await self._conversations.append_message(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                role="user",
                content=text,
                message_id=f"user-{request_id}",
                images=images,
                documents=documents,
            )
            await self._conversations.append_message(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                role="assistant",
                content="",
                message_id=message_id,
            )
            await self._conversations.mark_active_run(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                message_id=message_id,
                run_id=request_id,
            )
        except Exception:
            await self._bindings.finish_turn(
                str(binding["binding_id"]), message_id=message_id, status="failed"
            )
            raise
        live_stream = LiveTurnStream()
        self._live_streams[message_id] = live_stream
        if self._turn_events is not None:
            self._turn_events.register(
                ProjectionScope(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    kernel_session_id=str(binding["kernel_session_id"]),
                ),
                live_stream,
            )
        task = asyncio.create_task(
            self._turn_runner.run(
                binding=claimed,
                message_id=message_id,
                request_id=request_id,
                text=text,
                temporal_context=temporal_context,
                turn_context=turn_context,
                live_stream=live_stream,
            ),
            name=f"dsh-turn:{message_id}",
        )
        self._tasks[message_id] = task
        task.add_done_callback(lambda finished: self._turn_finished(message_id, finished))
        return PreparedTurn(
            conversation_id=conversation_id,
            message_id=message_id,
            binding_id=str(binding["binding_id"]),
        )

    async def wait_turn(self, message_id: str) -> str:
        """Wait for the owned DSH runner, independent of an SSE subscriber."""
        task = self._tasks.get(message_id)
        if task is None:
            return self._turn_outcomes.pop(message_id, "unknown")
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            raise
        except Exception:
            return "failed"
        return self._turn_outcomes.pop(message_id, str(task.result() or "unknown"))

    @staticmethod
    def _safe_attachments(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed = {"object_path", "filename", "content_type", "size"}
        return [
            {key: value for key, value in dict(item).items() if key in allowed and value not in (None, "")}
            for item in items[:20]
            if isinstance(item, dict) and str(item.get("object_path") or "").strip()
        ]

    async def stream(self, turn: PreparedTurn, *, tenant_id: str, user_id: str) -> AsyncIterator[str]:
        live_stream = self._live_streams.get(turn.message_id)
        if live_stream is None:
            raise LookupError("live_turn_stream_not_found")
        try:
            async for projected in live_stream.events():
                row = dict(projected)
                row.setdefault("session_id", turn.conversation_id)
                row.setdefault("task_id", turn.conversation_id)
                yield json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        finally:
            live_stream.detach()
            if self._live_streams.get(turn.message_id) is live_stream:
                self._live_streams.pop(turn.message_id, None)

    async def snapshot(
        self,
        message_id: str,
        *,
        tenant_id: str,
        user_id: str,
        after_cursor: int,
    ) -> dict[str, Any]:
        message = await self._conversations.message(
            message_id, tenant_id=tenant_id, user_id=user_id
        )
        if message is None:
            raise LookupError("message_not_found")
        binding = await self._bindings.by_message(message_id, tenant_id=tenant_id, user_id=user_id)
        if binding and str((binding.get("active_turn") or {}).get("status")) == "running":
            try:
                binding = await self._coordinator.restore(binding)
                await self._terminal_recovery.ingest_once(
                    binding=binding, message_id=message_id
                )
            except Exception:
                pass
        rows = await self._events.list_for_message(
            message_id,
            tenant_id=tenant_id,
            user_id=user_id,
            after_cursor=after_cursor,
        )
        all_rows = await self._events.all_for_message(message_id, tenant_id=tenant_id, user_id=user_id)
        terminal = next(
            (row for row in reversed(all_rows) if row.get("type") in {"run.completed", "run.failed", "run.cancelled"}),
            None,
        )
        next_cursor = max(
            [after_cursor, *[int(row.get("stream_seq_end") or row.get("stream_seq") or 0) for row in rows]]
        )
        status = "live" if terminal is None else str(terminal["type"]).removeprefix("run.")
        return {
            "message_id": message_id,
            "session_id": str(message.get("session_id") or ""),
            "status": status,
            "exit_reason": status,
            "events": rows,
            "next_cursor": next_cursor,
            "next_index": next_cursor,
            "live": terminal is None,
        }

    async def cancel(self, conversation_id: str, *, tenant_id: str, user_id: str) -> bool:
        return await self._cancellation.cancel(
            conversation_id, tenant_id=tenant_id, user_id=user_id
        )

    async def dispose_conversation(self, conversation_id: str, *, tenant_id: str, user_id: str) -> None:
        await self._conversations.owned(conversation_id, tenant_id=tenant_id, user_id=user_id)
        binding = await self._bindings.current(conversation_id, tenant_id=tenant_id, user_id=user_id)
        if binding is None:
            return
        try:
            binding = await self._coordinator.restore(binding)
            if str((binding.get("active_turn") or {}).get("status")) == "running":
                await self._gateway.cancel(
                    CancelSessionRequest(
                        session_id=str(binding["kernel_session_id"]), cause="conversation_deleted"
                    )
                )
            await self._gateway.dispose_session(str(binding["kernel_session_id"]))
        except Exception:
            await self._bindings.mark_disposed(str(binding["binding_id"]), pending=True)
            return
        await self._bindings.mark_disposed(str(binding["binding_id"]))

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        if tasks:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def _turn_finished(self, message_id: str, task: asyncio.Task[str]) -> None:
        self._tasks.pop(message_id, None)
        self._turn_outcomes[message_id] = (
            "cancelled" if task.cancelled()
            else ("failed" if task.exception() else str(task.result() or "unknown"))
        )
        if len(self._turn_outcomes) > 1000:
            self._turn_outcomes.pop(next(iter(self._turn_outcomes)))
        live_stream = self._live_streams.get(message_id)
        if live_stream is not None:
            live_stream.finish()
