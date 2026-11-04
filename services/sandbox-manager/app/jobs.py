"""One-shot script jobs. The API never accepts Docker images or commands."""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

from .docker_engine import DockerEngine, split_docker_logs
from .settings_store import SettingsStore
from .skill_environments import SkillEnvironments
from .storage_paths import legacy_runtime_root, manager_state_root


JOB_ID = re.compile(r"^[0-9a-f]{32}$")
SKILL_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class ScriptJobs:
    def __init__(self, engine: DockerEngine) -> None:
        self.engine = engine
        self.root = Path(os.environ.get("MOVO_SANDBOX_WORKSPACE_ROOT", "/workspaces"))
        self.volume = os.environ["MOVO_SANDBOX_WORKSPACE_VOLUME"]
        self.image = os.environ["MOVO_SANDBOX_SCRIPT_IMAGE"]
        self.slots = threading.BoundedSemaphore(int(os.environ.get("MOVO_SANDBOX_MAX_CONCURRENT", "2")))
        self.project = os.environ.get("MOVO_SANDBOX_COMPOSE_PROJECT", "movo")
        self._state_lock = threading.Lock()
        self._running = 0
        self._pending = 0
        self._settings = SettingsStore(manager_state_root(), legacy_root=legacy_runtime_root())
        self._max_pending = self._settings.max_pending(int(os.environ.get("MOVO_SANDBOX_MAX_PENDING", "8")))
        self.environments = SkillEnvironments(engine)

    def set_max_pending(self, value: int) -> dict:
        if not 0 <= value <= 100:
            raise ValueError("Pending queue limit must be between 0 and 100")
        with self._state_lock:
            self._settings.save_max_pending(value)
            self._max_pending = value
        return self.status()

    def status(self) -> dict:
        with self._state_lock:
            return {
                "running": self._running,
                "pending": self._pending,
                "capacity": int(os.environ.get("MOVO_SANDBOX_MAX_CONCURRENT", "2")),
                "max_pending": self._max_pending,
            }

    def execute(self, job_id: str) -> dict:
        if not JOB_ID.fullmatch(job_id):
            raise ValueError("Invalid job identifier")
        job_dir = self.root / job_id
        if not job_dir.is_dir() or not all((job_dir / name).is_file() for name in ("runner.py", "plugin.py", "stdin.json")):
            raise ValueError("Job input is missing")
        skill_marker = job_dir / "skill-digest"
        skill_digest = skill_marker.read_text(encoding="ascii").strip() if skill_marker.is_file() else ""
        if skill_digest and (not SKILL_DIGEST.fullmatch(skill_digest) or
                             not (self.root / "skill-cache" / skill_digest).is_dir()):
            raise ValueError("Selected Skill package is unavailable")
        image = self.environments.ready_image(skill_digest) if skill_digest else self.image
        with self._state_lock:
            if self._pending >= self._max_pending:
                raise RuntimeError("Sandbox queue is full")
            self._pending += 1
        acquired = self.slots.acquire(timeout=20)
        with self._state_lock:
            self._pending -= 1
            if acquired:
                self._running += 1
        if not acquired:
            raise RuntimeError("Sandbox queue wait timed out")
        container_id = None
        network_id = None
        proxy_id = None
        try:
            proxy_id = self.engine.find_compose_service(self.project, "sandbox-egress")
            network_id = self.engine.create_outbound_network(f"movo-sandbox-{job_id}")
            self.engine.connect_network(network_id, proxy_id, ["sandbox-egress"])
            payload = {
                "Image": image,
                "User": "65534:65534",
                "Entrypoint": ["python"],
                "Cmd": ["-I", "/job/runner.py", "/job/plugin.py", "/job/stdin.json"],
                "WorkingDir": "/job",
                "Env": [
                    "HOME=/tmp", "TMPDIR=/tmp", "LANG=C.UTF-8", "PYTHONUNBUFFERED=1",
                    "HTTP_PROXY=http://sandbox-egress:3128", "HTTPS_PROXY=http://sandbox-egress:3128",
                    "http_proxy=http://sandbox-egress:3128", "https_proxy=http://sandbox-egress:3128",
                    "NO_PROXY=", "no_proxy=",
                    "NODE_PATH=/opt/movo-skill-node-modules",
                    "PATH=/opt/movo-skill-node-modules/.bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                ],
                "HostConfig": {
                    "NetworkMode": network_id,
                    "ReadonlyRootfs": True,
                    "CapDrop": ["ALL"],
                    "SecurityOpt": ["no-new-privileges:true"],
                    "PidsLimit": 64,
                    "Memory": 1024 * 1024 * 1024,
                    "NanoCpus": 1_000_000_000,
                    "Tmpfs": {"/tmp": "rw,nosuid,noexec,size=64m"},
                    "Mounts": [{
                        "Type": "volume", "Source": self.volume, "Target": "/job",
                        "VolumeOptions": {"Subpath": job_id, "NoCopy": True},
                    }] + ([{
                        "Type": "volume", "Source": self.volume, "Target": "/job/skills",
                        "ReadOnly": True,
                        "VolumeOptions": {"Subpath": f"skill-cache/{skill_digest}", "NoCopy": True},
                    }] if skill_digest else []),
                },
                "Labels": {"movo.role": "script-job", "movo.job": job_id},
            }
            container_id = self.engine.create(f"movo-script-{job_id}", payload)
            self.engine.start(container_id)
            try:
                exit_code = self.engine.wait(container_id, 70)
            except Exception:
                self.engine.kill(container_id)
                raise
            stdout, stderr = split_docker_logs(self.engine.logs(container_id))
            return {
                "exit_code": exit_code,
                "stdout": stdout[:2_097_152].decode("utf-8", errors="replace"),
                "stderr": stderr[:8192].decode("utf-8", errors="replace"),
            }
        finally:
            try:
                if container_id is not None:
                    self.engine.remove(container_id)
            finally:
                try:
                    if network_id is not None:
                        try:
                            if proxy_id is not None:
                                self.engine.disconnect_network(network_id, proxy_id)
                        finally:
                            self.engine.remove_network(network_id)
                finally:
                    with self._state_lock:
                        self._running -= 1
                    self.slots.release()
