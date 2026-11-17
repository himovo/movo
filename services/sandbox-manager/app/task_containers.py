"""Reusable, isolated script containers scoped to one assistant turn."""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from .docker_engine import DockerEngine
from .skill_environments import SkillEnvironments
from .task_lease_store import TaskLeaseStore
from .storage_paths import manager_state_root, legacy_runtime_root
from .settings_store import SettingsStore
from .execution_scheduler import ExecutionScheduler
from .task_locks import TaskLocks
from .execution_timing import execution_phase


IDENTIFIER = re.compile(r"^[0-9a-f]{32}$")
SKILL_DIGEST = re.compile(r"^[0-9a-f]{64}$")
PERSONAL_KEY = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class TaskLease:
    container_id: str
    network_id: str
    proxy_id: str
    skill_digest: str
    image_ref: str = ""
    frozen: bool = False


class TaskContainers:
    def __init__(self, engine: DockerEngine, environments: SkillEnvironments | None = None,
                 scheduler: ExecutionScheduler | None = None, permits=None, residents=None) -> None:
        self.engine = engine
        self.permits = permits
        self.residents = residents
        self.root = Path(os.environ.get("MOVO_SANDBOX_WORKSPACE_ROOT", "/workspaces"))
        self.volume = os.environ["MOVO_SANDBOX_WORKSPACE_VOLUME"]
        self.image = os.environ["MOVO_SANDBOX_SCRIPT_IMAGE"]
        self.project = os.environ.get("MOVO_SANDBOX_COMPOSE_PROJECT", "movo")
        self.environments = environments or SkillEnvironments(engine)
        self.capacity = int(os.environ.get("MOVO_SANDBOX_MAX_TASKS", "10"))
        self.scheduler = scheduler or ExecutionScheduler(
            int(os.environ.get("MOVO_SANDBOX_MAX_CONCURRENT", "2")),
            int(os.environ.get("MOVO_SANDBOX_MAX_PENDING", "8")),
            SettingsStore(manager_state_root(), legacy_root=legacy_runtime_root()),
        )
        self._task_locks = TaskLocks()
        self._creating = 0
        self._leases: dict[str, TaskLease] = {}
        self._lock = threading.RLock()
        self._store = TaskLeaseStore(manager_state_root())
        self._restore()

    def execute(self, task_id: str, call_id: str, *, execution_permit: str = "") -> dict:
        if not IDENTIFIER.fullmatch(task_id) or not IDENTIFIER.fullmatch(call_id):
            raise ValueError("Invalid task or call identifier")
        task_root = self.root / task_id
        call_root = task_root / "work" / "calls" / call_id
        if not all((call_root / name).is_file() for name in ("runner.py", "plugin.py", "stdin.json")):
            raise ValueError("Script call input is missing")
        marker = task_root / "skill-digest"
        digest = marker.read_text(encoding="ascii").strip() if marker.is_file() else ""
        if digest and (not SKILL_DIGEST.fullmatch(digest) or not (self.root / "skill-cache" / digest).is_dir()):
            raise ValueError("Selected Skill package is unavailable")
        personal_marker = task_root / "personal-space-key"
        personal_key = personal_marker.read_text(encoding="ascii").strip() if personal_marker.is_file() else ""
        if personal_key and not PERSONAL_KEY.fullmatch(personal_key):
            raise ValueError("Invalid personal space key")
        parent = self.permits.parent_key(execution_permit) if execution_permit and self.permits else None
        if execution_permit and self.permits is None:
            raise ValueError('Execution delegation is unavailable')
        with self.scheduler.slot(f"task:{task_id}", parent=parent,
                                 ready=lambda active: self.residents.available(f'task:{task_id}') if self.residents else self._capacity_available(task_id, active),
                                 reserve=(lambda: self.residents.claim(f'task:{task_id}')) if self.residents else None), self._task_locks.hold(task_id):
            try:
                with execution_phase("container_prepare", task_id):
                    lease = self._get_or_create(task_id, digest, personal_key)
            except Exception:
                if self.residents:
                    self.residents.release(f'task:{task_id}')
                raise
            if lease.skill_digest != digest:
                raise ValueError("A task cannot change its prepared Skill image")
            if lease.frozen:
                raise RuntimeError("The script task is already finalizing")
            try:
                with execution_phase("script_exec", task_id):
                    exit_code, stdout, stderr = self.engine.execute(lease.container_id, [
                        "python", "-I", f"/job/work/calls/{call_id}/runner.py",
                        f"/job/work/calls/{call_id}/plugin.py",
                        f"/job/work/calls/{call_id}/stdin.json",
                    ], 70)
            except Exception:
                self.dispose(task_id)
                raise
        return {
            "exit_code": exit_code,
            "stdout": stdout[:2_097_152].decode("utf-8", errors="replace"),
            "stderr": stderr[:8192].decode("utf-8", errors="replace"),
            "image_ref": lease.image_ref,
        }

    def _capacity_available(self, task_id: str, active: set[str]) -> bool:
        with self._lock:
            if task_id in self._leases:
                return True
            reserved = sum(key.startswith('task:') and key[5:] not in self._leases for key in active)
            return len(self._leases) + reserved < self.capacity

    def _get_or_create(self, task_id: str, digest: str, personal_key: str) -> TaskLease:
        with self._lock:
            lease = self._leases.get(task_id)
            if lease is not None:
                return lease
            if len(self._leases) + self._creating >= self.capacity:
                raise RuntimeError("Sandbox task capacity is full")
            self._creating += 1
        lease = None
        try:
            lease = self._create(task_id, digest, personal_key)
            with self._lock:
                self._leases[task_id] = lease
                try:
                    self._save()
                except Exception:
                    self._leases.pop(task_id, None)
                    raise
            return lease
        except Exception:
            if lease is not None:
                try:
                    self.engine.remove(lease.container_id)
                finally:
                    try:
                        self.engine.disconnect_network(lease.network_id, lease.proxy_id)
                    finally:
                        self.engine.remove_network(lease.network_id)
            raise
        finally:
            with self._lock:
                self._creating -= 1

    def dispose(self, task_id: str) -> None:
        if not IDENTIFIER.fullmatch(task_id):
            raise ValueError("Invalid task identifier")
        with self._task_locks.hold(task_id):
            with self._lock:
                lease = self._leases.get(task_id)
            if lease is None:
                return
            try:
                self.engine.remove(lease.container_id)
            finally:
                try:
                    self.engine.disconnect_network(lease.network_id, lease.proxy_id)
                finally:
                    self.engine.remove_network(lease.network_id)
            with self._lock:
                self._leases.pop(task_id, None)
                self._save()
            if self.residents:
                self.residents.release(f'task:{task_id}')
            self.scheduler.wake()

    def freeze(self, task_id: str) -> None:
        if not IDENTIFIER.fullmatch(task_id):
            raise ValueError("Invalid task identifier")
        with self._task_locks.hold(task_id):
            with self._lock:
                lease = self._leases.get(task_id)
            if lease is None:
                return
            self.engine.kill(lease.container_id)
            lease.frozen = True
            with self._lock:
                self._save()

    def recover_interrupted(self) -> None:
        for task_id, lease in list(self._leases.items()):
            if self.engine.inspect(lease.container_id).get('ExecIDs'):
                self.freeze(task_id)

    def _restore(self) -> None:
        for task_id, row in self._store.load().items():
            if not IDENTIFIER.fullmatch(task_id):
                continue
            lease = TaskLease(str(row["container_id"]), str(row["network_id"]),
                              str(row["proxy_id"]), str(row["skill_digest"]),
                              str(row.get("image_ref") or ""), bool(row.get("frozen")))
            try:
                self.engine.inspect(lease.container_id)
            except Exception:
                continue
            self._leases[task_id] = lease
            if self.residents:
                self.residents.claim(f'task:{task_id}', restoring=True)
        self._save()

    def _save(self) -> None:
        self._store.save({task_id: {
            "container_id": lease.container_id, "network_id": lease.network_id,
            "proxy_id": lease.proxy_id, "skill_digest": lease.skill_digest,
            "image_ref": lease.image_ref,
            "frozen": lease.frozen,
        } for task_id, lease in self._leases.items()})

    def _create(self, task_id: str, digest: str, personal_key: str = "") -> TaskLease:
        image = self.environments.ready_image(digest) if digest else self.image
        dependency_root = "/job/home/work" if personal_key else "/job/work"
        proxy_id = self.engine.find_compose_service(self.project, "sandbox-egress")
        network_id = self.engine.create_outbound_network(f"movo-task-{task_id}")
        container_id = None
        try:
            self.engine.connect_network(network_id, proxy_id, ["sandbox-egress"])
            mounts = [{
                "Type": "volume", "Source": self.volume, "Target": "/job/work",
                "VolumeOptions": {"Subpath": f"{task_id}/work", "NoCopy": True},
            }]
            if personal_key:
                personal_root = self.root / "personal" / personal_key
                personal_root.mkdir(parents=True, exist_ok=True)
                personal_root.chmod(0o777)
                mounts.append({
                    "Type": "volume", "Source": self.volume, "Target": "/job/home",
                    "VolumeOptions": {"Subpath": f"personal/{personal_key}", "NoCopy": True},
                })
            if digest:
                mounts.append({
                    "Type": "volume", "Source": self.volume, "Target": "/job/skills", "ReadOnly": True,
                    "VolumeOptions": {"Subpath": f"skill-cache/{digest}", "NoCopy": True},
                })
            container_id = self.engine.create(f"movo-task-{task_id}", {
                "Image": image, "User": "65534:65534", "Entrypoint": ["sleep"], "Cmd": ["infinity"],
                "WorkingDir": "/job/work", "Env": [
                    f"HOME={dependency_root}", f"TMPDIR={dependency_root}/tmp", "LANG=C.UTF-8", "PYTHONUNBUFFERED=1",
                    "HTTP_PROXY=http://sandbox-egress:3128", "HTTPS_PROXY=http://sandbox-egress:3128",
                    "http_proxy=http://sandbox-egress:3128", "https_proxy=http://sandbox-egress:3128",
                    "NO_PROXY=", "no_proxy=",
                    f"NODE_PATH={dependency_root}/.dependencies/node/node_modules:/opt/movo-skill-node-modules",
                    f"PATH={dependency_root}/.dependencies/bin:{dependency_root}/.dependencies/node/node_modules/.bin:/opt/movo-skill-node-modules/.bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                ],
                "HostConfig": {
                    "NetworkMode": network_id, "ReadonlyRootfs": True, "CapDrop": ["ALL"],
                    "SecurityOpt": ["no-new-privileges:true"], "PidsLimit": 64,
                    "Memory": 1024 * 1024 * 1024, "NanoCpus": 1_000_000_000,
                    "Tmpfs": {"/tmp": "rw,nosuid,exec,size=64m"}, "Mounts": mounts,
                },
                "Labels": {"movo.role": "script-task", "movo.task": task_id},
            })
            self.engine.start(container_id)
            return TaskLease(container_id, network_id, proxy_id, digest, image)
        except Exception:
            if container_id:
                self.engine.remove(container_id)
            self.engine.disconnect_network(network_id, proxy_id)
            self.engine.remove_network(network_id)
            raise
