"""Turn-boundary Runtime Profile synchronization for long-lived Conversations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.dsh_runtime.profile.service import RuntimeProfilePublisher
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator
from app.dsh_runtime.errors import DshSessionMissingError, DshTransportError

from .continuity import can_defer_profile_change


logger = logging.getLogger("app.dsh_runtime.profile_sync")


@dataclass(frozen=True)
class ProfileSyncResult:
    binding: dict[str, Any]
    changed: bool
    previous_profile_version: str
    profile_version: str
    previous_model_instance_id: str
    model_instance_id: str


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
        model_instance_id: str | None = None,
        selected_skill_id: str | None = None,
        selected_command_id: str | None = None,
    ) -> ProfileSyncResult:
        missing_session = False
        try:
            restored = await self._coordinator.restore(binding)
        except DshSessionMissingError:
            # The business conversation and messages remain durable even when
            # the host's separate session volume was lost. A missing host
            # session cannot seed a successor; replace only at a turn boundary.
            restored = binding
            missing_session = True
        previous_version = str(restored["profile_version"])
        previous_model_id = str(restored["model_instance_id"])
        desired_model_id = model_instance_id or previous_model_id
        desired = await self._profiles.compile_model_profile(
            tenant_id=tenant_id,
            user_id=user_id,
            model_instance_id=desired_model_id,
        )
        if desired.profile_version == previous_version and not missing_session:
            return ProfileSyncResult(
                binding=restored,
                changed=False,
                previous_profile_version=previous_version,
                profile_version=previous_version,
                previous_model_instance_id=previous_model_id,
                model_instance_id=previous_model_id,
            )

        logger.info(
            "conversation_profile_rotation_requested tenant_id=%s user_id=%s conversation_id=%s old=%s new=%s old_model=%s new_model=%s missing_host_session=%s",
            tenant_id, user_id, restored.get("conversation_id"), previous_version,
            desired.profile_version, previous_model_id, desired.model_instance_id, missing_session,
        )
        await self._profiles.publish_snapshot(desired, actor_id=user_id, activate=False)
        try:
            if missing_session:
                successor = await self._coordinator.replace_missing_binding(
                    restored,
                    profile_version=desired.profile_version,
                    model_instance_id=desired.model_instance_id,
                )
                disposed = False
            else:
                successor = await self._coordinator.rotate_binding(
                    restored,
                    profile_version=desired.profile_version,
                    model_instance_id=desired.model_instance_id,
                )
                disposed = await self._coordinator.dispose_restored_session(restored)
        except (DshTransportError, FileNotFoundError, OSError):
            if missing_session:
                raise
            previous = await self._profiles.get(previous_version)
            if not can_defer_profile_change(
                previous, desired, selected_skill_id=selected_skill_id,
                selected_command_id=selected_command_id,
            ):
                raise
            # Verify that the predecessor still exists before admitting the
            # turn. An unavailable Host must not be reported as a success.
            verified = await self._coordinator.restore(restored)
            logger.warning(
                "conversation_profile_rotation_deferred tenant_id=%s conversation_id=%s old=%s desired=%s",
                tenant_id, restored.get("conversation_id"), previous_version, desired.profile_version,
                exc_info=True,
            )
            return ProfileSyncResult(
                binding=verified,
                changed=False,
                previous_profile_version=previous_version,
                profile_version=previous_version,
                previous_model_instance_id=previous_model_id,
                model_instance_id=previous_model_id,
            )
        logger.info(
            "conversation_profile_rotated tenant_id=%s user_id=%s conversation_id=%s old=%s new=%s old_model=%s new_model=%s predecessor_disposed=%s missing_host_session=%s",
            tenant_id,
            user_id,
            restored.get("conversation_id"),
            previous_version,
            desired.profile_version,
            previous_model_id,
            desired.model_instance_id,
            disposed,
            missing_session,
        )
        return ProfileSyncResult(
            binding=successor,
            changed=True,
            previous_profile_version=previous_version,
            profile_version=desired.profile_version,
            previous_model_instance_id=previous_model_id,
            model_instance_id=desired.model_instance_id,
        )
