"""Opt-in Docker probe. Run only inside a dedicated validation manager container."""
from __future__ import annotations

import json
import hashlib
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.docker_engine import DockerEngine
from app.execution_permits import ExecutionPermits
from app.execution_scheduler import ExecutionScheduler
from app.plugin_runtimes import PluginRuntimes
from app.resident_capacity import ResidentCapacity
from app.settings_store import SettingsStore
from app.task_containers import TaskContainers


def main():
    if not os.environ['MOVO_SANDBOX_COMPOSE_PROJECT'].startswith('movo-scheduling-audit-'):
        raise RuntimeError('Dedicated validation project is required')
    root=Path(os.environ['MOVO_SANDBOX_WORKSPACE_ROOT'])
    guard=threading.Lock(); running=0; peak=0
    class ObservedDocker(DockerEngine):
        def execute(self,*args):
            nonlocal running,peak
            with guard:running+=1;peak=max(peak,running)
            try:return super().execute(*args)
            finally:
                with guard:running-=1
    engine=ObservedDocker()
    scheduler=ExecutionScheduler(2,8,SettingsStore(root/'.manager-state'))
    permits=ExecutionPermits(scheduler)
    residents=ResidentCapacity(10)
    tasks=TaskContainers(engine,scheduler=scheduler,permits=permits,residents=residents)
    plugins=PluginRuntimes(engine,scheduler=scheduler,permits=permits,residents=residents)
    created_tasks=[];created_plugins=[];results={}
    def prepare(number,delay=1):
        task=hashlib.sha256(f"{os.environ['MOVO_SANDBOX_COMPOSE_PROJECT']}:{number}".encode()).hexdigest()[:32];call='a'*32
        directory=root/task/'work'/'calls'/call
        directory.mkdir(parents=True,exist_ok=True)
        for parent in (root/task,root/task/'work',root/task/'work'/'calls',directory):parent.chmod(0o777)
        (directory/'runner.py').write_text(f'import time,json\ntime.sleep({delay})\nprint(json.dumps({{"success":True}}))\n')
        (directory/'plugin.py').write_text('')
        (directory/'stdin.json').write_text('{}')
        created_tasks.append(task)
        return task,call
    try:
        calls=[prepare(i) for i in range(1,5)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes=list(pool.map(lambda pair:tasks.execute(*pair),calls))
        assert peak==2 and all(row['exit_code']==0 for row in outcomes)
        results['four_real_script_tasks_peak']=peak
        before=len(tasks._leases)
        tasks.execute(*calls[0])
        assert len(tasks._leases)==before
        results['warm_container_reused']=True
        scheduler.configure(capacity=1)
        lease=plugins.create('tenant:audit:profile:user-one','1'*64,startup_guard=True)
        created_plugins.append(lease['lease_id'])
        assert scheduler.status()['running']==1
        with ThreadPoolExecutor() as pool:
            future=pool.submit(tasks.execute,*calls[1])
            deadline=time.monotonic()+3
            while scheduler.status()['pending']!=1:
                assert time.monotonic()<deadline;time.sleep(.01)
            assert not future.done()
            permits.release(lease['startup_token'],lease['lease_id'])
            assert future.result(20)['exit_code']==0
        results['real_plugin_startup_and_scripts_share_budget']=True
        child=next(row for row in plugins._leases.values() if row['lease_id']==lease['lease_id'])
        inspected=engine.inspect(child['container_id'])
        assert inspected['State']['Running']
        results['real_dsh_plugin_container_running']=True
        native=permits.acquire(lease['lease_id'],'native-operation')['token']
        delegated=prepare(5,.1)
        assert tasks.execute(*delegated,execution_permit=native)['exit_code']==0
        assert scheduler.status()['running']==1
        permits.release(native,lease['lease_id'])
        results['nested_native_to_real_script_at_capacity_one']=True
        restarted=ExecutionScheduler(2,8,SettingsStore(root/'.manager-state'))
        assert restarted.status()['capacity']==1
        results['saved_limit_restored']=True
        assert scheduler.status()['running']==0 and scheduler.status()['pending']==0
        results['final_scheduler']=scheduler.status()
    finally:
        for lease in created_plugins:plugins.dispose(lease)
        for task in created_tasks:tasks.dispose(task)
        results['resident_containers_after_cleanup']=residents.status()['resident_containers']
        engine.client.close()
    assert results['resident_containers_after_cleanup']==0
    print(json.dumps(results,sort_keys=True))


if __name__=='__main__':main()
