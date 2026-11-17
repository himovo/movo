"""Restart, authentication and duplicate-admission regression coverage."""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.execution_permit_routes import permit_router
from app.execution_permits import ExecutionPermits
from app.execution_scheduler import ExecutionScheduler
from app.permit_markers import PermitMarkers
from app.settings_store import SettingsStore


def test_markers_stop_each_owner_once_and_preserve_failed_recovery(tmp_path):
    markers = PermitMarkers(tmp_path)
    markers.add('one', 'runtime-a')
    markers.add('two', 'runtime-a')
    markers.add('three', 'runtime-b')
    stopped = []
    def stop(owner):
        if owner == 'runtime-b':
            raise OSError('Docker unavailable')
        stopped.append(owner)
    with pytest.raises(RuntimeError, match="recovery failed"):
        markers.recover(stop)
    assert stopped == ['runtime-a']
    assert sorted(path.name for path in markers.root.iterdir()) == ['three']
    markers.recover(stopped.append)
    assert stopped == ['runtime-a', 'runtime-b']
    assert not list(markers.root.iterdir())


def test_authenticated_permits_reject_cross_owner_and_duplicate_keys(tmp_path):
    pool = ExecutionPermits(ExecutionScheduler(2, 8, SettingsStore(tmp_path)), markers=PermitMarkers(tmp_path))
    def authorize(value):
        if value != 'Bearer private':
            raise HTTPException(401)
    app = FastAPI()
    app.include_router(permit_router(authorize, lambda: pool))
    client = TestClient(app)
    path = '/v1/execution-permits/'
    body = {'owner': 'runtime-a', 'key': 'command'}
    assert client.post(path+'acquire', json=body).status_code == 401
    client.headers['Authorization'] = 'Bearer private'
    token = client.post(path+'acquire', json=body).json()['token']
    assert client.post(path+'acquire', json=body).status_code == 400
    assert client.post(path+'heartbeat', json={'owner': 'runtime-b', 'token': token}).status_code == 400
    assert client.post(path+'release', json={'owner': 'runtime-b', 'token': token}).status_code == 400
    assert pool.scheduler.status()['running'] == 1
    assert client.post(path+'release', json={'owner': 'runtime-a', 'token': token}).status_code == 200
    assert pool.scheduler.status()['running'] == 0
    assert not list(pool.markers.root.iterdir())
