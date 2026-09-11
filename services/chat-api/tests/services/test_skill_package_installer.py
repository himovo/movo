from __future__ import annotations

import asyncio
import io
import zipfile
from dataclasses import replace

from app.services.skill_packages import SkillPackageInstaller, validate_skill_zip
from app.services.skill_packages import installer as installer_module


class Result:
    matched_count = 1


class Collection:
    def __init__(self):
        self.rows = {}

    async def find_one(self, query, projection=None):
        for row in self.rows.values():
            if all(row.get(key) == value for key, value in query.items()):
                return dict(row)
        return None

    async def insert_one(self, row):
        self.rows[row["_id"]] = dict(row)

    async def update_one(self, query, update):
        row = await self.find_one(query)
        assert row is not None
        row.update(update["$set"])
        self.rows[row["_id"]] = row
        return Result()

    async def delete_one(self, query):
        row = await self.find_one(query)
        if row:
            self.rows.pop(row["_id"], None)


class Database:
    def __init__(self):
        self.user_skills = Collection()
        self.skills = Collection()
        self.skill_packages = Collection()


def package(version="1.0.0", body="Instructions"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        bundle.writestr("SKILL.md", f"---\nname: imported-skill\ndescription: Imported\nversion: {version}\n---\n{body}\n")
    return validate_skill_zip(output.getvalue())


def test_personal_and_organization_installations_keep_separate_ownership(monkeypatch):
    db = Database()
    monkeypatch.setattr(installer_module, "get_db", lambda: db)
    service = SkillPackageInstaller()
    personal = asyncio.run(service.install(package(), scope="personal", main_id="tenant", user_id="user"))
    organization = asyncio.run(service.install(package(), scope="organization", main_id="tenant"))
    assert personal["enabled"] is True
    assert organization["enabled"] is False
    assert next(iter(db.user_skills.rows.values()))["user_id"] == "user"
    assert "user_id" not in next(iter(db.skills.rows.values()))


def test_reinstall_updates_in_place_and_exact_duplicate_is_idempotent(monkeypatch):
    db = Database()
    monkeypatch.setattr(installer_module, "get_db", lambda: db)
    service = SkillPackageInstaller()
    first = asyncio.run(service.install(package(), scope="personal", main_id="tenant", user_id="user"))
    duplicate = asyncio.run(service.install(package(), scope="personal", main_id="tenant", user_id="user"))
    updated = asyncio.run(service.install(package("2.0.0", "Changed"), scope="personal", main_id="tenant", user_id="user"))
    assert duplicate["duplicate"] is True
    assert updated["updated"] is True
    assert updated["id"] == first["id"]
    assert len(db.user_skills.rows) == 1


def test_expert_package_persists_as_one_skill_with_internal_children(monkeypatch):
    db = Database()
    monkeypatch.setattr(installer_module, "get_db", lambda: db)
    expert = replace(
        package(),
        package_kind="expert_package",
        children=({"slug": "child-one", "name": "Child One", "description": "Child", "version": "1.0.0"},),
    )
    result = asyncio.run(SkillPackageInstaller().install(
        expert, scope="organization", main_id="tenant",
    ))
    row = next(iter(db.skills.rows.values()))
    assert result["type"] == "expert_package"
    assert result["childCount"] == 1
    assert row["type"] == "expert_package"
    assert row["package_children"][0]["slug"] == "child-one"
    assert len(db.skills.rows) == 1


def test_remote_source_is_persisted_without_changing_zip_ownership(monkeypatch):
    db = Database()
    monkeypatch.setattr(installer_module, "get_db", lambda: db)
    source = {"kind": "skillhub", "coordinate": "@owner/imported-skill", "slug": "imported-skill"}
    result = asyncio.run(SkillPackageInstaller().install(
        package(), scope="personal", main_id="tenant", user_id="user", package_source=source,
    ))
    row = next(iter(db.user_skills.rows.values()))
    package_row = next(iter(db.skill_packages.rows.values()))
    assert row["source_kind"] == "zip"
    assert row["package_source"] == source
    assert package_row["source"] == source
    assert result["source"] == source


def test_duplicate_remote_install_records_its_distribution_source(monkeypatch):
    db = Database()
    monkeypatch.setattr(installer_module, "get_db", lambda: db)
    service = SkillPackageInstaller()
    asyncio.run(service.install(package(), scope="personal", main_id="tenant", user_id="user"))
    source = {"kind": "skillhub", "coordinate": "@owner/imported-skill", "slug": "imported-skill"}
    result = asyncio.run(service.install(
        package(), scope="personal", main_id="tenant", user_id="user", package_source=source,
    ))
    assert result["duplicate"] is True
    assert next(iter(db.user_skills.rows.values()))["package_source"] == source
    assert next(iter(db.skill_packages.rows.values()))["source"] == source
