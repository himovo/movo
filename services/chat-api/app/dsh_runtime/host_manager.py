"""Lifecycle manager for the out-of-process Node DSH Runtime Host."""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from pathlib import Path

import httpx

from .errors import DshRuntimeError


@dataclass(frozen=True)
class DshHostConfig:
    node_executable: Path
    host_entry: Path
    storage_root: Path
    log_path: Path
    bind_host: str = "127.0.0.1"
    startup_timeout_seconds: float = 20.0


class DshRuntimeHostManager:
    def __init__(self, config: DshHostConfig) -> None:
        self._config = config
        self._process: asyncio.subprocess.Process | None = None
        self._log_file = None
        self.base_url: str | None = None

    @property
    def process(self) -> asyncio.subprocess.Process | None:
        return self._process

    async def start(self) -> str:
        if self._process is not None:
            raise DshRuntimeError("DSH Runtime Host is already started")
        port = self._reserve_port()
        config = self._config
        config.storage_root.mkdir(parents=True, exist_ok=True)
        config.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_file = config.log_path.open("ab", buffering=0)
        self._process = await asyncio.create_subprocess_exec(
            str(config.node_executable),
            str(config.host_entry),
            "--host",
            config.bind_host,
            "--port",
            str(port),
            "--storage-root",
            str(config.storage_root),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=self._log_file,
            stderr=self._log_file,
        )
        self.base_url = f"http://{config.bind_host}:{port}"
        try:
            await self._wait_until_ready()
        except BaseException:
            await self.stop()
            raise
        return self.base_url

    async def stop(self) -> None:
        process = self._process
        self._process = None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        if self._log_file is not None:
            self._log_file.close()
            self._log_file = None

    async def _wait_until_ready(self) -> None:
        assert self.base_url is not None
        assert self._process is not None
        deadline = asyncio.get_running_loop().time() + self._config.startup_timeout_seconds
        async with httpx.AsyncClient(timeout=0.5) as client:
            while asyncio.get_running_loop().time() < deadline:
                if self._process.returncode is not None:
                    raise DshRuntimeError(
                        f"DSH Runtime Host exited during startup with code {self._process.returncode}"
                    )
                try:
                    response = await client.get(f"{self.base_url}/health")
                    if response.status_code == 200 and response.json().get("ok") is True:
                        return
                except (httpx.HTTPError, ValueError):
                    pass
                await asyncio.sleep(0.05)
        raise DshRuntimeError("DSH Runtime Host did not become healthy before the startup deadline")

    def _reserve_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.bind((self._config.bind_host, 0))
            return int(server.getsockname()[1])
