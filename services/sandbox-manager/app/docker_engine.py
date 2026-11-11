"""Small, allowlisted Docker Engine client for ephemeral jobs."""

from __future__ import annotations

import json

import httpx


def split_docker_logs(raw: bytes) -> tuple[bytes, bytes]:
    stdout = bytearray()
    stderr = bytearray()
    offset = 0
    while offset + 8 <= len(raw):
        stream = raw[offset]
        size = int.from_bytes(raw[offset + 4:offset + 8], "big")
        offset += 8
        if size > len(raw) - offset:
            raise ValueError("Docker returned a truncated log frame")
        target = stderr if stream == 2 else stdout
        target.extend(raw[offset:offset + size])
        offset += size
    if offset != len(raw):
        raise ValueError("Docker returned an invalid log frame")
    return bytes(stdout), bytes(stderr)


def merged_docker_logs(raw: bytes) -> bytes:
    """Preserve Docker's interleaved stdout/stderr frame order."""
    output = bytearray()
    offset = 0
    while offset + 8 <= len(raw):
        size = int.from_bytes(raw[offset + 4:offset + 8], "big")
        offset += 8
        if size > len(raw) - offset:
            raise ValueError("Docker returned a truncated log frame")
        output.extend(raw[offset:offset + size])
        offset += size
    if offset != len(raw):
        raise ValueError("Docker returned an invalid log frame")
    return bytes(output)


class DockerEngine:
    def __init__(self, socket_path: str = "/var/run/docker.sock") -> None:
        self.client = httpx.Client(
            base_url="http://docker/v1.45",
            transport=httpx.HTTPTransport(uds=socket_path),
            timeout=120,
            trust_env=False,
        )

    def request(self, method: str, path: str, **kwargs):
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        return response

    def create(self, name: str, payload: dict) -> str:
        return self.request("POST", "/containers/create", params={"name": name}, json=payload).json()["Id"]

    def start(self, container_id: str) -> None:
        self.request("POST", f"/containers/{container_id}/start")

    def wait(self, container_id: str, timeout: float) -> int:
        response = self.client.post(f"/containers/{container_id}/wait", params={"condition": "not-running"}, timeout=timeout)
        response.raise_for_status()
        return int(response.json()["StatusCode"])

    def logs(self, container_id: str) -> bytes:
        return self.request("GET", f"/containers/{container_id}/logs", params={"stdout": 1, "stderr": 1}).content

    def recent_logs(self, container_id: str, lines: int = 200) -> bytes:
        return self.request("GET", f"/containers/{container_id}/logs", params={"stdout": 1, "stderr": 1, "tail": lines}).content

    def execute(self, container_id: str, command: list[str], timeout: float) -> tuple[int, bytes, bytes]:
        created = self.request("POST", f"/containers/{container_id}/exec", json={
            "AttachStdout": True, "AttachStderr": True, "Cmd": command,
            "User": "65534:65534", "WorkingDir": "/job/work",
        }).json()["Id"]
        response = self.client.post(
            f"/exec/{created}/start", json={"Detach": False, "Tty": False}, timeout=timeout,
        )
        response.raise_for_status()
        status = self.request("GET", f"/exec/{created}/json").json()
        stdout, stderr = split_docker_logs(response.content)
        return int(status["ExitCode"]), stdout, stderr

    def kill(self, container_id: str) -> None:
        try:
            self.request("POST", f"/containers/{container_id}/kill")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {304, 404, 409}:
                raise

    def inspect(self, container_id: str) -> dict:
        return self.request("GET", f"/containers/{container_id}/json").json()

    def remove(self, container_id: str) -> None:
        try:
            self.request("DELETE", f"/containers/{container_id}", params={"force": 1, "v": 1})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

    def create_internal_network(self, name: str) -> str:
        return self._create_network(name, internal=True)

    def create_outbound_network(self, name: str) -> str:
        return self._create_network(name, internal=False)

    def _create_network(self, name: str, *, internal: bool) -> str:
        payload = {
            "Name": name, "Driver": "bridge", "Internal": internal,
            "CheckDuplicate": True,
            "Labels": {"movo.role": "sandbox-job-network"},
        }
        return self.request("POST", "/networks/create", json=payload).json()["Id"]

    def connect_network(self, network_id: str, container_id: str, aliases: list[str] | None = None) -> None:
        self.request("POST", f"/networks/{network_id}/connect", json={
            "Container": container_id,
            "EndpointConfig": {"Aliases": aliases or []},
        })

    def disconnect_network(self, network_id: str, container_id: str) -> None:
        try:
            self.request("POST", f"/networks/{network_id}/disconnect", json={"Container": container_id, "Force": True})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {403, 404}:
                return
            try:
                network = self.request("GET", f"/networks/{network_id}").json()
            except httpx.HTTPStatusError as inspect_error:
                if inspect_error.response.status_code == 404:
                    return
                raise exc from inspect_error
            if container_id not in (network.get("Containers") or {}):
                return
            raise

    def remove_network(self, network_id: str) -> None:
        try:
            self.request("DELETE", f"/networks/{network_id}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return
            try:
                self.request("GET", f"/networks/{network_id}")
            except httpx.HTTPStatusError as inspect_error:
                if inspect_error.response.status_code == 404:
                    return
                raise exc from inspect_error
            raise

    def find_compose_service(self, project: str, service: str) -> str:
        filters = {"label": [f"com.docker.compose.project={project}", f"com.docker.compose.service={service}"]}
        rows = self.request("GET", "/containers/json", params={"filters": json.dumps(filters)}).json()
        if len(rows) != 1:
            raise RuntimeError(f"Expected one running {service} container for project {project}")
        return rows[0]["Id"]

    def image_id(self, name: str) -> str | None:
        try:
            return str(self.request("GET", f"/images/{name}/json").json()["Id"])
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    def commit(self, container_id: str, repository: str, tag: str) -> str:
        return str(self.request("POST", "/commit", params={
            "container": container_id, "repo": repository, "tag": tag,
        }, timeout=300).json()["Id"])
