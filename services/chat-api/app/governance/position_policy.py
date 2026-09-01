from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from app.core.db import get_db

MIGRATION_COLLECTION = "position_role_migrations"

CAPABILITY_KEYS = (
    "content_generation",
    "image_generation",
    "code_generation",
    "browser_automation",
    "internal_knowledge",
)

INTERNAL_CAPABILITY_REQUIREMENTS = {
    "content.produce@v1": "content_generation",
    "presentation.create@v1": "content_generation",
    "document.pdf_retain_pages@v1": "content_generation",
    "image.generate@v1": "image_generation",
    "browser.task@v1": "browser_automation",
    "knowledge.search@v1": "internal_knowledge",
}


@dataclass(frozen=True)
class EffectiveEmployeePolicy:
    tenant_id: str
    user_id: str
    capabilities: dict[str, bool]
    tool_access_mode: str = "selected"
    tool_ids: frozenset[str] = frozenset()
    denied_tool_ids: frozenset[str] = frozenset()
    skill_access_mode: str = "selected"
    skill_ids: frozenset[str] = frozenset()
    denied_skill_ids: frozenset[str] = frozenset()
    role_ids: tuple[str, ...] = ()
    role_names: tuple[str, ...] = ()
    migration_pending: bool = False
    version: str = ""

    def allows_capability(self, key: str) -> bool:
        return bool(self.capabilities.get(key, False))

    def allows_external_tool(self, tool_id: str) -> bool:
        return tool_id not in self.denied_tool_ids and (self.tool_access_mode == "all" or tool_id in self.tool_ids)

    def allows_skill(self, skill_id: str) -> bool:
        # Admin role resources use the organization asset's raw id, while the
        # employee Skill adapter exposes it as ``org_skill:<id>`` to prevent a
        # collision with personal assets. Treat those as one governed identity.
        aliases = {skill_id}
        if skill_id.startswith("org_skill:"):
            aliases.add(skill_id.removeprefix("org_skill:"))
        denied = any(item in self.denied_skill_ids for item in aliases)
        allowed = self.skill_access_mode == "all" or any(item in self.skill_ids for item in aliases)
        return not denied and allowed

    def allows_internal(self, capability_ref: str) -> bool:
        required = INTERNAL_CAPABILITY_REQUIREMENTS.get(capability_ref)
        return required is None or self.allows_capability(required)

    def public_snapshot(self) -> dict[str, Any]:
        return {
            "capabilities": dict(self.capabilities),
            "toolAccessMode": self.tool_access_mode,
            "toolIds": sorted(self.tool_ids),
            "deniedToolIds": sorted(self.denied_tool_ids),
            "skillAccessMode": self.skill_access_mode,
            "skillIds": sorted(self.skill_ids),
            "deniedSkillIds": sorted(self.denied_skill_ids),
            "roleIds": list(self.role_ids),
            "roleNames": list(self.role_names),
            "migrationPending": self.migration_pending,
            "version": self.version,
        }


class EmployeePolicyResolver(Protocol):
    async def resolve(self, tenant_id: str, user_id: str) -> EffectiveEmployeePolicy: ...


class MongoEmployeePolicyResolver:
    async def resolve(self, tenant_id: str, user_id: str) -> EffectiveEmployeePolicy:
        db = get_db()
        assignments = await db.end_user_position_roles.find(
            {"main_id": tenant_id, "user_id": user_id}
        ).to_list(length=100)
        role_ids = [str(row.get("role_id") or "") for row in assignments if row.get("role_id")]
        roles = await db.position_roles.find(
            {"main_id": tenant_id, "_id": {"$in": role_ids}, "status": "active"}
        ).to_list(length=100) if role_ids else []

        now = datetime.now(timezone.utc)
        overrides = await db.end_user_capability_overrides.find({
            "main_id": tenant_id,
            "user_id": user_id,
            "status": "active",
            "effective_at": {"$lte": now},
            "$or": [{"expires_at": None}, {"expires_at": {"$exists": False}}, {"expires_at": {"$gt": now}}],
        }).sort("created_at", 1).to_list(length=100)
        migration = await db[MIGRATION_COLLECTION].find_one({"main_id": tenant_id}, {"status": 1})
        return build_effective_policy(
            tenant_id,
            user_id,
            roles,
            overrides,
            role_ids,
            migration_completed=str((migration or {}).get("status") or "pending") == "complete",
        )


