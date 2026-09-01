"""Single ASKAI policy and execution authority for DSH-managed tool calls."""

from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from typing import Any

from app.dsh_runtime.profile.store import RuntimeProfileStore
from app.dsh_runtime.profile.tools import ToolProfileDefinition
from app.dsh_runtime.tool_gateway import ToolGatewayClaims
from app.dsh_runtime.events.turn_channel import TurnEventRegistry
from app.services.external_tools import external_tool_service
from app.governance.position_policy import EmployeePolicyResolver

from app.enterprise_capabilities.runtime import CapabilityExecutionContext, InternalCapabilityService
from app.enterprise_capabilities.evidence import ExecutionEvidenceRepository
from app.enterprise_capabilities.content.invocation_contract import (
    ContentInvocationContractRepository,
)
from app.enterprise_capabilities.content.style_scope import apply_writing_style_ref
from app.enterprise_capabilities.delivery import (
    AuthoritativeDeliveryRepository,
    record_accepted_delivery,
    reuse_accepted_delivery,
)
from .contracts import ApprovalAskRequest, EnterpriseActionReceipt, EnterpriseApproval, ToolExecuteRequest
from .approval_events import approval_requested_event, approval_resolved_event
from .approval_scope import approval_scope
from .repository import EnterpriseToolRepository
from .result_compaction import compact_tool_result
from .execution_timeout import (
    ExecutionActivity,
    ExecutionDeadlineExceeded,
    ExecutionTimeoutPolicy,
    execute_with_timeout,
)


class ToolPolicyDenied(RuntimeError):
    pass


