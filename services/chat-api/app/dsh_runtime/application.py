"""Process-local composition root for the DSH runtime boundary."""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.core.db import get_db
from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.chat_service import DshChatService
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.events import KernelEventRepository
from app.dsh_runtime.events.turn_channel import TurnEventRegistry
from app.dsh_runtime.errors import DshRuntimeError
from app.dsh_runtime.gateway import DshAgentKernelGateway
from app.dsh_runtime.model_gateway.token import ModelGatewayTokenService
from app.dsh_runtime.tool_gateway.token import ToolGatewayTokenService
from app.dsh_runtime.profile.catalog import MongoModelCatalog
from app.dsh_runtime.profile.compiler import ModelProfileCompiler
from app.dsh_runtime.profile.tools import MongoToolCatalog, ToolProfileCompiler
from app.dsh_runtime.profile.skills import MongoSkillCatalog, SkillProfileCompiler
from app.dsh_runtime.profile.resolver import RuntimeProfileResolver
from app.dsh_runtime.profile.service import RuntimeProfilePublisher
from app.dsh_runtime.profile.store import MongoRuntimeProfileStore
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator
from app.dsh_runtime.desktop_bootstrap import DesktopRuntimeBootstrapService
from app.dsh_runtime.desktop_binding import DesktopCodeBindingService
from app.dsh_runtime.transport import HttpKernelHostTransport
from app.enterprise_capabilities.tools import EnterpriseToolRepository, EnterpriseToolService
from app.enterprise_capabilities.evidence import ExecutionEvidenceRepository
from app.enterprise_capabilities.delivery import AuthoritativeDeliveryRepository
from app.enterprise_capabilities.runtime import InternalCapabilityCatalog, InternalCapabilityService
from app.enterprise_capabilities.runtime.adapters import build_default_registry
from app.governance.position_policy import MongoEmployeePolicyResolver
from app.services.presentation.execution import PresentationJobRepository


class DshRuntimeApplication:
    KERNEL_VERSION = "0.1.0-rc.6"

    def __init__(self) -> None:
        self._transport: HttpKernelHostTransport | None = None
        self.chat: DshChatService | None = None
        self.tools: EnterpriseToolService | None = None
        self.desktop_bootstrap: DesktopRuntimeBootstrapService | None = None
        self.desktop_bindings: DesktopCodeBindingService | None = None
        self.host_healthy = False

    async def start(self) -> None:
        settings = get_settings()
        db = get_db()
        secret = str(settings.DSH_MODEL_GATEWAY_SIGNING_SECRET or settings.ASKAI_ADMIN_JWT_SECRET or "")
        store = MongoRuntimeProfileStore()
        resolver = RuntimeProfileResolver(
            store,
            ModelGatewayTokenService(secret),
            gateway_url=settings.DSH_MODEL_GATEWAY_URL,
            tool_token_service=ToolGatewayTokenService(secret),
            tool_gateway_url=settings.DSH_TOOL_GATEWAY_URL,
        )
        self._transport = HttpKernelHostTransport(
            settings.DSH_RUNTIME_HOST_URL,
            timeout_seconds=settings.DSH_RUNTIME_HTTP_TIMEOUT_SECONDS,
            access_token=settings.DSH_RUNTIME_HOST_TOKEN,
        )
        try:
            health = await self._transport.request("GET", "/health")
            self.host_healthy = health.get("ok") is True and health.get("kernel") == "dsh"
        except DshRuntimeError:
            self.host_healthy = False
        gateway = DshAgentKernelGateway(
            self._transport,
            kernel_version=self.KERNEL_VERSION,
            profile_resolver=resolver,
        )
        conversations = ConversationRepository(db)
        bindings = KernelBindingRepository(db)
        events = KernelEventRepository(db)
        turn_events = TurnEventRegistry(events)
        tool_repository = EnterpriseToolRepository()
        presentation_jobs = PresentationJobRepository()
        internal_catalog = InternalCapabilityCatalog()
        employee_policy = MongoEmployeePolicyResolver()
        internal_capabilities = InternalCapabilityService(build_default_registry())
        await store.ensure_indexes()
        await conversations.ensure_indexes()
        await bindings.ensure_indexes()
        await events.ensure_indexes()
        await tool_repository.ensure_indexes()
        await presentation_jobs.ensure_indexes()
        await presentation_jobs.recover_running()
        execution_evidence = ExecutionEvidenceRepository()
        authoritative_deliveries = AuthoritativeDeliveryRepository()
        await authoritative_deliveries.ensure_indexes()
        self.tools = EnterpriseToolService(
            tool_repository,
            store,
            internal_capabilities,
            turn_events=turn_events,
            execution_evidence=execution_evidence,
            authoritative_deliveries=authoritative_deliveries,
            employee_policy=employee_policy,
            presentation_jobs=presentation_jobs,
        )
        publisher = RuntimeProfilePublisher(
            ModelProfileCompiler(
                MongoModelCatalog(),
                ToolProfileCompiler(MongoToolCatalog(), internal_catalog, employee_policy),
                SkillProfileCompiler(MongoSkillCatalog(employee_policy)),
            ),
            store,
        )
        self.desktop_bootstrap = DesktopRuntimeBootstrapService(publisher, resolver)
        self.desktop_bindings = DesktopCodeBindingService(
            conversations, bindings, publisher, kernel_version=self.KERNEL_VERSION
        )
        self.chat = DshChatService(
            gateway=gateway,
            coordinator=RuntimeCoordinator(gateway, bindings),
            conversations=conversations,
            bindings=bindings,
            events=events,
            profiles=publisher,
            kernel_version=self.KERNEL_VERSION,
            turn_events=turn_events,
            execution_evidence=execution_evidence,
            authoritative_deliveries=authoritative_deliveries,
        )

    async def stop(self) -> None:
        if self.chat is not None:
            await self.chat.shutdown()
        if self._transport is not None:
            await self._transport.close()
        self.chat = None
        self.tools = None
        self.desktop_bootstrap = None
        self.desktop_bindings = None
        self._transport = None
        self.host_healthy = False

    async def probe_host(self) -> bool:
        if self._transport is None:
            self.host_healthy = False
            return False
        try:
            health = await self._transport.request("GET", "/health")
            self.host_healthy = health.get("ok") is True and health.get("kernel") == "dsh"
        except DshRuntimeError:
            self.host_healthy = False
        return self.host_healthy

    def require_chat(self) -> DshChatService:
        if self.chat is None:
            raise RuntimeError("DSH Runtime Application is not started")
        return self.chat

    def require_tools(self) -> EnterpriseToolService:
        if self.tools is None:
            raise RuntimeError("DSH Tool Gateway is not started")
        return self.tools

    def require_desktop_bootstrap(self) -> DesktopRuntimeBootstrapService:
        if self.desktop_bootstrap is None:
            raise RuntimeError("DSH Desktop bootstrap service is not started")
        return self.desktop_bootstrap

    def require_desktop_bindings(self) -> DesktopCodeBindingService:
        if self.desktop_bindings is None:
            raise RuntimeError("DSH Desktop binding service is not started")
        return self.desktop_bindings


dsh_runtime_application = DshRuntimeApplication()
