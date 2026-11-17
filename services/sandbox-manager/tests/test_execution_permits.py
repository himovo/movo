from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep

import pytest

from app.execution_permits import ExecutionPermits
from app.execution_scheduler import ExecutionScheduler
from app.settings_store import SettingsStore


def pool(tmp_path, capacity=1):
    scheduler = ExecutionScheduler(capacity, 8, SettingsStore(tmp_path))
    return ExecutionPermits(scheduler)


def wait_for(check):
    end = monotonic()+2
    while not check():
        assert monotonic() < end
        sleep(.005)


def test_delegation_runs_at_capacity_one_and_fanout_is_bounded(tmp_path):
    p = pool(tmp_path)
    root = p.acquire('runtime-a', 'parent')['token']
    first = p.acquire('runtime-a', 'child', root)['token']
    assert p.scheduler.status()['running'] == 1
    with ThreadPoolExecutor() as threads:
        second = threads.submit(p.acquire, 'runtime-a', 'sibling', root)
        wait_for(lambda:p.scheduler.status()['pending']==1)
        assert not second.done()
        p.release(first)
        sibling = second.result(1)['token']
    assert p.scheduler.status()['running'] == 1
    p.release(sibling)
    p.release(root)
    assert p.scheduler.status()['running'] == 0


def test_parallel_sibling_uses_another_slot_when_available(tmp_path):
    p = pool(tmp_path,2)
    root = p.acquire('a','root')['token']
    child = p.acquire('a','child',root)['token']
    sibling = p.acquire('a','sibling',root)['token']
    assert p.scheduler.status()['running'] == 2
    for token in (sibling,child,root):p.release(token)


def test_scope_rejection_expiry_and_parent_cancel_do_not_leak(tmp_path):
    p = pool(tmp_path)
    root = p.acquire('a','root')['token']
    with pytest.raises(ValueError):p.acquire('b','cross-user',root)
    assert not p._pending
    child = p.acquire('a','child',root)['token']
    p.release(root)
    assert p.scheduler.status()['running'] == 1
    p.release(child)
    assert p.scheduler.status()['running'] == 0
    token = p.acquire('a','new')['token']
    p.ttl = -1
    def cannot_stop(owner):raise OSError('Docker unavailable')
    p.expire(on_expire=cannot_stop)
    assert p.scheduler.status()['running'] == 1
    p.expire(on_expire=lambda owner:None)
    assert p.scheduler.status()['running'] == 0
    p.release(token)


def test_cancel_queued_and_lost_acquire_response(tmp_path):
    p = pool(tmp_path)
    root = p.acquire('a','busy')['token']
    with ThreadPoolExecutor() as threads:
        future = threads.submit(p.acquire,'b','waiting')
        wait_for(lambda:p.scheduler.status()['pending']==1)
        p.cancel('b','waiting')
        with pytest.raises(RuntimeError,match='cancelled'):future.result(1)
    p.release(root)
    p.acquire('b','response-lost')
    p.cancel('b','response-lost')
    assert p.scheduler.status()['running'] == 0
    p.cancel('c','not-started')
    with pytest.raises(RuntimeError):p.acquire('c','not-started')
    assert not p._pending


def test_resident_wait_is_visible_and_does_not_reserve_execution(tmp_path):
    from app.resident_capacity import ResidentCapacity
    p=pool(tmp_path,2)
    residents=ResidentCapacity(1)
    residents.claim('old')
    entered=Event()
    def waiting():
        with p.scheduler.slot('new',ready=lambda active:residents.available('new'),reserve=lambda:residents.claim('new')):
            entered.set()
    with ThreadPoolExecutor() as threads:
        future=threads.submit(waiting)
        wait_for(lambda:p.scheduler.status()['pending']==1)
        assert p.scheduler.status()['running']==0
        with p.scheduler.slot('existing-work'):
            assert not entered.is_set()
        residents.release('old');p.scheduler.wake()
        future.result(1)
    assert entered.is_set()


def test_guarded_plugin_startup_shares_script_budget_and_resident_accounting(tmp_path,monkeypatch):
    from app.plugin_runtimes import PluginRuntimes
    from app.resident_capacity import ResidentCapacity
    from test_task_scheduling import Engine,setup
    setup(tmp_path,monkeypatch,1)
    monkeypatch.setenv('MOVO_SANDBOX_RUNTIME_IMAGE','test:1')
    class PluginEngine(Engine):
        def create_internal_network(self,name):return name
    p=pool(tmp_path)
    residents=ResidentCapacity(2)
    runtimes=PluginRuntimes(PluginEngine(),scheduler=p.scheduler,permits=p,residents=residents)
    lease=runtimes.create('user-a',startup_guard=True)
    assert p.scheduler.status()['running']==1
    with ThreadPoolExecutor() as threads:
        started=Event()
        def script():
            with p.scheduler.slot('script'):started.set()
        future=threads.submit(script)
        wait_for(lambda:p.scheduler.status()['pending']==1)
        p.release(lease['startup_token'],lease['lease_id'])
        future.result(1)
    assert residents.status()['resident_containers']==1
    runtimes.dispose(lease['lease_id'])
    assert residents.status()['resident_containers']==0


def test_failed_plugin_cleanup_keeps_budget_until_owner_is_stopped(tmp_path, monkeypatch):
    from app.plugin_runtimes import PluginRuntimes
    from app.resident_capacity import ResidentCapacity
    from test_task_scheduling import Engine, setup
    setup(tmp_path, monkeypatch, 1)
    monkeypatch.setenv('MOVO_SANDBOX_RUNTIME_IMAGE', 'test:1')
    class UncertainEngine(Engine):
        failed = True
        def create_internal_network(self, name): return name
        def start(self, container): raise RuntimeError('startup interrupted')
        def remove(self, container):
            if self.failed: raise OSError('Docker unavailable')
    p = pool(tmp_path)
    residents = ResidentCapacity(2)
    engine = UncertainEngine()
    runtimes = PluginRuntimes(engine, scheduler=p.scheduler, permits=p, residents=residents)
    with pytest.raises(RuntimeError, match='startup interrupted'):
        runtimes.create('uncertain-user', startup_guard=True)
    assert p.scheduler.status()['running'] == 1
    assert residents.status()['resident_containers'] == 1
    p.ttl = -1
    p.expire(on_expire=runtimes.recover_interrupted_owner)
    assert p.scheduler.status()['running'] == 1
    engine.failed = False
    p.expire(on_expire=runtimes.recover_interrupted_owner)
    assert p.scheduler.status()['running'] == 0
    assert residents.status()['resident_containers'] == 0
