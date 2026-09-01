"""One DSH turn: immediate live delivery with ordered durable projection."""

from __future__ import annotations

import asyncio
import logging
from time import monotonic
from typing import Any

from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.credential_lease import ActiveTurnCredentialLease
from app.dsh_runtime.contracts import ContentBlock, SendMode, SendRequest, TemporalContext
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.event_mapper import DshEventMapper
from app.dsh_runtime.events import KernelEventRepository, KernelEventWrite
from app.dsh_runtime.events.durable_writer import DurableKernelEventWriter
from app.dsh_runtime.events.live_stream import LiveTurnStream
from app.dsh_runtime.events.turn_channel import TurnEventRegistry
from app.dsh_runtime.events.tool_presentation import tool_presentations
from app.dsh_runtime.events.authoritative_delivery import AuthoritativeDeliveryGuard, DeliveryStore
from app.dsh_runtime.evidence_projection import (
    build_execution_evidence_event,
    project_execution_evidence,
)
from app.dsh_runtime.gateway import DshAgentKernelGateway
from app.dsh_runtime.profile.service import RuntimeProfilePublisher
from app.enterprise_capabilities.evidence import ExecutionEvidenceRepository


logger = logging.getLogger(__name__)

_KERNEL_TURN_CONTEXT_KEYS = frozenset({
    "knowledge_qa_enabled", "knowledge_base_ids", "images", "documents", "browser_resume",
    "selected_writing_skill_id", "selected_skill_id",
})


def kernel_turn_context(turn_context: dict[str, Any] | None) -> dict[str, Any]:
    return {
        key: value for key, value in dict(turn_context or {}).items()
        if key in _KERNEL_TURN_CONTEXT_KEYS
    }


