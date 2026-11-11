from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.skill_packages import reconcile


def test_reconcile_installed_consumes_async_cursor(monkeypatch) -> None:
    async def run() -> None:
        prepared = []

        class Cursor:
            def __aiter__(self):
                self._rows = iter([{"_id": "a"}, {"_id": "b"}])
                return self

            async def __anext__(self):
                try:
                    return next(self._rows)
                except StopIteration:
                    raise StopAsyncIteration

        def find(query):
            assert query == {"_id": {"$in": ["a", "b"]}}
            return Cursor()

        async def package_ids():
            return {"b", "a"}

        async def prepare(package, _client, _base, _headers):
            prepared.append(package["_id"])

        monkeypatch.setattr(reconcile, "_installed_package_ids", package_ids)
        monkeypatch.setattr(reconcile, "_prepare_package", prepare)
        monkeypatch.setattr(reconcile, "get_db", lambda: SimpleNamespace(skill_packages=SimpleNamespace(find=find)))

        assert await reconcile.reconcile_installed(None, "http://manager", {}) is True
        assert sorted(prepared) == ["a", "b"]

    asyncio.run(run())
