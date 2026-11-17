"""Admin proxy validation and partial updates for live sandbox limits."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import sandbox_settings as route


def client():
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.get_current_admin_user] = lambda: {'id': 'admin'}
    return TestClient(app)


def test_concurrency_update_forwards_only_supplied_values(monkeypatch):
    calls = []
    def request(method, path, body=None):
        calls.append((method, path, body))
        return {'capacity': 4, 'max_pending': 8}
    monkeypatch.setattr(route, '_manager_request', request)
    response = client().put('/settings', json={'capacity': 4})
    assert response.status_code == 200
    assert calls == [('PUT', '/v1/settings', {'capacity': 4})]
    assert client().put('/settings', json={'capacity': 0}).status_code == 422
    assert client().put('/settings', json={'max_pending': 101}).status_code == 422


def test_manager_failure_is_reported_without_success(monkeypatch):
    def request(*args):
        raise OSError('manager unavailable')
    monkeypatch.setattr(route, '_manager_request', request)
    assert client().put('/settings', json={'capacity': 4}).status_code == 503


def test_status_preserves_combined_scheduler_counts(monkeypatch):
    monkeypatch.setenv('MOVO_SANDBOX_MANAGER_URL', 'http://manager')
    monkeypatch.setattr(route, '_manager_request', lambda *args: {
        'ok': True, 'running': 3, 'pending': 2, 'capacity': 4,
        'max_pending': 8, 'task_capacity': 10,
    })
    status = client().get('/status').json()
    assert (status['running'], status['pending'], status['capacity']) == (3, 2, 4)
    assert status['task_capacity'] == 10