class DshTurnRunner:
    def __init__(
        self,
        *,
        gateway: DshAgentKernelGateway,
        conversations: ConversationRepository,
        bindings: KernelBindingRepository,
        events: KernelEventRepository,
        profiles: RuntimeProfilePublisher,
        kernel_version: str,
        turn_events: TurnEventRegistry | None = None,
        execution_evidence: ExecutionEvidenceRepository | None = None,
        authoritative_deliveries: DeliveryStore | None = None,
        credential_refresh_interval_seconds: float = 240.0,
    ) -> str:
        self._gateway = gateway
        self._conversations = conversations
        self._bindings = bindings
        self._events = events
        self._profiles = profiles
        self._turn_events = turn_events
        self._execution_evidence = execution_evidence
        self._authoritative_deliveries = authoritative_deliveries
        self._credential_refresh_interval_seconds = credential_refresh_interval_seconds
        self._mapper = DshEventMapper(kernel_version=kernel_version)

    async def run(
        self,
        *,
        binding: dict[str, Any],
        message_id: str,
        request_id: str,
        text: str,
        temporal_context: TemporalContext,
        live_stream: LiveTurnStream,
        turn_context: dict[str, Any] | None = None,
    ) -> None:
        status = "interrupted"
        assistant_text = ""
        history_events: list[dict[str, Any]] = []
        started_at = monotonic()
        first_delta_at: float | None = None
        terminal_received_at: float | None = None
        native_event_count = 0
        delta_count = 0
        last_native_cursor = int(binding.get("event_cursor") or 0)
        terminal_projection: dict[str, Any] | None = None
        browser_intervention: dict[str, Any] | None = None
        writer_aborted = False
        writer = DurableKernelEventWriter(
            events=self._events,
            bindings=self._bindings,
            binding_id=str(binding["binding_id"]),
            tenant_id=str(binding["tenant_id"]),
            user_id=str(binding["user_id"]),
            conversation_id=str(binding["conversation_id"]),
            message_id=message_id,
        )
        credential_lease = ActiveTurnCredentialLease(
            self._gateway,
            session_id=str(binding["kernel_session_id"]),
            interval_seconds=self._credential_refresh_interval_seconds,
        )
        try:
            profile = await self._profiles.get(str(binding["profile_version"]))
            tool_ui = tool_presentations(profile)
            delivery_guard = AuthoritativeDeliveryGuard(
                store=self._authoritative_deliveries,
                tool_presentations=tool_ui,
                tenant_id=str(binding["tenant_id"]),
                user_id=str(binding["user_id"]),
                message_id=message_id,
            )
            await self._gateway.send(
                SendRequest(
                    session_id=str(binding["kernel_session_id"]),
                    request_id=request_id,
                    mode=SendMode.FOLLOWUP,
                    content=[ContentBlock(type="text", data={"text": text})],
                    temporal_context=temporal_context,
                    turn_context=kernel_turn_context(turn_context),
                )
            )
            credential_lease.start()
            async for event in self._gateway.subscribe(
                str(binding["kernel_session_id"]), int(binding.get("event_cursor") or 0)
            ):
                native_event_count += 1
                if event.type == "tool.approval.requested":
                    await credential_lease.refresh_now()
                projected = self._events.project(
                    event,
                    message_id=message_id,
                    tool_presentations=tool_ui,
                )
                projected = await delivery_guard.apply(event, projected)
                is_terminal = event.type in {"turn.completed", "runtime.failed"}
                if projected is not None:
                    projected = await self._publish_kernel(
                        message_id,
                        projected,
                        live_stream=live_stream,
                        publish_live=not is_terminal,
                    )
                writer.enqueue(KernelEventWrite(event=event, projected=projected))
                side_band_action_id = self._side_band_action_id(projected)
                if side_band_action_id and self._turn_events is not None:
                    # The parent tool row must be durable before any child
                    # Browser Agent rows become replayable after reconnect.
                    await writer.flush()
                    await self._turn_events.mark_action_durable(
                        message_id, side_band_action_id
                    )
                if projected is not None and projected.get("type") != "item.delta":
                    history_events.append(projected)
                    candidate = (projected.get("payload") or {}).get("browser_intervention")
                    if isinstance(candidate, dict) and candidate.get("suspension_id"):
                        browser_intervention = dict(candidate)
                last_native_cursor = max(last_native_cursor, event.cursor)
                if projected and projected.get("item_kind") == "final_answer":
                    value = str((projected.get("payload") or {}).get("text") or "")
                    if projected.get("type") == "item.completed":
                        assistant_text = value
                    if projected.get("type") == "item.delta":
                        delta_count += 1
                        if first_delta_at is None:
                            first_delta_at = monotonic()
                if is_terminal:
                    terminal_received_at = monotonic()
                    terminal_projection = projected
                    status = (
                        str((projected or {}).get("type") or "run.completed").removeprefix("run.")
                        if event.type == "turn.completed"
                        else "failed"
                    )
                    await writer.flush()
                    if self._turn_events is not None:
                        await self._turn_events.flush(message_id)
                    break
        except asyncio.CancelledError:
            await credential_lease.stop()
            await writer.abort()
            await self._finish_side_events(message_id)
            await self._clear_active_run(binding=binding, message_id=message_id)
            return "cancelled"
        except Exception as exc:
            await writer.abort()
            writer_aborted = True
            status = "failed"
            terminal_projection = await self._best_effort_failure(
                binding=binding,
                message_id=message_id,
                cursor=9_000_000_000_000_000 + last_native_cursor,
                error=exc,
            )
            if terminal_projection is not None:
                history_events.append(terminal_projection)
        if status == "interrupted":
            await credential_lease.stop()
            await writer.abort()
            await self._finish_side_events(message_id)
            await self._clear_active_run(binding=binding, message_id=message_id)
            live_stream.finish()
            return "interrupted"
        try:
            if not writer_aborted:
                await writer.close()
            evidence_bundles: list[dict[str, Any]] = []
            if self._execution_evidence is not None:
                evidence_bundle = await self._execution_evidence.load(
                    tenant_id=str(binding["tenant_id"]),
                    user_id=str(binding["user_id"]),
                    kernel_session_id=str(binding["kernel_session_id"]),
                    message_id=message_id,
                )
                public_evidence_bundle = project_execution_evidence(
                    evidence_bundle,
                    evidence_id=f"evidence-{message_id}",
                )
                if public_evidence_bundle:
                    evidence_bundles.append(public_evidence_bundle)
                    evidence_event = build_execution_evidence_event(
                        message_id=message_id,
                        payload=public_evidence_bundle,
                    )
                    if self._turn_events is not None:
                        await self._turn_events.publish_standalone(message_id, evidence_event)
                    else:
                        live_stream.publish(evidence_event)
                        history_events.append(evidence_event)
            side_history = await self._finish_side_events(message_id)
            history_events.extend(side_history)
            history_events.sort(key=lambda row: int(row.get("stream_seq") or 0))
            await self._conversations.update_assistant_projection(
                message_id=message_id,
                tenant_id=str(binding["tenant_id"]),
                user_id=str(binding["user_id"]),
                content=assistant_text,
                execution_events=history_events,
                evidence_bundles=evidence_bundles,
            )
            await self._bindings.finish_turn(
                str(binding["binding_id"]), message_id=message_id, status=status
            )
        except Exception as exc:
            status = "failed"
            terminal_projection = await self._failure_projection(
                binding=binding,
                message_id=message_id,
                cursor=9_100_000_000_000_000 + last_native_cursor,
                error=exc,
            )
            try:
                await self._bindings.finish_turn(
                    str(binding["binding_id"]), message_id=message_id, status=status
                )
            except Exception:
                pass
        finally:
            await credential_lease.stop()
            if browser_intervention is not None and status == "completed":
                await self._conversations.suspend_active_run(
                    conversation_id=str(binding["conversation_id"]),
                    tenant_id=str(binding["tenant_id"]),
                    user_id=str(binding["user_id"]),
                    message_id=message_id,
                    intervention=browser_intervention,
                )
            else:
                await self._clear_active_run(binding=binding, message_id=message_id)
            if terminal_projection is not None:
                live_stream.publish(terminal_projection)
            live_stream.finish()
            self._log_performance(
                message_id=message_id,
                status=status,
                started_at=started_at,
                first_delta_at=first_delta_at,
                terminal_received_at=terminal_received_at,
                native_event_count=native_event_count,
                delta_count=delta_count,
            )
        return status

    async def _publish_kernel(
        self,
        message_id: str,
        projected: dict[str, Any],
        *,
        live_stream: LiveTurnStream,
        publish_live: bool,
    ) -> dict[str, Any]:
        if self._turn_events is None:
            if publish_live:
                live_stream.publish(projected)
            return projected
        return await self._turn_events.publish_kernel(
            message_id, projected, publish_live=publish_live
        )

    async def _finish_side_events(self, message_id: str) -> list[dict[str, Any]]:
        if self._turn_events is None:
            return []
        return await self._turn_events.finish(message_id)

    @staticmethod
    def _side_band_action_id(projected: dict[str, Any] | None) -> str:
        if not projected or projected.get("type") != "item.started":
            return ""
        payload = projected.get("payload")
        if not isinstance(payload, dict) or payload.get("name") != "browser_task":
            return ""
        return str(payload.get("callId") or "")

    async def _clear_active_run(self, *, binding: dict[str, Any], message_id: str) -> None:
        try:
            await self._conversations.clear_active_run(
                conversation_id=str(binding["conversation_id"]),
                tenant_id=str(binding["tenant_id"]),
                user_id=str(binding["user_id"]),
                message_id=message_id,
            )
        except Exception:
            logger.exception("failed to clear DSH active_run", extra={"message_id": message_id})

    async def _best_effort_failure(
        self,
        *,
        binding: dict[str, Any],
        message_id: str,
        cursor: int,
        error: Exception,
    ) -> dict[str, Any] | None:
        failure = self._mapper.runtime_failure(
            runtime_id=str(binding["runtime_id"]),
            session_id=str(binding["kernel_session_id"]),
            profile_version=str(binding["profile_version"]),
            cursor=cursor,
            message=str(error),
        )
        projected = self._events.project(failure, message_id=message_id)
        if projected is not None and self._turn_events is not None:
            projected = await self._turn_events.publish_kernel(
                message_id, projected, publish_live=False
            )
        try:
            await self._events.persist_batch(
                [KernelEventWrite(event=failure, projected=projected)],
                tenant_id=str(binding["tenant_id"]),
                user_id=str(binding["user_id"]),
                conversation_id=str(binding["conversation_id"]),
                message_id=message_id,
            )
        except Exception:
            pass
        return projected

    async def _failure_projection(
        self,
        *,
        binding: dict[str, Any],
        message_id: str,
        cursor: int,
        error: Exception,
    ) -> dict[str, Any] | None:
        failure = self._mapper.runtime_failure(
            runtime_id=str(binding["runtime_id"]),
            session_id=str(binding["kernel_session_id"]),
            profile_version=str(binding["profile_version"]),
            cursor=cursor,
            message=str(error),
        )
        projected = self._events.project(failure, message_id=message_id)
        if projected is not None and self._turn_events is not None:
            projected = await self._turn_events.publish_kernel(
                message_id, projected, publish_live=False
            )
        return projected

    @staticmethod
    def _log_performance(
        *,
        message_id: str,
        status: str,
        started_at: float,
        first_delta_at: float | None,
        terminal_received_at: float | None,
        native_event_count: int,
        delta_count: int,
    ) -> None:
        finished_at = monotonic()
        logger.info(
            "DSH turn live delivery and durable projection finished",
            extra={
                "event": "dsh.turn.performance",
                "message_id": message_id,
                "status": status,
                "native_event_count": native_event_count,
                "delta_count": delta_count,
                "first_delta_ms": (
                    round((first_delta_at - started_at) * 1000)
                    if first_delta_at is not None
                    else None
                ),
                "native_terminal_ms": (
                    round((terminal_received_at - started_at) * 1000)
                    if terminal_received_at is not None
                    else None
                ),
                "terminal_commit_ms": (
                    round((finished_at - terminal_received_at) * 1000)
                    if terminal_received_at is not None
                    else None
                ),
                "total_ms": round((finished_at - started_at) * 1000),
            },
        )
