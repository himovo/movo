from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from app.dsh_runtime.profile.compiler import ModelProfileCompiler
from app.dsh_runtime.profile.models import RuntimeProfileSnapshot
from app.dsh_runtime.profile.synchronizer import ConversationProfileSynchronizer
from app.dsh_runtime.errors import DshSessionMissingError, DshTransportError
from app.dsh_runtime.profile.tools import ToolProfileCompiler
from app.dsh_runtime.profile import tools as tools_module
from app.dsh_runtime.profile.skills import SkillProfileCompiler
from app.governance.position_policy import CAPABILITY_KEYS, EffectiveEmployeePolicy


def _profile(version: str, *, model: str = "model-a") -> RuntimeProfileSnapshot:
    return RuntimeProfileSnapshot(
        profile_version=version,
        content_hash=("a" if version == "rp-old" else "b") * 64,
        tenant_id="tenant-a",
        subject_user_id="user-a",
        model_source_tenant_id="tenant-a",
        model_instance_id=model,
        provider_id="provider-a",
        provider_type="openai_compatible",
        provider_name="provider",
        model_name="model",
        display_name="Model",
        capabilities=("chat",),
    )


class _Profiles:
    def __init__(self, desired: RuntimeProfileSnapshot) -> None:
        self.desired = desired
        self.published: list[str] = []

    async def compile_model_profile(self, **scope):
        assert scope == {
            "tenant_id": "tenant-a", "user_id": "user-a", "model_instance_id": "model-a",
        }
        return self.desired

    async def publish_snapshot(self, snapshot, **scope):
        assert scope == {"actor_id": "user-a", "activate": False}
        self.published.append(snapshot.profile_version)

    async def get(self, profile_version):
        assert profile_version == "rp-old"
        return _profile("rp-old")


class _Coordinator:
    def __init__(self) -> None:
        self.rotations: list[tuple[str, str]] = []
        self.disposed: list[str] = []

    async def restore(self, binding):
        return {**binding, "restored": True}

    async def rotate_binding(self, binding, *, profile_version, model_instance_id):
        self.rotations.append((profile_version, model_instance_id))
        return {
            **binding,
            "binding_id": "binding-new",
            "kernel_session_id": "session-new",
            "profile_version": profile_version,
            "model_instance_id": model_instance_id,
        }

    async def dispose_restored_session(self, binding):
        self.disposed.append(binding["kernel_session_id"])
        return True


def _binding() -> dict:
    return {
        "binding_id": "binding-old",
        "tenant_id": "tenant-a",
        "user_id": "user-a",
        "conversation_id": "conversation-a",
        "kernel_session_id": "session-old",
        "runtime_id": "runtime-old",
        "profile_version": "rp-old",
        "model_instance_id": "model-a",
    }


def test_unchanged_profile_resumes_without_rotation_or_publish_noise() -> None:
    async def run() -> None:
        profiles = _Profiles(_profile("rp-old"))
        coordinator = _Coordinator()
        result = await ConversationProfileSynchronizer(profiles, coordinator).synchronize(
            _binding(), tenant_id="tenant-a", user_id="user-a", model_instance_id="model-a",
        )
        assert result.changed is False
        assert result.binding["restored"] is True
        assert profiles.published == []
        assert coordinator.rotations == []
        assert coordinator.disposed == []

    asyncio.run(run())


def test_changed_profile_rotates_same_conversation_and_disposes_predecessor() -> None:
    async def run() -> None:
        profiles = _Profiles(_profile("rp-new"))
        coordinator = _Coordinator()
        result = await ConversationProfileSynchronizer(profiles, coordinator).synchronize(
            _binding(), tenant_id="tenant-a", user_id="user-a",
        )
        assert result.changed is True
        assert result.binding["conversation_id"] == "conversation-a"
        assert result.binding["profile_version"] == "rp-new"
        assert profiles.published == ["rp-new"]
        assert coordinator.rotations == [("rp-new", "model-a")]
        assert coordinator.disposed == ["session-old"]

    asyncio.run(run())


