from __future__ import annotations

import base64
import datetime
import uuid
from typing import Any, Literal

from pymongo.errors import DuplicateKeyError

from app.core.db import get_db
from app.core.tenant import resolve_main_id

from .validator import ValidatedSkillPackage


InstallScope = Literal["personal", "organization"]


class SkillPackageInstaller:
    """Persist validated packages into the existing personal/organization control planes."""

    async def install(
        self,
        package: ValidatedSkillPackage,
        *,
        scope: InstallScope,
        main_id: str,
        user_id: str = "",
        package_source: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tenant_id = resolve_main_id(main_id)
        if scope == "personal" and not user_id:
            raise ValueError("personal Skill installation requires an owner")
        db = get_db()
        collection = db.user_skills if scope == "personal" else db.skills
        owner_query: dict[str, Any] = {"main_id": tenant_id, "package_slug": package.name}
        if scope == "personal":
            owner_query["user_id"] = str(user_id)
        current = await collection.find_one(owner_query)
        if current and str(current.get("package_digest") or "") == package.archive_digest:
            if package_source:
                source = dict(package_source)
                await collection.update_one(
                    {"_id": current["_id"], **owner_query},
                    {"$set": {"package_source": source}},
                )
                package_id = str(current.get("package_id") or "")
                if package_id:
                    await db.skill_packages.update_one(
                        {"_id": package_id, "main_id": tenant_id},
                        {"$set": {"source": source}},
                    )
                current = {**current, "package_source": source}
            return self._result(
                current, package, duplicate=True, updated=False, package_source=package_source,
            )

        now = datetime.datetime.now(datetime.timezone.utc)
        package_id = uuid.uuid4().hex
        package_doc = {
            "_id": package_id,
            "main_id": tenant_id,
            "owner_scope": scope,
            "owner_id": str(user_id) if scope == "personal" else tenant_id,
            "slug": package.name,
            "version": package.version,
            "digest": package.archive_digest,
            "root_prefix": package.root_prefix,
            "archive_base64": base64.b64encode(package.archive_bytes).decode("ascii"),
            "files": [dict(item) for item in package.files],
            "kind": package.package_kind,
            "children": [dict(item) for item in package.children],
            "source": dict(package_source or {}),
            "created_at": now,
        }
        await db.skill_packages.insert_one(package_doc)

        common = {
            "name": package.display_name,
            "description": package.description,
            "scenario": package.when_to_use,
            "summary": package.description,
            "type": package.package_kind,
            "skill_type": package.package_kind,
            "role": "execution",
            "skill_markdown": package.markdown,
            "package_id": package_id,
            "package_slug": package.name,
            "package_version": package.version,
            "package_digest": package.archive_digest,
            "package_files": [dict(item) for item in package.files],
            "package_declared_tools": list(package.declared_tools),
            "package_referenced_tools": list(package.referenced_tools),
            "package_warnings": [dict(item) for item in package.warnings],
            "model_invocable": package.model_invocable,
            "user_invocable": package.user_invocable,
            "package_market_metadata": dict(package.market_metadata),
            "package_kind": package.package_kind,
            "package_children": [dict(item) for item in package.children],
            "package_source": dict(package_source or {}),
            "source_kind": "zip",
            "updated_at": now,
        }
        if current:
            previous = [str(item) for item in current.get("previous_package_ids") or [] if str(item)]
            old_package = str(current.get("package_id") or "")
            if old_package:
                previous.append(old_package)
            retained = previous[-5:]
            common["previous_package_ids"] = retained
            try:
                await collection.update_one({"_id": current["_id"], **owner_query}, {"$set": common})
            except Exception:
                await db.skill_packages.delete_one({"_id": package_id})
                raise
            expired = [item for item in previous if item not in retained]
            if expired:
                await db.skill_packages.delete_many({"_id": {"$in": expired}})
            updated = await collection.find_one({"_id": current["_id"], **owner_query})
            return self._result(
                updated or {**current, **common}, package,
                duplicate=False, updated=True, package_source=package_source,
            )

        skill_id = uuid.uuid4().hex
        record = {
            "_id": skill_id,
            "main_id": tenant_id,
            **common,
            "config": {},
            "enabled": scope == "personal",
            "is_active": scope == "personal",
            "visibility": "private" if scope == "personal" else "organization",
            "category": "Imported Expert Package" if package.package_kind == "expert_package" else "Imported Skill",
            "tags": ["zip", package.package_kind],
            "formats": [],
            "input_profile": {},
            "contract_json": {},
            "resources": {},
            "advanced": {},
            "notes": package.when_to_use,
            "execution_plane": "runtime",
            "skill_contract_version": "dsh-package-v1",
            "skill_contract": {},
            "skill_lint_warnings": [item["message"] for item in package.warnings],
            "sources": [],
            "skill_object_path": "",
            "created_at": now,
        }
        if scope == "personal":
            record["user_id"] = str(user_id)
        try:
            await collection.insert_one(record)
        except DuplicateKeyError:
            await db.skill_packages.delete_one({"_id": package_id})
            winner = await collection.find_one(owner_query)
            if winner and str(winner.get("package_digest") or "") == package.archive_digest:
                return self._result(
                    winner, package, duplicate=True, updated=False, package_source=package_source,
                )
            raise
        return self._result(
            record, package, duplicate=False, updated=False, package_source=package_source,
        )

    @staticmethod
    def _result(
        record: dict[str, Any],
        package: ValidatedSkillPackage,
        *,
        duplicate: bool,
        updated: bool,
        package_source: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": str(record.get("_id") or ""),
            "name": str(record.get("name") or package.display_name),
            "slug": package.name,
            "description": package.description,
            "version": package.version,
            "type": package.package_kind,
            "enabled": bool(record.get("enabled", record.get("is_active", False))),
            "duplicate": duplicate,
            "updated": updated,
            "fileCount": len(package.files),
            "digest": package.archive_digest,
            "warnings": [dict(item) for item in package.warnings],
            "childCount": len(package.children),
            "children": [dict(item) for item in package.children],
            "source": dict(package_source or record.get("package_source") or {}),
            "compatibility": {
                "status": "warning" if package.warnings else "compatible",
                "declaredTools": list(package.declared_tools),
                "referencedTools": list(package.referenced_tools),
                "warnings": [dict(item) for item in package.warnings],
            },
        }
