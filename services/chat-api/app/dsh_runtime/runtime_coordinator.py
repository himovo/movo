"""Recoverable Runtime/Session coordination above the DSH gateway."""

from __future__ import annotations

from typing import Any

from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.contracts import CreateRuntimeRequest, CreateSessionRequest, SessionSpec
from app.dsh_runtime.errors import DshRuntimeError
from app.dsh_runtime.gateway import DshAgentKernelGateway


class RuntimeCoordinator:
    def __init__(self, gateway: DshAgentKernelGateway, bindings: KernelBindingRepository) -> None:
        self._gateway = gateway
        self._bindings = bindings

    @staticmethod
    def isolation_key(tenant_id: str, profile_version: str) -> str:
        return f"tenant:{tenant_id}:profile:{profile_version}"

    async def create_binding(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        profile_version: str,
        model_instance_id: str,
        preset_id: str = "askai-enterprise",
        execution_location: str = "server",
        workspace_id: str | None = None,
        device_id: str | None = None,
        source_workspace_id: str | None = None,
        git_branch: str | None = None,
        source_ref: str | None = None,
        base_commit: str | None = None,
        detached_head: bool = False,
        execution_mode: str | None = None,
        worktree: bool = False,
        replaces_binding_id: str | None = None,
        seed_runtime_id: str | None = None,
        seed_session_id: str | None = None,
    ) -> dict[str, Any]:
        runtime = await self._runtime(tenant_id=tenant_id, profile_version=profile_version)
        session = await self._gateway.create_session(
            CreateSessionRequest(
                runtime_id=runtime.runtime_id,
                session_spec=SessionSpec(
                    conversation_id=conversation_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    profile_version=profile_version,
                    preset_id=preset_id,
                    execution_location=execution_location,
                    workspace_id=workspace_id,
                    seed_runtime_id=seed_runtime_id,
                    seed_session_id=seed_session_id,
                ),
            )
        )
        try:
            return await self._bindings.create(
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
                kernel_session_id=session.session_id,
                runtime_id=runtime.runtime_id,
                profile_version=profile_version,
                model_instance_id=model_instance_id,
                kernel_version=runtime.kernel_version,
                preset_id=preset_id,
                execution_location=execution_location,
                dsh_workspace_id=workspace_id,
                device_id=device_id,
                source_workspace_id=source_workspace_id,
                git_branch=git_branch,
                source_ref=source_ref,
                base_commit=base_commit,
                detached_head=detached_head,
                execution_mode=execution_mode,
                worktree=worktree,
                replaces_binding_id=replaces_binding_id,
            )
        except Exception:
            await self._gateway.dispose_session(session.session_id)
            raise

    async def rotate_binding(
        self,
        binding: dict[str, Any],
        *,
        profile_version: str,
        model_instance_id: str,
    ) -> dict[str, Any]:
        """Create a successor Session seeded from the completed predecessor."""
        return await self.create_binding(
            tenant_id=str(binding["tenant_id"]),
            user_id=str(binding["user_id"]),
            conversation_id=str(binding["conversation_id"]),
            profile_version=profile_version,
            model_instance_id=model_instance_id,
            preset_id=str(binding.get("preset_id") or "askai-enterprise"),
            execution_location=str(binding.get("execution_location") or "server"),
            workspace_id=str(binding.get("dsh_workspace_id") or "") or None,
            device_id=str(binding.get("device_id") or "") or None,
            source_workspace_id=str(binding.get("source_workspace_id") or "") or None,
            git_branch=str(binding.get("git_branch") or "") or None,
            source_ref=str(binding.get("source_ref") or "") or None,
            base_commit=str(binding.get("base_commit") or "") or None,
            detached_head=bool(binding.get("detached_head")),
            execution_mode=str(binding.get("execution_mode") or "") or None,
            worktree=bool(binding.get("worktree")),
            replaces_binding_id=str(binding["binding_id"]),
            seed_runtime_id=str(binding["runtime_id"]),
            seed_session_id=str(binding["kernel_session_id"]),
        )

    async def dispose_restored_session(self, binding: dict[str, Any]) -> bool:
        """Best-effort cleanup after a successor has durably copied the seed."""
        try:
            await self._gateway.dispose_session(str(binding["kernel_session_id"]))
        except DshRuntimeError:
            return False
        return True

    async def restore(self, binding: dict[str, Any]) -> dict[str, Any]:
        tenant_id = str(binding["tenant_id"])
        profile_version = str(binding["profile_version"])
        runtime = await self._runtime(tenant_id=tenant_id, profile_version=profile_version)
        session_id = str(binding["kernel_session_id"])
        self._gateway.attach_session(
            runtime_id=runtime.runtime_id,
            session_id=session_id,
            conversation_id=str(binding["conversation_id"]),
            profile_version=profile_version,
            model_instance_id=str(binding["model_instance_id"]),
            preset_id=str(binding.get("preset_id") or "askai-enterprise"),
            workspace_id=str(binding.get("dsh_workspace_id") or "") or None,
        )
        await self._gateway.resume_session(session_id)
        if str(binding.get("runtime_id")) != runtime.runtime_id:
            await self._bindings.update_runtime(str(binding["binding_id"]), runtime_id=runtime.runtime_id)
            binding = {**binding, "runtime_id": runtime.runtime_id}
        return binding

    async def _runtime(self, *, tenant_id: str, profile_version: str):
        isolation_key = self.isolation_key(tenant_id, profile_version)
        runtime = await self._gateway.discover_runtime(
            tenant_id=tenant_id,
            profile_version=profile_version,
            isolation_key=isolation_key,
        )
        if runtime is not None:
            return runtime
        try:
            return await self._gateway.create_runtime(
                CreateRuntimeRequest(
                    tenant_id=tenant_id,
                    profile_version=profile_version,
                    isolation_key=isolation_key,
                )
            )
        except DshRuntimeError:
            concurrent = await self._gateway.discover_runtime(
                tenant_id=tenant_id,
                profile_version=profile_version,
                isolation_key=isolation_key,
            )
            if concurrent is not None:
                return concurrent
            raise