def test_missing_host_session_replaces_binding_without_seed() -> None:
    class MissingCoordinator(_Coordinator):
        def __init__(self) -> None:
            super().__init__()
            self.replacements: list[tuple[str, str]] = []

        async def restore(self, binding):
            raise DshSessionMissingError('session "dsh-lost" not found')

        async def replace_missing_binding(self, binding, *, profile_version, model_instance_id):
            self.replacements.append((profile_version, model_instance_id))
            return {**binding, "binding_id": "binding-new", "kernel_session_id": "session-new"}

    async def run() -> None:
        profiles = _Profiles(_profile("rp-old"))
        coordinator = MissingCoordinator()
        result = await ConversationProfileSynchronizer(profiles, coordinator).synchronize(
            _binding(), tenant_id="tenant-a", user_id="user-a",
        )
        assert result.binding["kernel_session_id"] == "session-new"
        assert coordinator.replacements == [("rp-old", "model-a")]
        assert coordinator.rotations == []
        assert coordinator.disposed == []

    asyncio.run(run())


def test_unavailable_host_does_not_replace_binding() -> None:
    class UnavailableCoordinator(_Coordinator):
        async def restore(self, binding):
            raise DshTransportError("DSH Runtime Host is unavailable")

    async def run() -> None:
        coordinator = UnavailableCoordinator()
        try:
            await ConversationProfileSynchronizer(_Profiles(_profile("rp-old")), coordinator).synchronize(
                _binding(), tenant_id="tenant-a", user_id="user-a",
            )
        except DshTransportError:
            pass
        else:
            assert False, "host outage must not reset conversation context"
        assert coordinator.rotations == []

    asyncio.run(run())


def test_additive_profile_change_can_wait_when_rotation_temporarily_fails() -> None:
    class FailingCoordinator(_Coordinator):
        async def rotate_binding(self, binding, *, profile_version, model_instance_id):
            self.rotations.append((profile_version, model_instance_id))
            raise DshTransportError("new Runtime is temporarily unavailable")

    async def run() -> None:
        profiles = _Profiles(_profile("rp-new"))
        coordinator = FailingCoordinator()
        result = await ConversationProfileSynchronizer(profiles, coordinator).synchronize(
            _binding(), tenant_id="tenant-a", user_id="user-a",
        )
        assert result.changed is False
        assert result.binding["kernel_session_id"] == "session-old"
        assert result.binding["restored"] is True
        assert coordinator.rotations == [("rp-new", "model-a")]
        assert coordinator.disposed == []

    asyncio.run(run())


def test_model_change_cannot_silently_reuse_previous_session() -> None:
    class FailingCoordinator(_Coordinator):
        async def rotate_binding(self, binding, *, profile_version, model_instance_id):
            raise DshTransportError("new Runtime is temporarily unavailable")

    class Profiles(_Profiles):
        async def compile_model_profile(self, **scope):
            return self.desired

    async def run() -> None:
        profiles = Profiles(_profile("rp-new", model="model-b"))
        with pytest.raises(DshTransportError):
            await ConversationProfileSynchronizer(profiles, FailingCoordinator()).synchronize(
                _binding(), tenant_id="tenant-a", user_id="user-a", model_instance_id="model-b",
            )

    asyncio.run(run())


def test_selected_new_skill_cannot_silently_use_old_profile() -> None:
    class FailingCoordinator(_Coordinator):
        async def rotate_binding(self, binding, *, profile_version, model_instance_id):
            raise FileNotFoundError("predecessor seed is unavailable")

    async def run() -> None:
        with pytest.raises(FileNotFoundError):
            await ConversationProfileSynchronizer(
                _Profiles(_profile("rp-new")), FailingCoordinator(),
            ).synchronize(
                _binding(), tenant_id="tenant-a", user_id="user-a",
                selected_skill_id="new-skill",
            )

    asyncio.run(run())


