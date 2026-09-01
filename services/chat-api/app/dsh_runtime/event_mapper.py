"""One-way projection from native DSH Session events to Kernel Event v1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .contracts import KernelEventEnvelope, KernelEventSource
from .errors import DshProtocolError


NATIVE_EVENT_TYPES: dict[str, str] = {
    "assistant/chunk": "agent.message.delta",
    "assistant/message": "agent.message.completed",
    "tool/call": "tool.call.started",
    "tool/result": "tool.call.completed",
    "tool/code-dispatch-start": "tool.call.started",
    "tool/code-dispatch": "tool.call.completed",
    "approval/asked": "tool.approval.requested",
    "approval/decided": "tool.approval.decided",
    "turn/start": "turn.started",
    "turn/end": "turn.completed",
    "step/start": "agent.step.started",
    "step/end": "agent.step.completed",
    "agent/status": "session.status.changed",
}


class DshEventMapper:
    def __init__(self, *, kernel_version: str) -> None:
        self._kernel_version = kernel_version

    @property
    def kernel_version(self) -> str:
        return self._kernel_version

    def map_event(
        self,
        native: dict[str, Any],
        *,
        runtime_id: str,
        session_id: str,
        profile_version: str,
    ) -> KernelEventEnvelope:
        try:
            cursor = int(native["cursor"])
            native_type = str(native["nativeType"])
            time_ms = int(native["time"])
            data = native.get("data", {})
        except (KeyError, TypeError, ValueError) as exc:
            raise DshProtocolError("malformed DSH event envelope") from exc
        if cursor < 1 or not native_type or not isinstance(data, dict):
            raise DshProtocolError("malformed DSH event values")

        payload = dict(data)
        event_type = NATIVE_EVENT_TYPES.get(native_type, "kernel.native.event")
        if native_type == "tool/code-dispatch-start":
            payload = {
                "callId": str(data.get("subCallId") or ""),
                "parentCallId": str(data.get("parentCallId") or ""),
                "rootCallId": str(data.get("rootCallId") or ""),
                "name": str(data.get("name") or "tool"),
                "arguments": data.get("arguments") or {},
                "codeDispatch": True,
            }
        elif native_type == "tool/code-dispatch":
            payload = {
                "callId": str(data.get("subCallId") or ""),
                "parentCallId": str(data.get("parentCallId") or ""),
                "rootCallId": str(data.get("rootCallId") or ""),
                "name": str(data.get("name") or "tool"),
                "arguments": data.get("arguments") or {},
                "isError": bool(data.get("isError")),
                "content": data.get("content") or [],
                "codeDispatch": True,
            }
        if native_type == "assistant/chunk":
            failure = self._model_failure(data)
            if failure is not None:
                event_type = "model.request.failed"
                payload = failure
        if native.get("nativeSeq") is not None:
            payload["native_seq"] = native["nativeSeq"]
        return KernelEventEnvelope(
            event_id=f"{runtime_id}:{session_id}:{cursor}",
            runtime_id=runtime_id,
            session_id=session_id,
            profile_version=profile_version,
            cursor=cursor,
            type=event_type,
            occurred_at=datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc),
            payload=payload,
            source=KernelEventSource(
                kernel_version=self._kernel_version,
                native_event_type=native_type,
            ),
        )

    @staticmethod
    def _model_failure(data: dict[str, Any]) -> dict[str, Any] | None:
        chunk = data.get("chunk")
        if not isinstance(chunk, dict) or chunk.get("type") != "finish":
            return None
        reason = chunk.get("reason")
        if not isinstance(reason, dict) or reason.get("kind") != "error":
            return None
        failure = reason.get("failure")
        if not isinstance(failure, dict):
            failure = {}
        native_code = str(failure.get("code") or "model_provider_failed")
        code = native_code.lower().replace("_", ".")
        non_retryable = ("auth", "scope", "configuration", "invalid.request")
        return {
            "code": code,
            "message": str(failure.get("message") or "model request failed"),
            "retryable": not any(value in code for value in non_retryable),
            "details": {
                key: value
                for key, value in failure.items()
                if key not in {"message", "code"}
            },
        }

    def runtime_failure(
        self,
        *,
        runtime_id: str,
        session_id: str,
        profile_version: str,
        cursor: int,
        message: str,
    ) -> KernelEventEnvelope:
        return KernelEventEnvelope(
            event_id=f"{runtime_id}:{session_id}:failure:{cursor}",
            runtime_id=runtime_id,
            session_id=session_id,
            profile_version=profile_version,
            cursor=cursor,
            type="runtime.failed",
            occurred_at=datetime.now(timezone.utc),
            payload={"code": "dsh_runtime_unavailable", "message": message, "retryable": True},
            source=KernelEventSource(kernel_version=self._kernel_version, native_event_type=None),
        )
