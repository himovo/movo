from __future__ import annotations

import asyncio

from app.api.endpoints import projects


class _Cursor:
    def __init__(self, documents: list[dict]) -> None:
        self._documents = documents

    def sort(self, _field: str, _direction: int):
        return self

    def __aiter__(self):
        self._iterator = iter(self._documents)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _ProjectCollection:
    def __init__(self) -> None:
        self.documents: list[dict] = []

    async def update_one(self, scope: dict, update: dict, upsert: bool = False) -> None:
        document = next((item for item in self.documents if all(item.get(key) == value for key, value in scope.items())), None)
        if document is None:
            assert upsert
            document = dict(scope)
            document.update(update.get("$setOnInsert", {}))
            self.documents.append(document)
        document.update(update.get("$set", {}))

    async def find_one(self, scope: dict):
        return next((item for item in self.documents if all(item.get(key) == value for key, value in scope.items())), None)

    def find(self, scope: dict) -> _Cursor:
        return _Cursor([
            item for item in self.documents
            if all(item.get(key) == value for key, value in scope.items())
        ])


class _Database:
    def __init__(self) -> None:
        self.desktop_projects = _ProjectCollection()


def test_desktop_projects_are_bound_to_authenticated_employee(monkeypatch) -> None:
    database = _Database()

    async def identity(authorization: str | None):
        assert authorization
        tenant_id, user_id = authorization.split(":", 1)
        return tenant_id, user_id

    monkeypatch.setattr(projects, "get_db", lambda: database)
    monkeypatch.setattr(projects, "_identity", identity)

    async def scenario() -> None:
        await projects.create_desktop_project(
            projects.DesktopProjectCreate(workspace_id="alice-workspace", title="Alice", worktree=False),
            authorization="tenant:alice",
        )
        await projects.create_desktop_project(
            projects.DesktopProjectCreate(workspace_id="bob-workspace", title="Bob", worktree=False),
            authorization="tenant:bob",
        )

        alice = await projects.list_desktop_projects(authorization="tenant:alice")
        bob = await projects.list_desktop_projects(authorization="tenant:bob")
        assert [item["workspace_id"] for item in alice.data] == ["alice-workspace"]
        assert [item["workspace_id"] for item in bob.data] == ["bob-workspace"]

    asyncio.run(scenario())
