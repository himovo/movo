"""Resolve a published profile into an ephemeral Host binding."""

from __future__ import annotations

from app.dsh_runtime.model_gateway.token import ModelGatewayTokenService
from app.dsh_runtime.tool_gateway.token import ToolGatewayTokenService

from .store import RuntimeProfileStore


class RuntimeProfileResolver:
    def __init__(
        self,
        store: RuntimeProfileStore,
        token_service: ModelGatewayTokenService,
        *,
        gateway_url: str,
        tool_token_service: ToolGatewayTokenService | None = None,
        tool_gateway_url: str = "",
    ) -> None:
        self._store = store
        self._tokens = token_service
        self._gateway_url = gateway_url
        self._tool_tokens = tool_token_service
        self._tool_gateway_url = tool_gateway_url

    async def resolve(self, profile_version: str, *, tenant_id: str | None = None) -> dict[str, object]:
        snapshot = await self._store.get(profile_version)
        if tenant_id is not None and snapshot.tenant_id != tenant_id:
            raise ValueError("cross-tenant Runtime Profile access is forbidden")
        token = self._tokens.issue(
            tenant_id=snapshot.tenant_id,
            profile_version=snapshot.profile_version,
            model_instance_id=snapshot.model_instance_id,
        )
        tool_token = ""
        if snapshot.tools:
            if self._tool_tokens is None or not self._tool_gateway_url:
                raise ValueError("Tool-enabled Runtime Profile has no Tool Gateway binding")
            tool_token = self._tool_tokens.issue(
                tenant_id=snapshot.tenant_id,
                user_id=snapshot.subject_user_id,
                profile_version=snapshot.profile_version,
                tool_names=[tool.name for tool in snapshot.tools],
                scopes=sorted({scope for tool in snapshot.tools for scope in tool.required_scopes}),
            )
        return snapshot.host_payload(
            gateway_url=self._gateway_url,
            access_token=token,
            tool_gateway_url=self._tool_gateway_url,
            tool_access_token=tool_token,
        )
