"""Authenticated control-plane bootstrap for an ASKAI Desktop DSH Runtime."""

from __future__ import annotations

from dataclasses import dataclass

from app.dsh_runtime.profile.resolver import RuntimeProfileResolver
from app.dsh_runtime.profile.service import RuntimeProfilePublisher


@dataclass(frozen=True)
class DesktopRuntimeBootstrap:
    profile_version: str
    model_instance_id: str
    model_profile: dict[str, object]


class DesktopRuntimeBootstrapService:
    """Publishes one immutable user profile and leases its short-lived Host credentials."""

    def __init__(self, publisher: RuntimeProfilePublisher, resolver: RuntimeProfileResolver) -> None:
        self._publisher = publisher
        self._resolver = resolver

    async def prepare(
        self,
        *,
        tenant_id: str,
        user_id: str,
        model_instance_id: str | None,
    ) -> DesktopRuntimeBootstrap:
        snapshot = await self._publisher.publish_model_profile(
            tenant_id=tenant_id,
            actor_id=user_id,
            user_id=user_id,
            model_instance_id=model_instance_id,
            activate=False,
        )
        host_profile = await self._resolver.resolve(snapshot.profile_version, tenant_id=tenant_id)
        return DesktopRuntimeBootstrap(
            profile_version=snapshot.profile_version,
            model_instance_id=snapshot.model_instance_id,
            model_profile=host_profile,
        )
