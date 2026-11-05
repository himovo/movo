"""Read mutable Skill control-plane rows without using the legacy executor."""

from __future__ import annotations

from typing import Any, Protocol

from app.services.org_skill_adapter import organization_skill_adapter
from app.services.skills import user_skill_service
from app.core.db import get_db
from app.product.resource_access import filter_allowed_resource_ids
from app.services.skill_packages.readiness import attach_environment_status


class SkillCatalog(Protocol):
    async def list_enabled(self, tenant_id: str, user_id: str) -> list[dict[str, Any]]: ...


class MongoSkillCatalog:
    async def list_enabled(self, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        personal = await user_skill_service.list_skills(user_id, main_id=tenant_id, include_package_files=False)
        organization = await organization_skill_adapter.list_runtime_skills(main_id=tenant_id, include_package_files=False)
        allowed_organization_ids = await filter_allowed_resource_ids(
            "skill",
            main_id=tenant_id,
            user_id=user_id,
            resource_ids=(str(item.get("id") or "") for item in organization if isinstance(item, dict)),
        )
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        # Only a staged upgrade needs a readiness lookup to promote its new
        # package. The installed version is durable even during an outage or
        # base-image rebuild.
        pending = [
            item for item in [*personal, *organization]
            if isinstance(item, dict) and item.get("pending_package")
        ]
        if pending:
            await attach_environment_status(pending)
        for item in [*personal, *organization]:
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("id") or "").strip()
            if not source_id or source_id in seen:
                continue
            if item.get("enabled", item.get("is_active", True)) is False:
                continue
            # Preparation is execution readiness, not an installed Skill
            # change. Keep the durable Skill definition in the profile.
            is_organization = str(item.get("visibility") or "").lower() == "organization" or str(item.get("source") or "") == "org_db"
            if is_organization and source_id not in allowed_organization_ids:
                continue
            seen.add(source_id)
            runtime_skill = dict(item)
            runtime_skill.pop("pending_package", None)
            rows.append(runtime_skill)
        package_ids = [str(item.get("package_id") or "") for item in rows if item.get("package_id")]
        if package_ids:
            packages = await get_db().skill_packages.find({
                "_id": {"$in": package_ids}, "main_id": tenant_id,
            }, {
                "archive_base64": 1, "archive_gridfs_id": 1, "root_prefix": 1,
                "files": {"$slice": 3},
            }).to_list(length=len(package_ids))
            by_id = {str(item.get("_id") or ""): item for item in packages}
            for row in rows:
                package = by_id.get(str(row.get("package_id") or ""))
                if package:
                    resource_files = [
                        item for item in package.get("files") or []
                        if str(item.get("path") or "") not in {"SKILL.md", "_meta.json"}
                    ]
                    if resource_files:
                        row["runtime_bundle_base64"] = str(package.get("archive_base64") or "")
                        row["runtime_bundle_archive_id"] = str(package.get("archive_gridfs_id") or "")
                        row["runtime_bundle_root"] = str(package.get("root_prefix") or "")
        return rows