class EnterpriseToolService:
    def __init__(
        self,
        repository: EnterpriseToolRepository,
        profiles: RuntimeProfileStore,
        internal_capabilities: InternalCapabilityService | None = None,
        turn_events: TurnEventRegistry | None = None,
        execution_evidence: ExecutionEvidenceRepository | None = None,
        content_contracts: ContentInvocationContractRepository | None = None,
        authoritative_deliveries: AuthoritativeDeliveryRepository | None = None,
        employee_policy: EmployeePolicyResolver | None = None,
    ) -> None:
        self._repository = repository
        self._profiles = profiles
        self._internal_capabilities = internal_capabilities
        self._turn_events = turn_events
        self._execution_evidence = execution_evidence or ExecutionEvidenceRepository()
        self._content_contracts = content_contracts or ContentInvocationContractRepository()
        self._authoritative_deliveries = authoritative_deliveries
        self._employee_policy = employee_policy
        self._signals: dict[str, asyncio.Event] = defaultdict(asyncio.Event)

    async def request_approval(self, request: ApprovalAskRequest, claims: ToolGatewayClaims) -> str:
        tool, binding = await self._authorize(request.toolName, request.profileVersion, request.sessionId, claims)
        if not self._approval_required(tool, request.arguments):
            return "allowed-once"
        scope = approval_scope(tool, request.arguments)
        conversation_id = str(binding["conversation_id"])
        active_turn = dict(binding.get("active_turn") or {})
        message_id = str(active_turn.get("message_id") or "")
        grant = await self._repository.active_session_grant(
            tenant_id=claims.tenant_id,
            user_id=claims.user_id,
            conversation_id=conversation_id,
            profile_version=request.profileVersion,
            scope_key=scope.key,
        )
        if grant is not None:
            await self._repository.audit(
                tenant_id=claims.tenant_id,
                user_id=claims.user_id,
                action_id=request.actionId,
                event="approval.session_grant.used",
                details={"tool_name": tool.name, "grant_id": grant.grant_id, "scope_key": scope.key},
            )
            return "allowed-once"
        approval = await self._repository.ensure_approval(EnterpriseApproval(
            action_id=request.actionId,
            tenant_id=claims.tenant_id,
            user_id=claims.user_id,
            conversation_id=conversation_id,
            kernel_session_id=request.sessionId,
            profile_version=request.profileVersion,
            tool_name=tool.name,
            reason=request.reason,
            message_id=message_id,
            arguments=dict(request.arguments),
            scope_key=scope.key,
            scope_label=scope.label,
        ))
        await self._repository.audit(
            tenant_id=claims.tenant_id, user_id=claims.user_id, action_id=request.actionId,
            event="approval.requested", details={"tool_name": tool.name, "risk_level": tool.risk_level},
        )
        if approval.status != "pending":
            return self._approval_outcome(approval.status)
        await self._publish_approval(
            approval,
            approval_requested_event(
                approval,
                display_name=tool.display_name or tool.name,
                description=tool.description,
                risk_level=tool.risk_level,
            ),
        )
        deadline = asyncio.get_running_loop().time() + request.timeoutSeconds
        signal = self._signals[request.actionId]
        try:
            while True:
                current = await self._repository.approval(request.actionId)
                if current is None:
                    return "unavailable"
                if current.status != "pending":
                    return self._approval_outcome(current.status)
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    expired = await self._repository.expire(request.actionId)
                    if expired is not None:
                        await self._publish_approval(expired, approval_resolved_event(expired))
                    return "unavailable"
                try:
                    await asyncio.wait_for(signal.wait(), timeout=min(remaining, 0.5))
                    signal.clear()
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            cancelled = await self._repository.decide(
                request.actionId, decision="cancelled", actor_id="kernel-cancel", tenant_id=claims.tenant_id
            )
            if cancelled is not None:
                await self._publish_approval(cancelled, approval_resolved_event(cancelled))
            raise
        finally:
            self._signals.pop(request.actionId, None)

    async def decide(
        self,
        action_id: str,
        *,
        decision: str,
        actor_id: str,
        tenant_id: str,
        subject_user_id: str | None = None,
        grant_scope: str = "once",
    ) -> EnterpriseApproval:
        current = await self._repository.approval(action_id)
        if current is None or current.tenant_id != tenant_id:
            raise LookupError("approval_not_found")
        if subject_user_id is not None and current.user_id != subject_user_id:
            raise ToolPolicyDenied("approval_subject_mismatch")
        if decision != "approved" and grant_scope != "once":
            raise ValueError("session grant is only valid for an approved decision")
        row = await self._repository.decide(action_id, decision=decision, actor_id=actor_id, tenant_id=tenant_id)
        if row is None:
            existing = current
            if existing is None or existing.tenant_id != tenant_id:
                raise LookupError("approval_not_found")
            if existing.status != decision:
                raise ValueError(f"approval is already {existing.status}")
            row = existing
        if decision == "approved" and grant_scope == "session":
            await self._repository.grant_for_session(row, actor_id=actor_id)
            row = row.model_copy(update={"grant_scope": "session"})
            await self._repository.set_approval_grant_scope(action_id, "session")
        signal = self._signals.get(action_id)
        if signal is not None:
            signal.set()
        await self._repository.audit(
            tenant_id=tenant_id, user_id=row.user_id, action_id=action_id,
            event=f"approval.{decision}", details={"tool_name": row.tool_name, "actor_id": actor_id},
        )
        await self._publish_approval(row, approval_resolved_event(row))
        return row

    async def list_pending(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str | None = None,
    ) -> list[EnterpriseApproval]:
        return await self._repository.list_pending(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
        )

    async def _publish_approval(self, approval: EnterpriseApproval, event: dict[str, Any]) -> None:
        if self._turn_events is None or not approval.message_id:
            return
        publish_standalone = getattr(self._turn_events, "publish_standalone", None)
        if callable(publish_standalone):
            await publish_standalone(approval.message_id, event)
            return
        sink = self._turn_events.progress_sink(approval.message_id, approval.action_id)
        if sink is not None:
            await sink(event)

    async def execute(self, request: ToolExecuteRequest, claims: ToolGatewayClaims) -> EnterpriseActionReceipt:
        tool, binding = await self._authorize(request.toolName, request.profileVersion, request.sessionId, claims)
        existing = await self._repository.receipt_by_idempotency(request.idempotencyKey)
        if existing is not None:
            if existing.action_id != request.actionId or existing.tool_name != request.toolName:
                raise ToolPolicyDenied("idempotency key is bound to another action")
            return existing
        if self._approval_required(tool, request.arguments):
            approval = await self._repository.approval(request.actionId)
            if approval is None or approval.status != "approved":
                scope = approval_scope(tool, request.arguments)
                grant = await self._repository.active_session_grant(
                    tenant_id=claims.tenant_id,
                    user_id=claims.user_id,
                    conversation_id=str(binding["conversation_id"]),
                    profile_version=request.profileVersion,
                    scope_key=scope.key,
                )
                if grant is None:
                    raise ToolPolicyDenied("one-shot or session MOVO approval is required")
        receipt = EnterpriseActionReceipt(
            action_id=request.actionId,
            idempotency_key=request.idempotencyKey,
            tenant_id=claims.tenant_id,
            user_id=claims.user_id,
            conversation_id=str(binding["conversation_id"]),
            kernel_session_id=request.sessionId,
            profile_version=request.profileVersion,
            tool_name=tool.name,
            status="running",
        )
        receipt = await self._repository.start_receipt(receipt)
        if receipt.status != "running":
            return receipt
        active_turn = dict(binding.get("active_turn") or {})
        message_id = str(active_turn.get("message_id") or "")
        if tool.delivery_mode == "authoritative_markdown" and self._authoritative_deliveries is not None:
            reused_result = await reuse_accepted_delivery(
                self._authoritative_deliveries,
                action_id=request.actionId,
                tenant_id=claims.tenant_id,
                user_id=claims.user_id,
                message_id=message_id,
                tool_name=tool.name,
            )
            if reused_result is not None:
                receipt = await self._repository.finish_receipt(
                    request.actionId,
                    status="succeeded",
                    result=self._bounded_result(reused_result),
                )
                await self._repository.audit(
                    tenant_id=claims.tenant_id,
                    user_id=claims.user_id,
                    action_id=request.actionId,
                    event="content.delivery.reused",
                    details={
                        "tool_name": tool.name,
                        "source_action_id": reused_result["source_action_id"],
                    },
                )
                await self._repository.audit(
                    tenant_id=claims.tenant_id,
                    user_id=claims.user_id,
                    action_id=request.actionId,
                    event="tool.succeeded",
                    details={"tool_name": tool.name, "error": ""},
                )
                return receipt
        await self._repository.audit(
            tenant_id=claims.tenant_id, user_id=claims.user_id, action_id=request.actionId,
            event="tool.started", details={"tool_name": tool.name, "idempotency_key": request.idempotencyKey},
        )
        try:
            activity = ExecutionActivity() if tool.timeout_mode == "activity" else None
            if tool.source_type == "internal":
                if self._internal_capabilities is None:
                    raise LookupError("internal capability runtime is unavailable")
                execution_arguments = dict(request.arguments)
                capability_turn_context = {
                    **dict(active_turn.get("turn_context") or {}),
                    **dict(active_turn.get("turn_metadata") or {}),
                }
                if str(tool.capability_ref or "") == "content.produce@v1":
                    profile = await self._profiles.get(request.profileVersion)
                    try:
                        execution_arguments, capability_turn_context = apply_writing_style_ref(
                            execution_arguments, capability_turn_context, profile,
                        )
                    except PermissionError as exc:
                        raise ToolPolicyDenied(str(exc)) from exc
                    resolved_contract = await self._content_contracts.resolve(
                        tenant_id=claims.tenant_id,
                        user_id=claims.user_id,
                        kernel_session_id=request.sessionId,
                        message_id=str(active_turn.get("message_id") or ""),
                        arguments=execution_arguments,
                    )
                    execution_arguments = dict(resolved_contract.arguments)
                    if resolved_contract.recovered_fields:
                        capability_turn_context["content_contract_recovered_fields"] = list(
                            resolved_contract.recovered_fields
                        )
                        await self._repository.audit(
                            tenant_id=claims.tenant_id,
                            user_id=claims.user_id,
                            action_id=request.actionId,
                            event="content.contract.recovered",
                            details={
                                "fields": list(resolved_contract.recovered_fields),
                                "fingerprint": resolved_contract.fingerprint,
                            },
                        )
                if tool.consumes_execution_evidence:
                    upstream_evidence = await self._execution_evidence.load(
                        tenant_id=claims.tenant_id,
                        user_id=claims.user_id,
                        kernel_session_id=request.sessionId,
                        message_id=str(active_turn.get("message_id") or ""),
                    )
                    if upstream_evidence:
                        capability_turn_context["evidence_bundle"] = upstream_evidence
                base_progress_sink = (
                    self._turn_events.progress_sink(
                        str(active_turn.get("message_id") or ""),
                        request.actionId,
                    )
                    if self._turn_events is not None else None
                )
                execution = self._internal_capabilities.execute(
                    tool.capability_ref or tool.external_tool_id,
                    execution_arguments,
                    CapabilityExecutionContext(
                        tenant_id=claims.tenant_id,
                        user_id=claims.user_id,
                        conversation_id=str(binding["conversation_id"]),
                        kernel_session_id=request.sessionId,
                        profile_version=request.profileVersion,
                        model_instance_id=str(binding.get("model_instance_id") or ""),
                        action_id=request.actionId,
                        message_id=str(active_turn.get("message_id") or ""),
                        turn_context=capability_turn_context,
                        progress_sink=(activity.progress_sink(base_progress_sink) if activity else base_progress_sink),
                    ),
                )
            else:
                execution = external_tool_service.execute_runtime(
                    main_id=claims.tenant_id,
                    external_tool_id=tool.external_tool_id,
                    provider_type=tool.source_type,
                    mcp_tool_name=tool.mcp_tool_name,
                    arguments=request.arguments,
                    actor_user_id=claims.user_id,
                )
            result = await execute_with_timeout(
                execution,
                policy=ExecutionTimeoutPolicy(
                    total_seconds=tool.timeout_ms / 1000,
                    inactivity_seconds=(
                        tool.inactivity_timeout_ms / 1000
                        if tool.timeout_mode == "activity" else 0
                    ),
                ),
                activity=activity,
            )
            execution_evidence = result.pop("_execution_evidence_bundle", None)
            if isinstance(execution_evidence, dict) and execution_evidence:
                active_turn = dict(binding.get("active_turn") or {})
                await self._execution_evidence.append(
                    tenant_id=claims.tenant_id,
                    user_id=claims.user_id,
                    kernel_session_id=request.sessionId,
                    message_id=str(active_turn.get("message_id") or ""),
                    action_id=request.actionId,
                    bundle=execution_evidence,
                )
            if tool.delivery_mode == "authoritative_markdown" and self._authoritative_deliveries is not None:
                await record_accepted_delivery(
                    self._authoritative_deliveries,
                    result=result,
                    action_id=request.actionId,
                    tenant_id=claims.tenant_id,
                    user_id=claims.user_id,
                    message_id=message_id,
                    tool_name=tool.name,
                )
            bounded = self._bounded_result(result)
            governed_rejection = (
                tool.delivery_mode == "authoritative_markdown"
                and result.get("accepted") is False
            )
            execution_succeeded = bool(result.get("success", True)) or governed_rejection
            receipt = await self._repository.finish_receipt(
                request.actionId,
                status="succeeded" if execution_succeeded else "failed",
                result=bounded,
                error="" if execution_succeeded else str(result.get("message") or "tool failed"),
            )
        except ExecutionDeadlineExceeded as exc:
            receipt = await self._repository.finish_receipt(
                request.actionId, status="timed_out", error=exc.reason
            )
        except asyncio.CancelledError:
            await self._repository.finish_receipt(request.actionId, status="cancelled", error="tool execution cancelled")
            raise
        except Exception as exc:
            receipt = await self._repository.finish_receipt(
                request.actionId, status="failed", error=self._safe_error(exc)
            )
        await self._repository.audit(
            tenant_id=claims.tenant_id, user_id=claims.user_id, action_id=request.actionId,
            event=f"tool.{receipt.status}", details={"tool_name": tool.name, "error": receipt.error},
        )
        return receipt

    async def _authorize(
        self, tool_name: str, profile_version: str, session_id: str, claims: ToolGatewayClaims
    ) -> tuple[ToolProfileDefinition, dict[str, Any]]:
        if profile_version != claims.profile_version or tool_name not in claims.tool_names:
            raise ToolPolicyDenied("tool is outside the signed Runtime Profile scope")
        profile = await self._profiles.get(profile_version)
        if profile.tenant_id != claims.tenant_id or profile.subject_user_id != claims.user_id:
            raise ToolPolicyDenied("Runtime Profile subject mismatch")
        tool = next((item for item in profile.tools if item.name == tool_name), None)
        if tool is None or not set(tool.required_scopes).issubset(claims.scopes):
            raise ToolPolicyDenied("required tool scope is missing")
        if self._employee_policy is not None:
            current_policy = await self._employee_policy.resolve(claims.tenant_id, claims.user_id)
            allowed = (
                current_policy.allows_internal(str(tool.capability_ref or ""))
                if tool.source_type == "internal"
                else current_policy.allows_external_tool(str(tool.external_tool_id or ""))
            )
            if not allowed:
                await self._repository.audit(
                    tenant_id=claims.tenant_id,
                    user_id=claims.user_id,
                    action_id="policy-denied",
                    event="capability.denied",
                    details={"tool_name": tool.name, "reason": "position_role"},
                )
                raise ToolPolicyDenied("当前岗位未开通该能力，本次任务未执行")
        binding = await self._repository.session_binding(session_id)
        if binding is None or any((
            str(binding.get("tenant_id")) != claims.tenant_id,
            str(binding.get("user_id")) != claims.user_id,
            str(binding.get("profile_version")) != profile_version,
        )):
            raise ToolPolicyDenied("Kernel Session scope mismatch")
        return tool, binding

    @staticmethod
    def _approval_outcome(status: str) -> str:
        return "allowed-once" if status == "approved" else ("cancelled" if status == "cancelled" else "rejected")

    @staticmethod
    def _approval_required(tool: ToolProfileDefinition, arguments: dict[str, Any]) -> bool:
        if tool.approval_required:
            return True
        if not tool.approval_argument or not tool.approval_values:
            return False
        return str(arguments.get(tool.approval_argument) or "") in set(tool.approval_values)

    @staticmethod
    def _bounded_result(result: dict[str, Any], max_bytes: int = 64 * 1024) -> dict[str, Any]:
        return compact_tool_result(result, max_bytes=max_bytes)

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        message = str(exc)[:2000]
        message = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", message)
        return re.sub(
            r"(?i)\b(api[_ -]?key|authorization|bearer|token)(\s*[:=]?\s*)[^\s,;]+",
            r"\1\2[REDACTED]",
            message,
        ) or "tool execution failed"
