import asyncio
from types import SimpleNamespace

from app.product import execution_access
from app.dsh_runtime.profile.skills.execution_access import skill_execution_is_allowed
from app.api.endpoints import skills as skill_api
from app.services.skill_packages.execution_requirements import package_uses_execution


class Policy:
    async def allows(self, *, main_id: str, user_id: str, capability: str) -> bool:
        return capability != "data.run_script@v1"


def test_community_has_no_execution_restriction(monkeypatch):
    monkeypatch.setattr(execution_access, "get_product_extension", lambda: SimpleNamespace(execution_access_policy=None))
    assert asyncio.run(execution_access.execution_is_allowed(
        main_id="tenant", user_id="member", capability="data.run_script@v1",
    ))


def test_package_can_declare_execution_without_bundled_scripts():
    assert package_uses_execution(files=(), tools=(), declared_requirement=True)


def test_workflow_script_requires_distribution_permission(monkeypatch):
    monkeypatch.setattr(execution_access, "get_product_extension", lambda: SimpleNamespace(execution_access_policy=Policy()))
    workflow = {"skill_contract": {"structure": {"workflow_nodes": [{"type": "script_plugin"}]}}}
    ordinary = {"skill_markdown": "Summarize a document"}
    package = {"skill_markdown": "Run the bundled script", "package_files": [{"path": "scripts/probe.sh"}]}
    installed_package = {"skill_markdown": "Run the bundled script", "package_requires_execution": True}
    assert not asyncio.run(skill_execution_is_allowed(row=workflow, tenant_id="tenant", user_id="member"))
    assert not asyncio.run(skill_execution_is_allowed(row=package, tenant_id="tenant", user_id="member"))
    assert not asyncio.run(skill_execution_is_allowed(row=installed_package, tenant_id="tenant", user_id="member"))
    assert asyncio.run(skill_execution_is_allowed(row=ordinary, tenant_id="tenant", user_id="member"))


def test_authorized_skill_remains_visible_with_execution_reason(monkeypatch):
    monkeypatch.setattr(execution_access, "get_product_extension", lambda: SimpleNamespace(execution_access_policy=Policy()))
    row = {
        "id": "skill-1", "name": "Report", "enabled": True,
        "skill_contract": {"structure": {"workflow_nodes": [{"type": "script_plugin"}]}},
    }

    async def personal(*args, **kwargs):
        return [row]

    async def organization(*args, **kwargs):
        return []

    async def no_status(*args, **kwargs):
        return None

    async def allowed(*args, **kwargs):
        return set()

    monkeypatch.setattr(skill_api.user_skill_service, "list_skills", personal)
    monkeypatch.setattr(skill_api.organization_skill_adapter, "list_runtime_skills", organization)
    monkeypatch.setattr(skill_api, "attach_environment_status", no_status)
    monkeypatch.setattr(skill_api, "filter_allowed_resource_ids", allowed)
    response = asyncio.run(skill_api.list_selectable_skills(
        user_id="member", main_id="tenant", main_id_snake=None,
        scope="all", keyword="", cursor=None, limit=20,
    ))
    item = response.data["items"][0]
    assert item["id"] == "skill-1"
    assert item["available"] is False
    assert item["unavailableReason"] == "execution_access"


def test_preparing_skill_remains_visible_but_cannot_be_selected(monkeypatch):
    row = {"id": "skill-2", "name": "Report", "enabled": True, "environment_status": "preparing"}

    async def personal(*args, **kwargs):
        return [row]

    async def organization(*args, **kwargs):
        return []

    async def no_status(*args, **kwargs):
        return None

    async def allowed(*args, **kwargs):
        return set()

    monkeypatch.setattr(skill_api.user_skill_service, "list_skills", personal)
    monkeypatch.setattr(skill_api.organization_skill_adapter, "list_runtime_skills", organization)
    monkeypatch.setattr(skill_api, "attach_environment_status", no_status)
    monkeypatch.setattr(skill_api, "filter_allowed_resource_ids", allowed)
    response = asyncio.run(skill_api.list_selectable_skills(
        user_id="member", main_id="tenant", main_id_snake=None,
        scope="all", keyword="", cursor=None, limit=20,
    ))
    item = response.data["items"][0]
    assert item["available"] is False
    assert item["unavailableReason"] == "environment_preparing"
