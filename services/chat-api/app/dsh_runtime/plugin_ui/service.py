"""Authorize and relay one plugin's browser surface into its DSH Runtime."""

from __future__ import annotations

from contextlib import suppress
import logging
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
import httpx

from app.dsh_runtime.profile.plugins import MongoPluginCatalog
from app.dsh_runtime.profile.service import RuntimeProfilePublisher
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator
from .backfill import backfill_browser_capabilities
from .tickets import PluginUiTicket, PluginUiTickets
from .surface import has_standalone_surface
from .history import hydrate_owned_history
from .session_navigation import resolve_owned_kernel_session


_REQUEST_HEADERS = {"accept", "accept-language", "content-type", "content-length",
                    "range", "if-none-match", "if-modified-since"}
_RESPONSE_HEADERS = {"content-type", "content-length", "content-encoding", "cache-control",
                     "etag", "last-modified", "content-range", "accept-ranges", "vary"}
logger = logging.getLogger(__name__)


class PluginUiService:
    def __init__(self, *, publisher: RuntimeProfilePublisher, coordinator: RuntimeCoordinator,
                 runtime_host_url: str, runtime_host_token: str, signing_secret: str) -> None:
        self._publisher = publisher
        self._coordinator = coordinator
        self._runtime_host_url = runtime_host_url.rstrip("/")
        self._runtime_host_token = runtime_host_token
        self.tickets = PluginUiTickets(signing_secret)
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(120.0), trust_env=False)

    def _host_headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self._runtime_host_token}"} if self._runtime_host_token else {}

    async def close(self) -> None:
        await self._http.aclose()

    @staticmethod
    async def _authorized_plugin(tenant_id: str, user_id: str, plugin_id: str,
                                 version: str | None = None,
                                 require_surface: bool = True) -> dict:
        plugins = await MongoPluginCatalog().list_enabled(tenant_id, user_id)
        plugin = next((item for item in plugins if item["installation_id"] == plugin_id), None)
        if plugin is None or (version is not None and plugin["version"] != version):
            raise HTTPException(status_code=403, detail="plugin_ui_access_denied")
        if not plugin.get("client_modules") or (require_surface and not has_standalone_surface(plugin)):
            raise HTTPException(status_code=409, detail="plugin_ui_unavailable")
        return plugin

    async def launch(self, *, tenant_id: str, user_id: str, plugin_id: str,
                     conversation_id: str | None = None) -> tuple[str, str | None]:
        plugin = await self._authorized_plugin(
            tenant_id, user_id, plugin_id, require_surface=False,
        )
        if conversation_id is None and not has_standalone_surface(plugin):
            try:
                await backfill_browser_capabilities(
                    tenant_id=tenant_id, user_id=user_id, plugin=plugin,
                )
            except Exception as exc:
                logger.exception("Plugin browser capability refresh failed", extra={
                    "tenant_id": tenant_id, "plugin_id": plugin_id,
                })
                raise HTTPException(status_code=503, detail="plugin_ui_runtime_unavailable") from exc
            plugin = await self._authorized_plugin(tenant_id, user_id, plugin_id)
        kernel_session_id = None
        if conversation_id is not None:
            from app.core.db import get_db
            kernel_session_id = await resolve_owned_kernel_session(
                get_db(), tenant_id=tenant_id, user_id=user_id,
                conversation_id=conversation_id,
            )
        profile = await self._publisher.publish_model_profile(
            tenant_id=tenant_id, actor_id=user_id, user_id=user_id, activate=False,
        )
        runtime = await self._coordinator.ensure_runtime(
            tenant_id=tenant_id, profile_version=profile.profile_version,
        )
        try:
            await hydrate_owned_history(
                http=self._http, host_url=self._runtime_host_url,
                headers=self._host_headers(), tenant_id=tenant_id,
                user_id=user_id, target_profile_version=profile.profile_version,
                runtime_id=runtime.runtime_id,
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="plugin_ui_history_unavailable") from exc
        try:
            inventory = await self._http.get(
                f"{self._runtime_host_url}/v1/runtimes/{quote(runtime.runtime_id, safe='')}/managed-plugins",
                headers=self._host_headers(),
            )
            inventory.raise_for_status()
            active = inventory.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="plugin_ui_runtime_unavailable") from exc
        if not any(bundle.get("name") == plugin["name"] and bundle.get("version") == plugin["version"]
                   and bundle.get("enabled") and not bundle.get("error")
                   for bundle in active.get("bundles") or []):
            raise HTTPException(status_code=409, detail="plugin_ui_runtime_not_active")
        ticket = self.tickets.issue(
            tenant_id=tenant_id, user_id=user_id, plugin_id=plugin_id,
            plugin_version=plugin["version"], profile_version=profile.profile_version,
            kernel_session_id=kernel_session_id,
        )
        return ticket, kernel_session_id

    async def proxy(self, ticket: PluginUiTicket, request: Request, path: str) -> StreamingResponse:
        await self._authorized_plugin(ticket.tenant_id, ticket.user_id,
                                      ticket.plugin_id, ticket.plugin_version,
                                      require_surface=False)
        runtime = await self._coordinator.ensure_runtime(
            tenant_id=ticket.tenant_id, profile_version=ticket.profile_version,
        )
        if request.method not in {"GET", "HEAD"}:
            await self._coordinator.refresh_runtime_credentials(runtime.runtime_id)
        suffix = f"/v1/runtimes/{quote(runtime.runtime_id, safe='')}/plugin-ui/{ticket.plugin_id}/{path}"
        if request.url.query:
            suffix += f"?{request.url.query}"
        headers = {name: value for name, value in request.headers.items()
                   if name in _REQUEST_HEADERS or (name.startswith("x-") and
                   not name.startswith("x-forwarded-") and name != "x-real-ip")}
        headers.update(self._host_headers())
        upstream = self._http.build_request(
            request.method, f"{self._runtime_host_url}{suffix}",
            headers=headers, content=request.stream(),
        )
        try:
            result = await self._http.send(upstream, stream=True)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="plugin_ui_runtime_unavailable") from exc

        async def close() -> None:
            with suppress(Exception):
                await result.aclose()

        return StreamingResponse(
            result.aiter_raw(), status_code=result.status_code,
            headers={name: value for name, value in result.headers.items()
                     if name in _RESPONSE_HEADERS},
            background=BackgroundTask(close),
        )
