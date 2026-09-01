"""Atomic immutable ASKAI binding for a Session already created by Desktop DSH."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.profile.service import RuntimeProfilePublisher


@dataclass(frozen=True)
class DesktopSessionIdentity:
    runtime_id: str
    kernel_session_id: str
    dsh_workspace_id: str
    profile_version: str
    model_instance_id: str
    device_id: str
    source_workspace_id: str
    git_branch: str | None = None
    source_ref: str | None = None
    base_commit: str | None = None
    detached_head: bool = False
    execution_mode: str = "local"
    worktree: bool = False


class DesktopCodeBindingService:
    """Commits all execution identity fields together; never accepts a filesystem path."""

    def __init__(
        self,
        conversations: ConversationRepository,
        bindings: KernelBindingRepository,
        profiles: RuntimeProfilePublisher,
        *,
        kernel_version: str,
    ) -> None:
        self._conversations = conversations
        self._bindings = bindings
        self._profiles = profiles
        self._kernel_version = kernel_version

    async def commit(
        self,
        *,
        tenant_id: str,
        user_id: str,
        identity: DesktopSessionIdentity,
        title: str,
    ) -> dict[str, Any]:
        existing = await self._bindings.by_kernel_session(
            identity.kernel_session_id, tenant_id=tenant_id, user_id=user_id
        )
        if existing is not None:
            self._assert_same(existing, identity)
            return existing

        profile = await self._profiles.get(identity.profile_version)
        if (
            profile.tenant_id != tenant_id
            or profile.subject_user_id != user_id
            or profile.model_instance_id != identity.model_instance_id
        ):
            raise ValueError("desktop Session does not match its published Runtime Profile")
        conversation = await self._conversations.create(
            tenant_id=tenant_id,
            user_id=user_id,
            title=title.strip()[:120] or "Code task",
        )
        conversation_id = str(conversation["_id"])
        try:
            return await self._bindings.create(
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
                kernel_session_id=identity.kernel_session_id,
                runtime_id=identity.runtime_id,
                profile_version=identity.profile_version,
                model_instance_id=identity.model_instance_id,
                kernel_version=self._kernel_version,
                preset_id="code",
                execution_location="desktop",
                dsh_workspace_id=identity.dsh_workspace_id,
                device_id=identity.device_id,
                source_workspace_id=identity.source_workspace_id,
                git_branch=identity.git_branch,
                source_ref=identity.source_ref,
                base_commit=identity.base_commit,
                detached_head=identity.detached_head,
                execution_mode=identity.execution_mode,
                worktree=identity.worktree,
            )
        except Exception:
            await self._conversations.delete_if_empty(
                conversation_id, tenant_id=tenant_id, user_id=user_id
            )
            raise

    async def resolve(
        self, *, tenant_id: str, user_id: str, device_id: str, conversation_id: str,
    ) -> dict[str, Any] | None:
        binding = await self._bindings.current(
            conversation_id, tenant_id=tenant_id, user_id=user_id
        )
        if binding is None or str(binding.get("execution_location") or "") != "desktop":
            return None
        if str(binding.get("device_id") or "") != device_id:
            raise ValueError("Code Session belongs to another desktop device")
        return binding

    async def rebind_runtime(
        self, *, tenant_id: str, user_id: str, device_id: str,
        conversation_id: str, profile_version: str, runtime_id: str,
    ) -> None:
        binding = await self.resolve(
            tenant_id=tenant_id, user_id=user_id, device_id=device_id,
            conversation_id=conversation_id,
        )
        if binding is None:
            raise LookupError("desktop_code_session_not_found")
        if str(binding.get("profile_version") or "") != profile_version:
            raise ValueError("Runtime Profile changed; Code Session cannot be resumed")
        await self._bindings.update_runtime(str(binding["binding_id"]), runtime_id=runtime_id)

    async def update_git_state(
        self, *, tenant_id: str, user_id: str, device_id: str,
        kernel_session_id: str, git_branch: str, head_commit: str,
    ) -> None:
        binding = await self._owned_binding(
            tenant_id=tenant_id, user_id=user_id, device_id=device_id,
            kernel_session_id=kernel_session_id,
        )
        await self._bindings.update_git_state(
            str(binding["binding_id"]), git_branch=git_branch, head_commit=head_commit,
        )

    async def start_turn(
        self, *, tenant_id: str, user_id: str, device_id: str,
        kernel_session_id: str, text: str, message_id: str,
    ) -> dict[str, Any]:
        binding = await self._owned_binding(
            tenant_id=tenant_id, user_id=user_id, device_id=device_id,
            kernel_session_id=kernel_session_id,
        )
        request_id = f"desktop-turn-{uuid4()}"
        claimed = await self._bindings.claim_turn(
            str(binding["binding_id"]), message_id=message_id, request_id=request_id,
            turn_metadata={"source": "desktop_dsh_code"},
        )
        if claimed is None:
            raise ValueError("another Code turn is already running")
        conversation_id = str(binding["conversation_id"])
        try:
            await self._conversations.append_message(
                conversation_id=conversation_id, tenant_id=tenant_id, user_id=user_id,
                role="user", content=text, message_id=f"user-{message_id}",
            )
            await self._conversations.append_message(
                conversation_id=conversation_id, tenant_id=tenant_id, user_id=user_id,
                role="assistant", content="", message_id=message_id,
            )
            await self._conversations.mark_active_run(
                conversation_id=conversation_id, tenant_id=tenant_id, user_id=user_id,
                message_id=message_id, run_id=request_id,
            )
        except Exception:
            await self._bindings.finish_turn(
                str(binding["binding_id"]), message_id=message_id, status="failed"
            )
            raise
        return {"conversation_id": conversation_id, "message_id": message_id}

    async def project_events(
        self, *, tenant_id: str, user_id: str, device_id: str,
        kernel_session_id: str, message_id: str, events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        binding = await self._owned_binding(
            tenant_id=tenant_id, user_id=user_id, device_id=device_id,
            kernel_session_id=kernel_session_id,
        )
        active = dict(binding.get("active_turn") or {})
        if str(active.get("message_id") or "") != message_id:
            raise ValueError("desktop projection does not match the active Code turn")
        current = await self._conversations.message(
            message_id, tenant_id=tenant_id, user_id=user_id
        )
        if current is None:
            raise LookupError("assistant_message_not_found")
        merged = self._merge_events(list(current.get("execution_events") or []), events)
        content = self._final_content(merged)
        await self._conversations.update_assistant_projection(
            message_id=message_id, tenant_id=tenant_id, user_id=user_id,
            content=content, execution_events=merged,
        )
        approval_state: dict[str, bool] = {}
        for event in merged:
            if event.get("item_kind") != "approval" or not event.get("item_id"):
                continue
            approval_state[str(event["item_id"])] = event.get("type") == "item.started"
        await self._conversations.set_pending_approval_count(
            conversation_id=str(binding["conversation_id"]), tenant_id=tenant_id,
            user_id=user_id, count=sum(1 for pending in approval_state.values() if pending),
        )
        cursor = max((int(event.get("stream_seq_end") or event.get("stream_seq") or 0) for event in merged), default=0)
        await self._bindings.advance_cursor(str(binding["binding_id"]), cursor)
        terminal = next((event for event in reversed(merged) if event.get("type") in {
            "run.completed", "run.failed", "run.cancelled"
        }), None)
        if terminal is not None:
            status = {"run.completed": "completed", "run.failed": "failed", "run.cancelled": "cancelled"}[str(terminal["type"])]
            await self._bindings.finish_turn(str(binding["binding_id"]), message_id=message_id, status=status)
            await self._conversations.clear_active_run(
                conversation_id=str(binding["conversation_id"]), tenant_id=tenant_id,
                user_id=user_id, message_id=message_id,
            )
        return {"cursor": cursor, "terminal": terminal is not None}

    async def _owned_binding(
        self, *, tenant_id: str, user_id: str, device_id: str, kernel_session_id: str,
    ) -> dict[str, Any]:
        binding = await self._bindings.by_kernel_session(
            kernel_session_id, tenant_id=tenant_id, user_id=user_id
        )
        if binding is None or str(binding.get("execution_location")) != "desktop":
            raise LookupError("desktop_code_session_not_found")
        if str(binding.get("device_id") or "") != device_id:
            raise ValueError("Code Session belongs to another desktop device")
        return binding

    @staticmethod
    def _merge_events(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {str(event.get("event_id") or event.get("id") or ""): dict(event) for event in existing}
        for event in incoming:
            event_id = str(event.get("event_id") or event.get("id") or "")
            if event_id:
                by_id[event_id] = dict(event)
        return sorted(by_id.values(), key=lambda event: (
            int(event.get("stream_seq") or 0), int(event.get("ts") or 0), str(event.get("event_id") or "")
        ))[-20_000:]

    @staticmethod
    def _final_content(events: list[dict[str, Any]]) -> str:
        completed = [
            str((event.get("payload") or {}).get("text") or "")
            for event in events
            if event.get("type") == "item.completed" and event.get("item_kind") == "final_answer"
        ]
        if completed:
            return completed[-1]
        return "".join(
            str((event.get("payload") or {}).get("text") or "")
            for event in events
            if event.get("type") == "item.delta" and event.get("item_kind") == "final_answer"
        )

    @staticmethod
    def _assert_same(binding: dict[str, Any], identity: DesktopSessionIdentity) -> None:
        expected = {
            "runtime_id": identity.runtime_id,
            "kernel_session_id": identity.kernel_session_id,
            "dsh_workspace_id": identity.dsh_workspace_id,
            "profile_version": identity.profile_version,
            "model_instance_id": identity.model_instance_id,
            "device_id": identity.device_id,
            "preset_id": "code",
            "execution_location": "desktop",
            "source_workspace_id": identity.source_workspace_id,
            "git_branch": identity.git_branch or "",
            "source_ref": identity.source_ref or "",
            "base_commit": identity.base_commit or "",
            "detached_head": "True" if identity.detached_head else "False",
            "execution_mode": identity.execution_mode,
            "worktree": "True" if identity.worktree else "False",
        }
        bool_fields = {"worktree", "detached_head"}
        legacy_defaults = {
            "detached_head": False,
            "execution_mode": "worktree" if bool(binding.get("worktree")) else "local",
        }
        def normalized(key: str) -> str:
            value = binding.get(key, legacy_defaults.get(key))
            return str(value if key in bool_fields else value or "")
        if any(normalized(key) != value for key, value in expected.items()):
            raise ValueError("kernel Session is already bound with another immutable identity")