def build_effective_policy(
    tenant_id: str,
    user_id: str,
    roles: list[dict[str, Any]],
    overrides: list[dict[str, Any]] | None = None,
    assigned_role_ids: list[str] | None = None,
    migration_completed: bool = False,
) -> EffectiveEmployeePolicy:
    if not roles and not assigned_role_ids:
        if migration_completed:
            return EffectiveEmployeePolicy(
                tenant_id=tenant_id,
                user_id=user_id,
                capabilities={key: False for key in CAPABILITY_KEYS},
                migration_pending=False,
                version="migration-complete-no-role",
            )
        return EffectiveEmployeePolicy(
            tenant_id=tenant_id,
            user_id=user_id,
            capabilities={key: True for key in CAPABILITY_KEYS},
            tool_access_mode="all",
            skill_access_mode="all",
            migration_pending=True,
            version="legacy-full-access",
        )

    capabilities = {key: False for key in CAPABILITY_KEYS}
    tool_all = False
    skill_all = False
    tool_ids: set[str] = set()
    skill_ids: set[str] = set()
    denied_tool_ids: set[str] = set()
    denied_skill_ids: set[str] = set()
    allowed_capabilities: set[str] = set()
    denied_capabilities: set[str] = set()
    role_names: list[str] = []
    version_parts: list[str] = []
    role_ids = list(assigned_role_ids or [str(role.get("_id") or "") for role in roles])

    for role in roles:
        role_names.append(str(role.get("name") or ""))
        for key in CAPABILITY_KEYS:
            capabilities[key] = capabilities[key] or bool((role.get("capabilities") or {}).get(key))
        tool_all = tool_all or str(role.get("tool_access_mode") or "selected") == "all"
        skill_all = skill_all or str(role.get("skill_access_mode") or "selected") == "all"
        tool_ids.update(str(item) for item in role.get("tool_ids") or [])
        skill_ids.update(str(item) for item in role.get("skill_ids") or [])
        version_parts.append(f"{role.get('_id')}:{_timestamp(role.get('updated_at'))}")

    for override in overrides or []:
        allowed_capabilities.update(str(key) for key in override.get("allow_capabilities") or [])
        denied_capabilities.update(str(key) for key in override.get("deny_capabilities") or [])
        tool_ids.update(str(item) for item in override.get("allow_tool_ids") or [])
        skill_ids.update(str(item) for item in override.get("allow_skill_ids") or [])
        denied_tool_ids.update(str(item) for item in override.get("deny_tool_ids") or [])
        denied_skill_ids.update(str(item) for item in override.get("deny_skill_ids") or [])
        version_parts.append(f"override:{override.get('_id')}:{_timestamp(override.get('updated_at'))}")

    for key in allowed_capabilities:
        if key in capabilities:
            capabilities[key] = True
    for key in denied_capabilities:
        if key in capabilities:
            capabilities[key] = False

    return EffectiveEmployeePolicy(
        tenant_id=tenant_id,
        user_id=user_id,
        capabilities=capabilities,
        tool_access_mode="all" if tool_all else "selected",
        tool_ids=frozenset(tool_ids),
        denied_tool_ids=frozenset(denied_tool_ids),
        skill_access_mode="all" if skill_all else "selected",
        skill_ids=frozenset(skill_ids),
        denied_skill_ids=frozenset(denied_skill_ids),
        role_ids=tuple(role_ids),
        role_names=tuple(role_names),
        version="|".join(version_parts),
    )


def _timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value or "")