def test_revoked_plugin_cannot_continue_on_old_session_when_rotation_fails() -> None:
    plugin = {"installation_id": "a" * 24, "name": "example", "version": "1.0.0"}
    old = _profile("rp-old").model_copy(update={
        "plugins": (plugin,), "plugin_versions": ("example@1.0.0",),
    })

    class Profiles(_Profiles):
        async def get(self, profile_version):
            assert profile_version == "rp-old"
            return old

    class FailingCoordinator(_Coordinator):
        async def rotate_binding(self, binding, *, profile_version, model_instance_id):
            raise DshTransportError("new Runtime is temporarily unavailable")

    async def run() -> None:
        with pytest.raises(DshTransportError):
            await ConversationProfileSynchronizer(
                Profiles(_profile("rp-new")), FailingCoordinator(),
            ).synchronize(_binding(), tenant_id="tenant-a", user_id="user-a")

    asyncio.run(run())


def test_missing_binding_replacement_does_not_seed_from_lost_session() -> None:
    from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator

    class RecordingCoordinator(RuntimeCoordinator):
        def __init__(self) -> None:
            self.calls = []

        async def create_binding(self, **kwargs):
            self.calls.append(kwargs)
            return kwargs

    async def run() -> None:
        coordinator = RecordingCoordinator()
        await coordinator.replace_missing_binding(
            {**_binding(), "speaker_user_id": "user-b", "speaker_preset_id": "askai-enterprise"},
            profile_version="rp-new",
            model_instance_id="model-b",
        )
        call = coordinator.calls[0]
        assert call["replaces_binding_id"] == "binding-old"
        assert call["conversation_id"] == "conversation-a"
        assert call["user_id"] == "user-b"
        assert call["seed_runtime_id"] is None
        assert call["seed_session_id"] is None

    asyncio.run(run())


def test_each_turn_can_rotate_the_same_conversation_to_the_requested_model() -> None:
    class SelectableProfiles:
        def __init__(self) -> None:
            self.published: list[str] = []

        async def compile_model_profile(self, **scope):
            model_id = scope["model_instance_id"]
            return _profile(f"rp-{model_id}", model=model_id)

        async def publish_snapshot(self, snapshot, **_scope):
            self.published.append(snapshot.profile_version)

    async def run() -> None:
        profiles = SelectableProfiles()
        coordinator = _Coordinator()
        synchronizer = ConversationProfileSynchronizer(profiles, coordinator)

        model_b = await synchronizer.synchronize(
            _binding(), tenant_id="tenant-a", user_id="user-a", model_instance_id="model-b",
        )
        assert model_b.binding["conversation_id"] == "conversation-a"
        assert model_b.binding["model_instance_id"] == "model-b"
        assert model_b.previous_model_instance_id == "model-a"
        assert model_b.model_instance_id == "model-b"

        model_a = await synchronizer.synchronize(
            model_b.binding, tenant_id="tenant-a", user_id="user-a", model_instance_id="model-a",
        )
        assert model_a.binding["conversation_id"] == "conversation-a"
        assert model_a.binding["model_instance_id"] == "model-a"
        assert model_a.previous_model_instance_id == "model-b"
        assert model_a.model_instance_id == "model-a"
        assert coordinator.rotations == [("rp-model-b", "model-b"), ("rp-model-a", "model-a")]
        assert coordinator.disposed == ["session-old", "session-new"]
        assert profiles.published == ["rp-model-b", "rp-model-a"]

    asyncio.run(run())


