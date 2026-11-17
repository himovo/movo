from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main


def test_queue_setting_requires_manager_token(monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_TOKEN", "a" * 64)
    client = TestClient(main.app)
    assert client.put("/v1/settings", json={"max_pending": 3}).status_code == 401


def test_queue_setting_is_validated_and_applied(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_TOKEN", "a" * 64)

    from types import SimpleNamespace
    from app.execution_scheduler import ExecutionScheduler
    from app.settings_store import SettingsStore
    scheduler = ExecutionScheduler(2, 8, SettingsStore(tmp_path))
    monkeypatch.setattr(main, "jobs", lambda: SimpleNamespace(scheduler=scheduler))
    client = TestClient(main.app)
    headers = {"Authorization": f"Bearer {'a' * 64}"}
    assert client.put("/v1/settings", json={"max_pending": 101}, headers=headers).status_code == 422
    response = client.put("/v1/settings", json={"max_pending": 3}, headers=headers)
    assert response.status_code == 200
    assert response.json()["max_pending"] == 3
    assert response.json()["capacity"] == 2
    assert client.put("/v1/settings", json={"capacity": 0}, headers=headers).status_code == 422
    response = client.put("/v1/settings", json={"capacity": 5}, headers=headers)
    assert response.json()["capacity"] == 5
    assert response.json()["max_pending"] == 3


@pytest.mark.parametrize('route', ['scripts', 'plugins'])
def test_control_plane_remains_responsive_with_many_script_waiters(tmp_path, monkeypatch, route):
    import asyncio
    from threading import Event, Lock
    from types import SimpleNamespace
    import httpx
    from app.execution_scheduler import ExecutionScheduler
    from app.settings_store import SettingsStore

    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_TOKEN", "a" * 64)
    scheduler = ExecutionScheduler(2, 8, SettingsStore(tmp_path))
    release, guard = Event(), Lock()
    entered = 0
    def execute(*args, **kwargs):
        nonlocal entered
        with guard:
            entered += 1
        assert release.wait(5)
        return {"exit_code": 0}
    fake = SimpleNamespace(scheduler=scheduler, execute=execute, status=scheduler.status)
    monkeypatch.setattr(main, 'jobs', lambda: fake)
    monkeypatch.setattr(main, 'tasks', lambda: fake)
    monkeypatch.setattr(main, 'plugins', lambda: SimpleNamespace(status=lambda: {},create=execute))
    monkeypatch.setattr(main, 'DockerEngine', lambda: SimpleNamespace(request=lambda *args: None))

    async def verify():
        headers = {"Authorization": f"Bearer {'a' * 64}"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test', headers=headers) as client:
            calls = [asyncio.create_task(client.post(
                '/v1/script-task-calls' if route == 'scripts' else '/v1/plugin-runtimes',
                json={'task_id': f'{i:032x}', 'call_id': 'a'*32} if route == 'scripts' else {'isolation_key': f'user-{i}'},
            )) for i in range(45)]
            try:
                for _ in range(200):
                    if entered == 45:
                        break
                    await asyncio.sleep(.005)
                assert entered == 45
                response = await asyncio.wait_for(client.get('/health'), 1)
                assert response.status_code == 200
                response = await asyncio.wait_for(client.put('/v1/settings', json={'capacity': 4}), 1)
                assert response.json()['capacity'] == 4
            finally:
                release.set()
                results = await asyncio.gather(*calls)
            assert all(result.status_code == 200 for result in results)
    asyncio.run(verify())
