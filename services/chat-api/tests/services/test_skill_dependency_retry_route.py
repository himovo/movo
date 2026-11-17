import asyncio
from types import SimpleNamespace

from app.api.endpoints import skill_package_install as routes


def test_organization_retry_loads_package_reference(monkeypatch):
    package_id = "package-1"
    row = {"_id": "skill-1", "package_id": package_id, "package_digest": "a" * 64}

    class Skills:
        async def find_one(self, query, projection):
            assert query == {"_id": "skill-1", "main_id": "tenant-1"}
            assert projection.get("package_id") == 1
            return {key: value for key, value in row.items() if key == "_id" or projection.get(key)}

    async def retry(skill):
        assert skill["package_id"] == package_id
        return "preparing"

    monkeypatch.setattr(routes, "get_db", lambda: SimpleNamespace(skills=Skills()))
    monkeypatch.setattr(routes, "retry_environment", retry)
    result = asyncio.run(routes.retry_organization_skill_dependency(
        "skill-1", SimpleNamespace(kind="admin_service", main_id="tenant-1")
    ))
    assert result["data"]["status"] == "preparing"