class _ModelCatalog:
    async def resolve(self, tenant_id: str, model_instance_id: str | None):
        return (
            {
                "_id": model_instance_id or "model-a",
                "main_id": tenant_id,
                "provider_id": "provider-a",
                "model_name": "deepseek-chat",
                "display_name": "DeepSeek",
                "status": "active",
                "capabilities": ["chat", "tools"],
            },
            {
                "_id": "provider-a",
                "name": "provider",
                "provider_type": "openai_compatible",
                "status": "active",
            },
        )


class _CrmCatalog:
    async def list_enabled(self, tenant_id: str, user_id: str):
        assert (tenant_id, user_id) == ("tenant-a", "user-a")
        return deepcopy([{
            "id": "crm",
            "name": "CRM",
            "type": "mcp",
            "description": "Enterprise CRM",
            "config": {},
            "discoveredTools": [{
                "name": "search_customers",
                "description": "Search customers",
                "inputSchema": {"type": "object", "properties": {}},
                "annotations": {"readOnlyHint": True},
            }],
        }])


class _MutablePolicyResolver:
    async def resolve(self, tenant_id: str, user_id: str):
        return EffectiveEmployeePolicy(
            tenant_id=tenant_id,
            user_id=user_id,
            capabilities={key: True for key in CAPABILITY_KEYS},
        )


def test_resource_tool_grant_and_revoke_change_the_desired_profile_for_same_user(monkeypatch) -> None:
    allowed_tool_ids: set[str] = set()

    async def filter_ids(_resource_type, *, resource_ids, **_scope):
        return set(resource_ids).intersection(allowed_tool_ids)

    monkeypatch.setattr(tools_module, "filter_allowed_resource_ids", filter_ids)

    async def run() -> None:
        policy = _MutablePolicyResolver()
        compiler = ModelProfileCompiler(
            _ModelCatalog(),
            ToolProfileCompiler(_CrmCatalog(), policy_resolver=policy),
        )

        denied = await compiler.compile(
            tenant_id="tenant-a", user_id="user-a", model_instance_id="model-a",
        )
        assert denied.tools == ()

        allowed_tool_ids.add("crm")
        granted = await compiler.compile(
            tenant_id="tenant-a", user_id="user-a", model_instance_id="model-a",
        )
        assert granted.profile_version != denied.profile_version
        assert len(granted.tools) == 1
        assert granted.tools[0].external_tool_id == "crm"

        allowed_tool_ids.clear()
        revoked = await compiler.compile(
            tenant_id="tenant-a", user_id="user-a", model_instance_id="model-a",
        )
        assert revoked.profile_version == denied.profile_version
        assert revoked.tools == ()

    asyncio.run(run())


class _MutableSkillCatalog:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def list_enabled(self, tenant_id: str, user_id: str):
        return deepcopy(self.rows)


def test_skill_publish_update_and_disable_rotate_the_same_conversation_profile() -> None:
    async def run() -> None:
        catalog = _MutableSkillCatalog()
        compiler = ModelProfileCompiler(
            _ModelCatalog(), skill_compiler=SkillProfileCompiler(catalog),
        )
        initial = await compiler.compile(tenant_id="tenant-a", user_id="user-a", model_instance_id="model-a")
        catalog.rows = [{
            "id": "skill-1", "name": "访谈分析", "description": "分析访谈",
            "skill_type": "execution", "skill_markdown": "提取事实与待办。",
        }]
        published = await compiler.compile(tenant_id="tenant-a", user_id="user-a", model_instance_id="model-a")
        assert published.profile_version != initial.profile_version
        assert len(published.skills) == 1
        catalog.rows[0]["skill_markdown"] = "提取事实、风险与待办。"
        updated = await compiler.compile(tenant_id="tenant-a", user_id="user-a", model_instance_id="model-a")
        assert updated.profile_version not in {initial.profile_version, published.profile_version}
        catalog.rows = []
        disabled = await compiler.compile(tenant_id="tenant-a", user_id="user-a", model_instance_id="model-a")
        assert disabled.profile_version == initial.profile_version
        assert disabled.skills == ()

    asyncio.run(run())
