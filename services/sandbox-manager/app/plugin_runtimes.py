"""Container leases for DSH plugins that require Host services."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import threading
from pathlib import Path
from uuid import uuid4

from .docker_engine import DockerEngine
from .lease_store import LeaseStore
from .storage_paths import legacy_runtime_root, manager_state_root, workspace_root


class PluginRuntimes:
    def __init__(self, engine: DockerEngine) -> None:
        self.engine = engine
        self.project = os.environ.get("MOVO_SANDBOX_COMPOSE_PROJECT", "movo")
        self.image = os.environ["MOVO_SANDBOX_RUNTIME_IMAGE"]
        self.volume = os.environ["MOVO_SANDBOX_WORKSPACE_VOLUME"]
        self.volume_root = workspace_root()
        self.legacy_root = legacy_runtime_root()
        self._store = LeaseStore(manager_state_root(), legacy_root=self.legacy_root)
        self._leases: dict[str, dict] = self._store.load()
        self._lock = threading.Lock()
        self._creating: set[str] = set()

    def status(self) -> dict:
        with self._lock:
            return {"plugin_runtimes": len(self._leases)}

    def create(self, isolation_key: str, personal_space_key: str | None = None) -> dict:
        if not isolation_key or len(isolation_key) > 512:
            raise ValueError("Invalid Runtime isolation key")
        if personal_space_key is not None and not re.fullmatch(r"[0-9a-f]{64}", personal_space_key):
            raise ValueError("Invalid personal space key")
        with self._lock:
            if isolation_key in self._creating:
                raise ValueError("Runtime creation is already in progress")
            self._creating.add(isolation_key)
        try:
            return self._create(isolation_key, personal_space_key)
        finally:
            with self._lock:
                self._creating.discard(isolation_key)

    def _create(self, isolation_key: str, personal_space_key: str | None = None) -> dict:
        with self._lock:
            previous = next((item["lease_id"] for item in self._leases.values()
                             if item.get("isolation_key") == isolation_key), None)
        if previous:
            self.dispose(previous)
        lease_id = uuid4().hex
        storage_key = hashlib.sha256(isolation_key.encode("utf-8")).hexdigest()
        legacy_storage = self.legacy_root / "sandbox-runtimes" / storage_key
        if legacy_storage.is_dir():
            relative_storage = f"sandbox-runtimes/{storage_key}"
            storage_volume = os.environ["MOVO_SANDBOX_RUNTIME_VOLUME"]
        else:
            relative_storage = f"plugin-runtimes/{storage_key}"
            storage = self.volume_root / relative_storage
            storage.mkdir(parents=True, exist_ok=True)
            storage.chmod(0o777)
            storage_volume = self.volume
        proxy_id = self.engine.find_compose_service(self.project, "sandbox-egress")
        parent_id = self.engine.find_compose_service(self.project, "dsh-runtime-host")
        network_id = None
        container_id = None
        connected_proxy = False
        connected_parent = False
        name = f"movo-plugin-{lease_id}"
        token = secrets.token_hex(32)
        try:
            network_id = self.engine.create_internal_network(f"movo-plugin-net-{lease_id}")
            self.engine.connect_network(network_id, proxy_id, ["sandbox-egress"])
            connected_proxy = True
            self.engine.connect_network(network_id, parent_id, ["sandbox-gateway"])
            connected_parent = True
            mounts = [{
                "Type": "volume", "Source": storage_volume, "Target": "/data/dsh-runtime",
                "VolumeOptions": {"Subpath": relative_storage, "NoCopy": True},
            }]
            offline_volume = os.environ.get("MOVO_OFFLINE_PACKAGE_VOLUME")
            if offline_volume:
                mounts.append({"Type": "volume", "Source": offline_volume, "Target": "/offline-packages"})
            if personal_space_key:
                personal_root = self.volume_root / "personal" / personal_space_key
                personal_root.mkdir(parents=True, exist_ok=True)
                personal_root.chmod(0o777)
                plugin_home = personal_root / "plugin-home"
                plugin_home.mkdir(exist_ok=True)
                plugin_home.chmod(0o777)
                personal_tmp = personal_root / "tmp"
                personal_tmp.mkdir(exist_ok=True)
                personal_tmp.chmod(0o777)
                mounts.append({
                    "Type": "volume", "Source": self.volume,
                    "Target": "/job/home",
                    "VolumeOptions": {"Subpath": f"personal/{personal_space_key}", "NoCopy": True},
                })
            if (self.legacy_root / "plugin-archives").is_dir():
                mounts.append({
                    "Type": "volume", "Source": os.environ["MOVO_SANDBOX_RUNTIME_VOLUME"],
                    "Target": "/data/dsh-runtime/plugin-archives", "ReadOnly": True,
                    "VolumeOptions": {"Subpath": "plugin-archives", "NoCopy": True},
                })
            payload = {
                "Image": self.image,
                "User": "1000:1000",
                "Entrypoint": ["node"],
                "Cmd": ["src/host.mjs", "--host", "0.0.0.0", "--port", "8101", "--storage-root", "/data/dsh-runtime"],
                "WorkingDir": "/app",
                "Env": [
                    f"DSH_RUNTIME_HOST_TOKEN={token}", "MOVO_DSH_PLUGIN_CHILD=1",
                    f"HOME={'/job/home/plugin-home' if personal_space_key else '/data/dsh-runtime'}",
                    *(["MOVO_PLUGIN_LEGACY_HOME=/data/dsh-runtime"] if personal_space_key else []),
                    f"TMPDIR={'/job/home/tmp' if personal_space_key else '/tmp'}",
                    "NODE_USE_ENV_PROXY=1",
                    *(["MOVO_PERSONAL_SPACE_ROOT=/job/home"] if personal_space_key else []),
                    "HTTP_PROXY=http://sandbox-egress:3128", "HTTPS_PROXY=http://sandbox-egress:3128",
                    "NO_PROXY=sandbox-gateway,localhost,127.0.0.1",
                    *(["MOVO_OFFLINE_PACKAGE_ROOT=/offline-packages",
                       "npm_config_userconfig=/offline-packages/.npmrc"] if offline_volume else []),
                ],
                "HostConfig": {
                    "NetworkMode": network_id, "ReadonlyRootfs": True,
                    "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"],
                    "PidsLimit": 128, "Memory": 2 * 1024 * 1024 * 1024,
                    "NanoCpus": 2_000_000_000,
                    "Tmpfs": {"/tmp": "rw,exec,nosuid,size=64m"},
                    "Mounts": mounts,
                },
                "Labels": {"movo.role": "plugin-runtime", "movo.lease": lease_id, "movo.project": self.project},
            }
            container_id = self.engine.create(name, payload)
            self.engine.start(container_id)
            lease = {
                "lease_id": lease_id, "host": name, "port": 8101, "token": token,
                "isolation_key": isolation_key,
                "container_id": container_id, "network_id": network_id,
                "proxy_id": proxy_id, "parent_id": parent_id,
            }
            with self._lock:
                self._leases[lease_id] = lease
                try:
                    self._store.save(self._leases)
                except Exception:
                    self._leases.pop(lease_id, None)
                    raise
            return {key: lease[key] for key in ("lease_id", "host", "port", "token")}
        except Exception:
            try:
                self._cleanup(container_id, network_id, proxy_id if connected_proxy else None, parent_id if connected_parent else None)
            except Exception:
                pass
            raise

    def dispose(self, lease_id: str) -> None:
        with self._lock:
            lease = self._leases.get(lease_id)
        if lease is None:
            return
        self._cleanup(lease["container_id"], lease["network_id"], lease["proxy_id"], lease["parent_id"])
        with self._lock:
            self._leases.pop(lease_id, None)
            self._store.save(self._leases)

    def _cleanup(self, container_id: str | None, network_id: str | None,
                 proxy_id: str | None, parent_id: str | None) -> None:
        errors = []
        if container_id is not None:
            try:
                self.engine.kill(container_id)
            except Exception as exc:
                errors.append(exc)
            try:
                self.engine.remove(container_id)
            except Exception as exc:
                errors.append(exc)
        if network_id is not None:
            if parent_id is not None:
                try:
                    self.engine.disconnect_network(network_id, parent_id)
                except Exception as exc:
                    errors.append(exc)
            if proxy_id is not None:
                try:
                    self.engine.disconnect_network(network_id, proxy_id)
                except Exception as exc:
                    errors.append(exc)
            try:
                self.engine.remove_network(network_id)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise RuntimeError(f"Sandbox cleanup failed: {errors[0]}")
