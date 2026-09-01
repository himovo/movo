from __future__ import annotations

import asyncio
from copy import deepcopy

from app.dsh_runtime.profile.compiler import ModelProfileCompiler
from app.dsh_runtime.profile.models import RuntimeProfileSnapshot
from app.dsh_runtime.profile.synchronizer import ConversationProfileSynchronizer
from app.dsh_runtime.profile.tools import ToolProfileCompiler
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
            _binding(), tenant_id="tenant-a", user_id="user-a",
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
    def __init__(self) -> None:
        self.allowed_tool_ids: tuple[str, ...] = ()

    async def resolve(self, tenant_id: str, user_id: str):
        return EffectiveEmployeePolicy(
            tenant_id=tenant_id,
            user_id=user_id,
            capabilities={key: True for key in CAPABILITY_KEYS},
            tool_access_mode="selected",
            tool_ids=frozenset(self.allowed_tool_ids),
        )


def test_role_tool_grant_and_revoke_change_the_desired_profile_for_same_user() -> None:
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

        policy.allowed_tool_ids = ("crm",)
        granted = await compiler.compile(
            tenant_id="tenant-a", user_id="user-a", model_instance_id="model-a",
        )
        assert granted.profile_version != denied.profile_version
        assert len(granted.tools) == 1
        assert granted.tools[0].external_tool_id == "crm"

        policy.allowed_tool_ids = ()
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
