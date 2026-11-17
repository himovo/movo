from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep

import pytest

from app.execution_scheduler import ExecutionScheduler
from app.settings_store import SettingsStore


def wait_for(predicate):
    deadline = monotonic() + 2
    while not predicate():
        assert monotonic() < deadline
        sleep(.005)


def scheduler(tmp_path, capacity=2, pending=8):
    return ExecutionScheduler(capacity, pending, SettingsStore(tmp_path))


def test_increase_wakes_waiter_and_survives_restart(tmp_path):
    s = scheduler(tmp_path, 1)
    entered, release = Event(), Event()
    def work():
        with s.slot('b'):
            entered.set()
            assert release.wait(2)
    with ThreadPoolExecutor() as pool:
        with s.slot('a'):
            future = pool.submit(work)
            wait_for(lambda: s.status()['pending'] == 1)
            assert not entered.is_set()
            s.configure(capacity=2)
            assert entered.wait(1)
            release.set()
        future.result()
    assert scheduler(tmp_path, 1).status()['capacity'] == 2


def test_decrease_drains_without_interrupting(tmp_path):
    s = scheduler(tmp_path)
    entered = Event()
    def work():
        with s.slot('c'):
            entered.set()
    with ThreadPoolExecutor() as pool:
        with s.slot('a'):
            with s.slot('b'):
                s.configure(capacity=1)
                f = pool.submit(work)
                wait_for(lambda: s.status()['pending'] == 1)
                assert s.status()['running'] == 2
            assert not entered.wait(.03)
        f.result(1)
    assert entered.is_set()


def test_same_task_waiter_does_not_reserve_capacity(tmp_path):
    s = scheduler(tmp_path)
    with ThreadPoolExecutor() as pool:
        with s.slot('task-a'):
            def work():
                with s.slot('task-a'):
                    pass
            f = pool.submit(work)
            wait_for(lambda: s.status()['pending'] == 1)
            with s.slot('task-b', timeout=.1):
                assert s.status()['running'] == 2
        f.result(1)


def test_zero_queue_allows_immediate_execution_and_timeout_releases_ticket(tmp_path):
    s = scheduler(tmp_path, 1, 0)
    with s.slot('a'):
        with pytest.raises(RuntimeError, match='queue is full'):
            with s.slot('b'):
                pass
        s.configure(max_pending=1)
        with pytest.raises(RuntimeError, match='timed out'):
            with s.slot('b', timeout=.01):
                pass
        assert s.status()['pending'] == 0
    with pytest.raises(ValueError):
        with s.slot('c'):
            raise ValueError('execution failed')
    assert s.status()['running'] == 0


def test_save_failure_keeps_live_limits_and_legacy_settings(tmp_path, monkeypatch):
    store = SettingsStore(tmp_path)
    store.save_max_pending(3)
    s = ExecutionScheduler(2, 8, store)
    assert s.status()['max_pending'] == 3
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(store, 'save', fail)
    with pytest.raises(OSError):
        s.configure(capacity=4)
    assert s.status()['capacity'] == 2
    for value in (0, 101, True):
        with pytest.raises(ValueError):
            s.configure(capacity=value)
