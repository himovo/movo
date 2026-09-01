from __future__ import annotations

import asyncio

from app.dsh_runtime.profile.tools import ToolProfileCompiler
from app.enterprise_capabilities.runtime import InternalCapabilityCatalog
from app.governance.position_policy import CAPABILITY_KEYS, EffectiveEmployeePolicy, build_effective_policy


def _role(role_id: str, *, capabilities=None, tool_mode="selected", tool_ids=None, skill_mode="selected", skill_ids=None):
    return {
        "_id": role_id,
        "name": role_id,
        "capabilities": capabilities or {},
        "tool_access_mode": tool_mode,
        "tool_ids": tool_ids or [],
        "skill_access_mode": skill_mode,
        "skill_ids": skill_ids or [],
    }


def test_existing_employee_without_position_role_keeps_explicit_migration_access() -> None:
    policy = build_effective_policy("tenant", "user", [])
    assert policy.migration_pending is True
    assert all(policy.capabilities[key] for key in CAPABILITY_KEYS)
    assert policy.tool_access_mode == "all"
    assert policy.skill_access_mode == "all"


def test_employee_with_only_disabled_or_missing_assigned_role_does_not_fall_back_to_full_access() -> None:
    policy = build_effective_policy("tenant", "user", [], assigned_role_ids=["disabled-role"])
    assert policy.migration_pending is False
    assert not any(policy.capabilities.values())
    assert policy.tool_access_mode == "selected"
    assert policy.skill_access_mode == "selected"


def test_roleless_employee_is_denied_after_migration_is_completed() -> None:
    policy = build_effective_policy("tenant", "user", [], migration_completed=True)
    assert policy.migration_pending is False
    assert not any(policy.capabilities.values())
    assert policy.tool_access_mode == "selected"
    assert policy.skill_access_mode == "selected"


def test_multiple_roles_union_resources_and_global_denies_win() -> None:
    roles = [
        _role("marketing", capabilities={"content_generation": True}, tool_ids=["crm"], skill_ids=["writer"]),
        _role("developer", capabilities={"code_generation": True}, tool_mode="all", skill_mode="all"),
    ]
    overrides = [
        {"_id": "allow", "allow_capabilities": ["browser_automation"], "allow_tool_ids": ["temporary"]},
        {
            "_id": "deny",
            "deny_capabilities": ["browser_automation", "code_generation"],
            "deny_tool_ids": ["crm"],
            "deny_skill_ids": ["writer"],
        },
    ]
    policy = build_effective_policy("tenant", "user", roles, overrides)
    assert policy.allows_capability("content_generation") is True
    assert policy.allows_capability("browser_automation") is False
    assert policy.allows_capability("code_generation") is False
    assert policy.allows_external_tool("temporary") is True
    assert policy.allows_external_tool("anything-else") is True
    assert policy.allows_external_tool("crm") is False
    assert policy.allows_skill("anything-else") is True
    assert policy.allows_skill("writer") is False


def test_organization_skill_adapter_id_matches_admin_role_resource_id() -> None:
    policy = build_effective_policy(
        "tenant", "user", [_role("employee", skill_ids=["workflow-raw-id"])],
    )
    assert policy.allows_skill("org_skill:workflow-raw-id") is True
    denied = build_effective_policy(
        "tenant", "user", [_role("employee", skill_ids=["workflow-raw-id"])],
        [{"_id": "deny", "deny_skill_ids": ["workflow-raw-id"]}],
    )
    assert denied.allows_skill("org_skill:workflow-raw-id") is False


class _EmptyCatalog:
    async def list_enabled(self, tenant_id: str, user_id: str):
        return []


class _StaticPolicyResolver:
    async def resolve(self, tenant_id: str, user_id: str) -> EffectiveEmployeePolicy:
        return EffectiveEmployeePolicy(
            tenant_id=tenant_id,
            user_id=user_id,
            capabilities={key: False for key in CAPABILITY_KEYS},
        )


def test_dsh_profile_omits_disabled_enterprise_capabilities_without_modifying_dsh() -> None:
    tools = asyncio.run(ToolProfileCompiler(
        _EmptyCatalog(), InternalCapabilityCatalog(), _StaticPolicyResolver()
    ).compile(tenant_id="tenant", user_id="user"))
    refs = {tool.capability_ref for tool in tools}
    assert "content.produce@v1" not in refs
    assert "presentation.create@v1" not in refs
    assert "document.pdf_retain_pages@v1" not in refs
    assert "image.generate@v1" not in refs
    assert "browser.task@v1" not in refs
    assert "knowledge.search@v1" not in refs
    assert "data.run_script@v1" in refs
