"""Build and reuse isolated dependency images for immutable Skill bundles."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from pathlib import Path
from uuid import uuid4

from .docker_engine import DockerEngine, merged_docker_logs, split_docker_logs
from .dependency_sources import build_attempts, retryable_failure
from .skill_build_records import SkillBuildRecords, _safe_log, MAX_LOG_CHARS
from .offline_package_store import OfflinePackageStore
from .offline_collections import record as record_collection


LOG = logging.getLogger(__name__)
SKILL_PACKAGE_KINDS = ("pip", "npm", "apt-archives", "apt-lists")


class DependencyPreparationError(RuntimeError):
    pass


class SkillEnvironments:
    def __init__(self, engine: DockerEngine) -> None:
        self.engine = engine
        self.root = Path(os.environ.get("MOVO_SANDBOX_WORKSPACE_ROOT", "/workspaces")) / "skill-cache"
        self.volume = os.environ["MOVO_SANDBOX_WORKSPACE_VOLUME"]
        self.base_image = os.environ["MOVO_SANDBOX_SCRIPT_IMAGE"]
        self.project = os.environ.get("MOVO_SANDBOX_COMPOSE_PROJECT", "movo")
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="movo-skill-deps")
        self.lock = threading.Lock()
        self.pending: dict[str, Future[str]] = {}
        self.records = SkillBuildRecords()
        self.packages = OfflinePackageStore()

    def _skill_root(self, digest: str) -> Path:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("Invalid Skill digest")
        bundle = self.root / digest
        roots = [path.parent for path in bundle.glob("SKILL.md")]
        roots.extend(path.parent for path in bundle.glob("*/SKILL.md"))
        if len(roots) != 1:
            raise ValueError("Skill package root is missing or ambiguous")
        return roots[0]

    def _image_name(self, digest: str) -> str | None:
        root = self._skill_root(digest)
        if not any((root / name).is_file() for name in (
            "requirements.txt", "package.json", "apt-packages.txt",
        )):
            return None
        base_id = self.engine.image_id(self.base_image)
        if not base_id:
            raise ValueError("Sandbox script base image is missing")
        key = hashlib.sha256(f"{base_id}:{digest}".encode()).hexdigest()[:40]
        return f"movo-skill-deps:{key}"

    def start(self, digest: str, *, retry_failed: bool = False) -> str:
        image = self._image_name(digest)
        if image is None:
            return "not_required"
        if self.engine.image_id(image):
            return "ready"
        with self.lock:
            existing = self.pending.get(image)
            if existing is None or (existing.done() and (existing.exception() is None or retry_failed)):
                existing = self.pool.submit(self._build, digest, image)
                self.pending[image] = existing
        return "failed" if existing.done() and existing.exception() else "preparing"

    def ready_image(self, digest: str, timeout: float = 5) -> str:
        image = self._image_name(digest)
        if image is None:
            return self.base_image
        if self.engine.image_id(image):
            return image
        self.start(digest)
        with self.lock:
            future = self.pending[image]
        try:
            return future.result(timeout=timeout)
        except TimeoutError as exc:
            raise DependencyPreparationError("Skill dependencies are still preparing; retry shortly") from exc
        except Exception as exc:
            raise DependencyPreparationError(
                "Skill dependency preparation failed; check sandbox manager logs"
            ) from exc

    def status(self, digest: str) -> str:
        image = self._image_name(digest)
        if image is None:
            return "not_required"
        if self.engine.image_id(image):
            return "ready"
        with self.lock:
            future = self.pending.get(image)
        if future is None:
            # A manager restart loses in-memory futures, but the cached bundle
            # survives. Resume preparation when the installer polls again.
            return self.start(digest)
        return "failed" if future.done() and future.exception() else "preparing"

    def live_output(self, digest: str) -> str:
        response = self.engine.request("GET", "/containers/json", params={
            "filters": json.dumps({"label": ["movo.role=skill-dependency-build", f"movo.skill_digest={digest}"]}),
        })
        containers = response.json()
        if not containers:
            return ""
        raw = self.engine.recent_logs(containers[0]["Id"])
        return _safe_log(merged_docker_logs(raw).decode(errors="replace"))[-MAX_LOG_CHARS:]

    def _build(self, digest: str, image: str) -> str:
        lease = uuid4().hex
        network_id = proxy_id = None
        deadline = time.monotonic() + self._build_timeout()
        record_id = self.records.create(digest, self.engine.image_id(self.base_image) or "")
        try:
            offline_only = self.packages.offline
            if not offline_only:
                proxy_id = self.engine.find_compose_service(self.project, "sandbox-egress")
            network_id = self.engine.create_internal_network(f"movo-deps-{lease}")
            if proxy_id:
                self.engine.connect_network(network_id, proxy_id, ["sandbox-egress"])
            environment = [
                "HOME=/tmp",
                "HTTP_PROXY=http://sandbox-egress:3128",
                "HTTPS_PROXY=http://sandbox-egress:3128",
                "http_proxy=http://sandbox-egress:3128",
                "https_proxy=http://sandbox-egress:3128",
                "PIP_DISABLE_PIP_VERSION_CHECK=1",
                f"MOVO_SKILL_DEPENDENCY_STEP_TIMEOUT={self._step_timeout()}",
            ]
            if offline_only:
                environment.append("MOVO_OFFLINE_ONLY=1")
            payload = {
                "Image": self.base_image,
                "User": "0:0",
                "Entrypoint": ["python"],
                "Cmd": ["/opt/movo-sandbox/prepare_skill.py"],
                "WorkingDir": "/tmp",
                "Env": environment,
                "HostConfig": {
                    "NetworkMode": network_id,
                    "CapDrop": ["ALL"],
                    "CapAdd": ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETUID", "SETGID"],
                    "SecurityOpt": ["no-new-privileges:true"],
                    "PidsLimit": 256,
                    "Memory": 2 * 1024 * 1024 * 1024,
                    "NanoCpus": 2_000_000_000,
                    "Mounts": [{
                        "Type": "volume", "Source": self.volume, "Target": "/skill",
                        "ReadOnly": True,
                        "VolumeOptions": {"Subpath": str(self._skill_root(digest).relative_to(self.root.parent)), "NoCopy": True},
                    }, *[{
                        "Type": "volume", "Source": os.environ.get("MOVO_OFFLINE_PACKAGE_VOLUME", self.volume), "Target": f"/offline/{kind}",
                        "VolumeOptions": {"Subpath": kind if os.environ.get("MOVO_OFFLINE_PACKAGE_VOLUME") else f".manager-state/offline-packages/{kind}", "NoCopy": True},
                    } for kind in SKILL_PACKAGE_KINDS]],
                },
                "Labels": {"movo.role": "skill-dependency-build", "movo.skill_digest": digest},
            }
            sources = build_attempts() if not offline_only else [build_attempts()[0]]
            for index, source in enumerate(sources):
                container_id = None
                output_captured = False
                try:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Skill dependency preparation exceeded its total time limit")
                    payload["Env"] = environment + source.environment()
                    container_id = self.engine.create(f"movo-deps-{lease}-{index}", payload)
                    self.engine.start(container_id)
                    exit_code = self.engine.wait(container_id, remaining)
                    stdout, stderr, ordered_output = self._container_output(container_id, digest)
                    self.records.append_attempt(
                        digest, record_id, source=source.name, exit_code=exit_code,
                        output=ordered_output,
                    )
                    output_captured = True
                    if exit_code == 0:
                        self.engine.commit(container_id, "movo-skill-deps", image.rsplit(":", 1)[1])
                        try:
                            record_collection(self.packages.root, digest=digest, record_id=record_id,
                                              source=source.name, base_image_id=self.engine.image_id(self.base_image) or "",
                                              skill_root=self._skill_root(digest))
                        except (OSError, ValueError):
                            LOG.exception("Offline package collection metadata unavailable for %s", digest)
                        self.records.finish(digest, record_id, "ready", "Image prepared")
                        return image
                    detail = (stderr or stdout)[-4000:].decode(errors="replace")
                    if index < len(sources) - 1 and retryable_failure(detail):
                        LOG.warning("Skill dependency source %s failed; retrying with %s for %s: %s", source.name, sources[index + 1].name, digest, detail)
                        continue
                    raise RuntimeError(f"Skill dependency installation failed using {source.name}: {detail}")
                finally:
                    if container_id:
                        if not output_captured:
                            _, _, ordered_output = self._container_output(container_id, digest)
                            self.records.append_attempt(
                                digest, record_id, source=source.name, exit_code=-1,
                                output=ordered_output,
                            )
                        self.engine.remove(container_id)
            raise RuntimeError("Skill dependency installation failed after all sources")
        except Exception:
            self.records.finish(digest, record_id, "failed", "Preparation failed; see sandbox manager logs for infrastructure errors")
            LOG.exception("Skill dependency build failed for %s", digest)
            raise
        finally:
            if network_id:
                if proxy_id:
                    self.engine.disconnect_network(network_id, proxy_id)
                self.engine.remove_network(network_id)

    def _container_output(self, container_id: str, digest: str) -> tuple[bytes, bytes, str]:
        try:
            raw = self.engine.logs(container_id)
            stdout, stderr = split_docker_logs(raw)
            return stdout, stderr, merged_docker_logs(raw).decode(errors="replace")
        except Exception:
            LOG.exception("Skill dependency build output unavailable for %s", digest)
            return b"", b"", ""

    @staticmethod
    def _step_timeout() -> int:
        return SkillEnvironments._bounded_timeout("MOVO_SKILL_DEPENDENCY_STEP_TIMEOUT", 480, 60, 1200)

    @staticmethod
    def _build_timeout() -> int:
        return SkillEnvironments._bounded_timeout("MOVO_SKILL_DEPENDENCY_BUILD_TIMEOUT", 1800, 300, 3600)

    @staticmethod
    def _bounded_timeout(name: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(os.environ.get(name, str(default)))
        except ValueError:
            value = default
        return max(minimum, min(value, maximum))
