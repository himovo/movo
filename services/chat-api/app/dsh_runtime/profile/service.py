"""Control-plane use cases for compiling and governing Runtime Profiles."""

from __future__ import annotations

from .compiler import ModelProfileCompiler
from .models import RuntimeProfileSnapshot
from .store import RuntimeProfileStore


class RuntimeProfilePublisher:
    def __init__(self, compiler: ModelProfileCompiler, store: RuntimeProfileStore) -> None:
        self._compiler = compiler
        self._store = store

    async def publish_model_profile(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        user_id: str = "",
        model_instance_id: str | None = None,
        activate: bool = True,
    ) -> RuntimeProfileSnapshot:
        snapshot = await self._compiler.compile(
            tenant_id=tenant_id,
            user_id=user_id,
            model_instance_id=model_instance_id,
        )
        await self._store.publish(snapshot, actor_id=actor_id, activate=activate)
        return snapshot

    async def compile_model_profile(
        self,
        *,
        tenant_id: str,
        user_id: str = "",
        model_instance_id: str | None = None,
    ) -> RuntimeProfileSnapshot:
        """Compile the desired immutable snapshot without producing an audit row."""
        return await self._compiler.compile(
            tenant_id=tenant_id,
            user_id=user_id,
            model_instance_id=model_instance_id,
        )

    async def publish_snapshot(
        self,
        snapshot: RuntimeProfileSnapshot,
        *,
        actor_id: str,
        activate: bool = False,
    ) -> RuntimeProfileSnapshot:
        """Publish an already compiled snapshot after a caller detects change."""
        await self._store.publish(snapshot, actor_id=actor_id, activate=activate)
        return snapshot

    async def disable(self, profile_version: str, *, actor_id: str) -> None:
        await self._store.disable(profile_version, actor_id=actor_id)

    async def get(self, profile_version: str) -> RuntimeProfileSnapshot:
        return await self._store.get(profile_version)

    async def rollback(
        self,
        *,
        tenant_id: str,
        profile_version: str,
        actor_id: str,
    ) -> RuntimeProfileSnapshot:
        return await self._store.rollback(tenant_id, profile_version, actor_id=actor_id)
