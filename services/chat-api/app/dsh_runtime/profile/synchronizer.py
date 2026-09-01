"""Turn-boundary Runtime Profile synchronization for long-lived Conversations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.dsh_runtime.profile.service import RuntimeProfilePublisher
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator


logger = logging.getLogger("app.dsh_runtime.profile_sync")


@dataclass(frozen=True)
class ProfileSyncResult:
    binding: dict[str, Any]
    changed: bool
    previous_profile_version: str
    profile_version: str


class ConversationProfileSynchronizer:
    """Keep a Conversation stable while its immutable kernel snapshot evolves."""

    def __init__(
        self,
        profiles: RuntimeProfilePublisher,
        coordinator: RuntimeCoordinator,
    ) -> None:
        self._profiles = profiles
        self._coordinator = coordinator

    async def synchronize(
        self,
        binding: dict[str, Any],
        *,
        tenant_id: str,
        user_id: str,
    ) -> ProfileSyncResult:
        restored = await self._coordinator.restore(binding)
        previous_version = str(restored["profile_version"])
        desired = await self._profiles.compile_model_profile(
            tenant_id=tenant_id,
            user_id=user_id,
            model_instance_id=str(restored["model_instance_id"]),
        )
        if desired.profile_version == previous_version:
            return ProfileSyncResult(
                binding=restored,
                changed=False,
                previous_profile_version=previous_version,
                profile_version=previous_version,
            )

        await self._profiles.publish_snapshot(desired, actor_id=user_id, activate=False)
        successor = await self._coordinator.rotate_binding(
            restored,
            profile_version=desired.profile_version,
            model_instance_id=desired.model_instance_id,
        )
        disposed = await self._coordinator.dispose_restored_session(restored)
        logger.info(
            "conversation_profile_rotated tenant_id=%s user_id=%s conversation_id=%s old=%s new=%s predecessor_disposed=%s",
            tenant_id,
            user_id,
            restored.get("conversation_id"),
            previous_version,
            desired.profile_version,
            disposed,
        )
        return ProfileSyncResult(
            binding=successor,
            changed=True,
            previous_profile_version=previous_version,
            profile_version=desired.profile_version,
        )
