"""ASKAI-owned AgentKernel Gateway with DSH as its only implementation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from .contracts import (
    AgentKernelContract,
    CancelSessionRequest,
    CreateRuntimeRequest,
    CreateSessionRequest,
    KernelEventEnvelope,
    RuntimeHandle,
    SendMode,
    SendRequest,
    SessionHandle,
    SessionStatus,
)
from .credential_lease import KeyedAsyncLock
from .errors import DshNotFoundError, DshProtocolError, DshTransportError
from .event_mapper import DshEventMapper
from .transport import KernelHostTransport
from .temporal_context import build_temporal_context


@dataclass(frozen=True)
class _SessionBinding:
    runtime_id: str
    profile_version: str
    conversation_id: str
    model_instance_id: str | None
    preset_id: str
    workspace_id: str | None


@dataclass(frozen=True)
class _RuntimeBinding:
    tenant_id: str
    profile_version: str
    model_instance_id: str | None


class RuntimeProfileResolver(Protocol):
    async def resolve(
        self,
        profile_version: str,
        *,
        tenant_id: str | None = None,
    ) -> dict[str, object]: ...


class DshAgentKernelGateway(AgentKernelContract):
    """Thin lifecycle/event boundary; it owns no planning or model logic."""

    def __init__(
        self,
        transport: KernelHostTransport,
        *,
        kernel_version: str = "0.1.0-rc.6",
        profile_resolver: RuntimeProfileResolver | None = None,
    ) -> None:
        self._transport = transport
        self._mapper = DshEventMapper(kernel_version=kernel_version)
        self._sessions: dict[str, _SessionBinding] = {}
        self._runtimes: dict[str, _RuntimeBinding] = {}
        self._profile_resolver = profile_resolver
        self._credential_refresh_locks = KeyedAsyncLock()

    async def create_runtime(self, request: CreateRuntimeRequest) -> RuntimeHandle:
        payload: dict[str, Any] = {
            "tenantId": request.tenant_id,
            "profileVersion": request.profile_version,
            "isolationKey": request.isolation_key,
        }
        model_instance_id: str | None = None
        if self._profile_resolver is not None:
            model_profile = await self._profile_resolver.resolve(
                request.profile_version,
                tenant_id=request.tenant_id,
            )
            payload["modelProfile"] = model_profile
            model_instance_id = self._optional_text(model_profile, "modelInstanceId")
        response = await self._transport.request(
            "POST",
            "/v1/runtimes",
            json=payload,
        )
        runtime_id = self._required_text(response, "runtimeId")
        self._runtimes[runtime_id] = _RuntimeBinding(
            tenant_id=request.tenant_id,
            profile_version=request.profile_version,
            model_instance_id=model_instance_id,
        )
        return RuntimeHandle(
            runtime_id=runtime_id,
            kernel="dsh",
            kernel_version=self._required_text(response, "kernelVersion"),
            profile_version=self._required_text(response, "profileVersion"),
            model_instance_id=model_instance_id,
            isolation_key=self._required_text(response, "isolationKey"),
        )

    async def dispose_runtime(self, runtime_id: str) -> None:
        await self._transport.request("DELETE", f"/v1/runtimes/{runtime_id}")
        self._runtimes.pop(runtime_id, None)
        self._credential_refresh_locks.discard(runtime_id)
        self._sessions = {
            session_id: binding
            for session_id, binding in self._sessions.items()
            if binding.runtime_id != runtime_id
        }

    async def discover_runtime(
        self,
        *,
        tenant_id: str,
        profile_version: str,
        isolation_key: str,
    ) -> RuntimeHandle | None:
        response = await self._transport.request(
            "GET",
            "/v1/runtimes",
            params={"isolationKey": isolation_key},
        )
        raw = response.get("runtime")
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise DshProtocolError("DSH runtime discovery returned invalid data")
        if self._required_text(raw, "profileVersion") != profile_version:
            raise DshProtocolError("DSH isolation key is bound to another Runtime Profile")
        runtime_id = self._required_text(raw, "runtimeId")
        model_instance_id = self._optional_text(raw, "modelInstanceId")
        self._runtimes[runtime_id] = _RuntimeBinding(
            tenant_id=tenant_id,
            profile_version=profile_version,
            model_instance_id=model_instance_id,
        )
        return RuntimeHandle(
            runtime_id=runtime_id,
            kernel="dsh",
            kernel_version=self._mapper.kernel_version,
            profile_version=profile_version,
            model_instance_id=model_instance_id,
            isolation_key=isolation_key,
        )

    def attach_session(
        self,
        *,
        runtime_id: str,
        session_id: str,
        conversation_id: str,
        profile_version: str,
        model_instance_id: str | None,
        preset_id: str = "askai-enterprise",
        workspace_id: str | None = None,
    ) -> None:
        runtime = self._runtime_binding(runtime_id)
        if runtime.profile_version != profile_version or runtime.model_instance_id != model_instance_id:
            raise DshProtocolError("persisted Session binding does not match discovered Runtime")
        self._sessions[session_id] = _SessionBinding(
            runtime_id=runtime_id,
            profile_version=profile_version,
            conversation_id=conversation_id,
            model_instance_id=model_instance_id,
            preset_id=preset_id,
            workspace_id=workspace_id,
        )

    async def describe_session(self, session_id: str) -> SessionHandle:
        binding = self._binding(session_id)
        response = await self._transport.request(
            "GET",
            f"/v1/runtimes/{binding.runtime_id}/sessions/{session_id}",
        )
        return self._session_handle(session_id, response)

    async def create_session(self, request: CreateSessionRequest) -> SessionHandle:
        session_id = f"dsh-{uuid4()}"
        spec = request.session_spec
        runtime_binding = self._runtime_binding(request.runtime_id)
        if spec.tenant_id != runtime_binding.tenant_id or spec.profile_version != runtime_binding.profile_version:
            raise DshProtocolError("Session identity does not match its immutable Runtime Profile")
        response = await self._transport.request(
            "POST",
            f"/v1/runtimes/{request.runtime_id}/sessions",
            json={
                "sessionId": session_id,
                "presetId": spec.preset_id,
                **({"workspaceId": spec.workspace_id} if spec.workspace_id else {}),
                **({
                    "seedRuntimeId": spec.seed_runtime_id,
                    "seedSessionId": spec.seed_session_id,
                } if spec.seed_runtime_id and spec.seed_session_id else {}),
            },
        )
        returned_id = self._required_text(response, "sessionId")
        if returned_id != session_id:
            raise DshProtocolError("DSH Runtime Host changed the allocated session id")
        self._sessions[session_id] = _SessionBinding(
            runtime_id=request.runtime_id,
            profile_version=spec.profile_version,
            conversation_id=spec.conversation_id,
            model_instance_id=runtime_binding.model_instance_id,
            preset_id=spec.preset_id,
            workspace_id=spec.workspace_id,
        )
        return self._session_handle(session_id, response)

    async def resume_session(self, session_id: str) -> SessionHandle:
        binding = self._binding(session_id)
        response = await self._transport.request(
            "POST",
            f"/v1/runtimes/{binding.runtime_id}/sessions/{session_id}/resume",
        )
        return self._session_handle(session_id, response)

    async def send(self, request: SendRequest) -> str:
        binding = self._binding(request.session_id)
        await self._refresh_model_credential(binding.runtime_id)
        temporal_context = request.temporal_context or build_temporal_context("UTC")
        response = await self._transport.request(
            "POST",
            f"/v1/runtimes/{binding.runtime_id}/sessions/{request.session_id}/send",
            json={
                "requestId": request.request_id,
                "mode": "steer" if request.mode is SendMode.STEER else "followup",
                "content": [block.model_dump(mode="json") for block in request.content],
                "temporalContext": (
                    temporal_context.model_dump(mode="json")
                ),
                "turnContext": request.turn_context,
            },
        )
        return self._required_text(response, "messageId")

    async def refresh_session_credentials(self, session_id: str) -> None:
        """Refresh scoped gateway credentials without starting another turn."""
        binding = self._binding(session_id)
        await self._refresh_model_credential(binding.runtime_id)

    async def cancel(self, request: CancelSessionRequest) -> dict[str, Any]:
        binding = self._binding(request.session_id)
        response = await self._transport.request(
            "POST",
            f"/v1/runtimes/{binding.runtime_id}/sessions/{request.session_id}/cancel",
            json={"cause": request.cause},
        )
        if response.get("accepted") is not True:
            raise DshProtocolError("DSH Runtime Host did not accept Session cancellation")
        return response

    async def dispose_session(self, session_id: str) -> None:
        binding = self._binding(session_id)
        await self._transport.request(
            "DELETE",
            f"/v1/runtimes/{binding.runtime_id}/sessions/{session_id}",
        )
        self._sessions.pop(session_id, None)

    async def native_plugin(self, runtime_id: str, action: str, specifier: str) -> dict[str, Any]:
        if action not in {"load", "probe", "unload"}:
            raise ValueError(f"unknown native plugin action: {action}")
        return await self._transport.request(
            "POST",
            f"/v1/runtimes/{runtime_id}/plugins/{action}",
            json={"specifier": specifier},
        )

    async def subscribe(self, session_id: str, after_cursor: int = 0) -> AsyncIterator[KernelEventEnvelope]:
        binding = self._binding(session_id)
        cursor = after_cursor
        try:
            async for native in self._transport.stream(
                "GET",
                f"/v1/runtimes/{binding.runtime_id}/sessions/{session_id}/event-stream",
                params={"after": cursor},
            ):
                event = self._mapper.map_event(
                    native,
                    runtime_id=binding.runtime_id,
                    session_id=session_id,
                    profile_version=binding.profile_version,
                )
                if event.cursor <= cursor:
                    continue
                cursor = event.cursor
                yield event
        except DshTransportError as exc:
            yield self._mapper.runtime_failure(
                runtime_id=binding.runtime_id,
                session_id=session_id,
                profile_version=binding.profile_version,
                cursor=cursor + 1,
                message=str(exc),
            )

    async def events_once(self, session_id: str, after_cursor: int = 0) -> list[KernelEventEnvelope]:
        binding = self._binding(session_id)
        response = await self._transport.request(
            "GET",
            f"/v1/runtimes/{binding.runtime_id}/sessions/{session_id}/events",
            params={"after": after_cursor},
        )
        native_events = response.get("events")
        if not isinstance(native_events, list):
            raise DshProtocolError("DSH events response must contain a list")
        mapped = []
        cursor = after_cursor
        for native in sorted(native_events, key=self._event_cursor):
            if not isinstance(native, dict):
                raise DshProtocolError("DSH event item must be an object")
            event = self._mapper.map_event(
                native,
                runtime_id=binding.runtime_id,
                session_id=session_id,
                profile_version=binding.profile_version,
            )
            if event.cursor <= cursor:
                continue
            cursor = event.cursor
            mapped.append(event)
        return mapped

    def _binding(self, session_id: str) -> _SessionBinding:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise DshNotFoundError(f"unknown DSH session binding: {session_id}") from exc

    def _session_handle(self, session_id: str, response: dict[str, Any]) -> SessionHandle:
        binding = self._binding(session_id)
        status = self._required_text(response, "status")
        mapped_status = SessionStatus.RUNNING if status == "running" else SessionStatus.IDLE
        returned_preset = self._optional_text(response, "presetId") or binding.preset_id
        if returned_preset != binding.preset_id:
            raise DshProtocolError("DSH Runtime Host changed the immutable Session preset")
        returned_workspace = self._optional_text(response, "workspaceId")
        if returned_workspace != binding.workspace_id:
            raise DshProtocolError("DSH Runtime Host changed the immutable Session workspace")
        return SessionHandle(
            runtime_id=binding.runtime_id,
            session_id=session_id,
            conversation_id=binding.conversation_id,
            profile_version=binding.profile_version,
            model_instance_id=binding.model_instance_id,
            preset_id=returned_preset,
            workspace_id=returned_workspace,
            status=mapped_status,
        )

    def _runtime_binding(self, runtime_id: str) -> _RuntimeBinding:
        try:
            return self._runtimes[runtime_id]
        except KeyError as exc:
            raise DshNotFoundError(f"unknown DSH runtime binding: {runtime_id}") from exc

    async def _refresh_model_credential(self, runtime_id: str) -> None:
        if self._profile_resolver is None:
            return
        async with self._credential_refresh_locks.for_key(runtime_id):
            binding = self._runtime_binding(runtime_id)
            model_profile = await self._profile_resolver.resolve(
                binding.profile_version,
                tenant_id=binding.tenant_id,
            )
            if self._optional_text(model_profile, "modelInstanceId") != binding.model_instance_id:
                raise DshProtocolError("published Runtime Profile changed model identity")
            await self._transport.request(
                "PUT",
                f"/v1/runtimes/{runtime_id}/model-credential",
                json={
                    "gatewayUrl": model_profile.get("gatewayUrl"),
                    "accessToken": model_profile.get("accessToken"),
                },
            )
            tool_profile = model_profile.get("toolProfile")
            if isinstance(tool_profile, dict):
                await self._transport.request(
                    "PUT",
                    f"/v1/runtimes/{runtime_id}/tool-credential",
                    json={"accessToken": tool_profile.get("accessToken")},
                )

    @staticmethod
    def _event_cursor(item: object) -> int:
        if not isinstance(item, dict):
            return -1
        value = item.get("cursor")
        return int(value) if isinstance(value, int) else -1

    @staticmethod
    def _required_text(response: dict[str, Any], key: str) -> str:
        value = response.get(key)
        if not isinstance(value, str) or not value:
            raise DshProtocolError(f"DSH Runtime Host response is missing {key}")
        return value

    @staticmethod
    def _optional_text(response: dict[str, Any], key: str) -> str | None:
        value = response.get(key)
        if value is None:
            return None
        if not isinstance(value, str) or not value:
            raise DshProtocolError(f"DSH Runtime Profile contains invalid {key}")
        return value
