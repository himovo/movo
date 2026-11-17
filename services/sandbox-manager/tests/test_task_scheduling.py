"""Concurrency regressions against the real task and legacy job entry points."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep

import pytest

from app.jobs import ScriptJobs
from app.task_containers import TaskContainers
from app.task_locks import TaskLocks


class Engine:
    def find_compose_service(self, *args): return 'proxy'
    def create_outbound_network(self, name): return name
    def connect_network(self, *args): pass
    def create(self, name, payload): return name
    def start(self, *args): pass
    def execute(self, *args): return 0, b'ok', b''
    def remove(self, *args): pass
    def disconnect_network(self, *args): pass
    def remove_network(self, *args): pass
    def inspect(self, *args): return {}
    def kill(self, *args): pass
    def wait(self, *args): return 0
    def logs(self, *args): return b''


def setup(tmp_path, monkeypatch, capacity=2):
    monkeypatch.setenv('MOVO_SANDBOX_WORKSPACE_ROOT', str(tmp_path))
    monkeypatch.setenv('MOVO_SANDBOX_WORKSPACE_VOLUME', 'test')
    monkeypatch.setenv('MOVO_SANDBOX_SCRIPT_IMAGE', 'test:1')
    monkeypatch.setenv('MOVO_SANDBOX_MAX_CONCURRENT', str(capacity))
    for task in ('a'*32, 'b'*32):
        for call in ('c'*32, 'd'*32):
            root = tmp_path / task / 'work' / 'calls' / call
            root.mkdir(parents=True)
            for name in ('runner.py', 'plugin.py', 'stdin.json'):
                (root / name).touch()


def wait_for(predicate):
    deadline = monotonic() + 2
    while not predicate():
        assert monotonic() < deadline
        sleep(.005)


def test_cold_creation_does_not_block_warm_task(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    creating, release = Event(), Event()
    class SlowEngine(Engine):
        def start(self, container):
            if container.endswith('a'*32):
                creating.set()
                assert release.wait(2)
    tasks = TaskContainers(SlowEngine())
    tasks.execute('b'*32, 'c'*32)
    with ThreadPoolExecutor() as pool:
        cold = pool.submit(tasks.execute, 'a'*32, 'c'*32)
        assert creating.wait(1)
        try:
            assert pool.submit(tasks.execute, 'b'*32, 'd'*32).result(1)['exit_code'] == 0
        finally:
            release.set()
        cold.result(1)


def test_same_task_wait_does_not_block_other_users(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    entered, release = Event(), Event()
    class BlockingEngine(Engine):
        def execute(self, container, *args):
            if container.endswith('a'*32) and not release.is_set():
                entered.set()
                assert release.wait(2)
            return super().execute(container, *args)
    tasks = TaskContainers(BlockingEngine())
    with ThreadPoolExecutor() as pool:
        first = pool.submit(tasks.execute, 'a'*32, 'c'*32)
        assert entered.wait(1)
        second = pool.submit(tasks.execute, 'a'*32, 'd'*32)
        wait_for(lambda: tasks.scheduler.status()['pending'] == 1)
        try:
            pool.submit(tasks.execute, 'b'*32, 'c'*32).result(1)
        finally:
            release.set()
        first.result(1)
        second.result(1)
    assert tasks.engine is not None
    assert len(tasks._leases) == 2


def test_legacy_jobs_and_task_calls_share_budget(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, 1)
    entered, release = Event(), Event()
    class BlockingEngine(Engine):
        def execute(self, *args):
            entered.set()
            assert release.wait(2)
            return 0, b'', b''
    jobs = ScriptJobs(Engine())
    tasks = TaskContainers(BlockingEngine(), scheduler=jobs.scheduler)
    job_id = 'e'*32
    root = tmp_path / job_id
    root.mkdir()
    for name in ('runner.py', 'plugin.py', 'stdin.json'): (root / name).touch()
    with ThreadPoolExecutor() as pool:
        first = pool.submit(tasks.execute, 'a'*32, 'c'*32)
        assert entered.wait(1)
        second = pool.submit(jobs.execute, job_id)
        wait_for(lambda: jobs.status()['pending'] == 1)
        assert jobs.status()['running'] == 1
        release.set()
        first.result(1)
        second.result(1)
    assert jobs.status()['running'] == 0


def test_failed_creation_returns_reservation_and_slot(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    class FailedEngine(Engine):
        def start(self, *args): raise RuntimeError('startup failed')
    tasks = TaskContainers(FailedEngine())
    with pytest.raises(RuntimeError, match='startup failed'):
        tasks.execute('a'*32, 'c'*32)
    assert tasks._creating == 0
    assert tasks.scheduler.status()['running'] == 0
    assert not tasks._leases
    assert not tasks._task_locks._entries


def test_frozen_task_rejects_execution_without_leaking_slot(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    tasks = TaskContainers(Engine())
    tasks.execute('a'*32, 'c'*32)
    tasks.freeze('a'*32)
    with pytest.raises(RuntimeError, match='finalizing'):
        tasks.execute('a'*32, 'd'*32)
    assert tasks.scheduler.status()['running'] == 0
    tasks.dispose('a'*32)
    assert not tasks._leases


def test_nested_lifecycle_lock_is_released():
    locks = TaskLocks()
    with locks.hold('a'):
        with locks.hold('a'):
            pass
    assert not locks._entries


def test_restart_stops_interrupted_exec_but_preserves_idle_task(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    class RecoveryEngine(Engine):
        killed = []
        def inspect(self, container):
            return {'ExecIDs': ['in-flight']} if container.endswith('a'*32) else {}
        def kill(self, container): self.killed.append(container)
    engine = RecoveryEngine()
    original = TaskContainers(engine)
    original.execute('a'*32, 'c'*32)
    original.execute('b'*32, 'c'*32)
    restored = TaskContainers(engine)
    restored.recover_interrupted()
    assert restored._leases['a'*32].frozen
    assert not restored._leases['b'*32].frozen
    assert len(engine.killed) == 1
    assert restored.execute('b'*32, 'd'*32)['exit_code'] == 0
    with pytest.raises(RuntimeError, match='finalizing'):
        restored.execute('a'*32, 'd'*32)
