"""Client boundary between the legacy script contract and job containers."""

from __future__ import annotations

import os
import hashlib
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4

import httpx


def container_backend_enabled() -> bool:
    return bool(os.environ.get("MOVO_SANDBOX_MANAGER_URL", "").strip())


def task_key(message_id: str) -> str:
    return hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:32]


def task_workspace(message_id: str) -> Path:
    return Path(os.environ.get("MOVO_SANDBOX_WORKSPACE_ROOT", "/workspaces")) / task_key(message_id)


@contextmanager
def script_workspace(task_id: str = "") -> Iterator[Path]:
    if not container_backend_enabled():
        with tempfile.TemporaryDirectory(prefix="askai_script_plugin_") as path:
            yield Path(path)
        return
    root = Path(os.environ.get("MOVO_SANDBOX_WORKSPACE_ROOT", "/workspaces"))
    root.mkdir(parents=True, exist_ok=True)
    if task_id:
        task_root = task_workspace(task_id)
        work = task_root / "work"
        work.mkdir(parents=True, exist_ok=True)
        temporary = work / "tmp"
        temporary.mkdir(exist_ok=True)
        task_root.chmod(0o777)
        work.chmod(0o777)
        temporary.chmod(0o777)
        yield work
        return
    path = root / uuid4().hex
    path.mkdir(mode=0o700)
    # The worker runs as an unprivileged UID and sees only this subdirectory.
    path.chmod(0o777)
    try:
        yield path
    finally:
        shutil.rmtree(path)


def child_path(path: Path, work_dir: Path) -> str:
    if not container_backend_enabled():
        return str(path)
    base = Path("/job/work") if work_dir.name == "work" else Path("/job")
    return str(base / path.relative_to(work_dir))


def run_script_job(
    *, work_dir: Path, runner_path: Path, plugin_path: Path, stdin_path: Path,
    env: dict[str, str], timeout_seconds: int, limit_child_process, skill_digest: str = "",
    task_id: str = "", call_id: str = "", execution_permit: str = "",
) -> subprocess.CompletedProcess[str]:
    if not container_backend_enabled():
        return subprocess.run(
            [os.sys.executable, "-I", str(runner_path), str(plugin_path), str(stdin_path)],
            cwd=str(work_dir), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout_seconds, preexec_fn=limit_child_process,
        )
    url = os.environ["MOVO_SANDBOX_MANAGER_URL"].rstrip("/")
    token = os.environ.get("MOVO_SANDBOX_MANAGER_TOKEN", "")
    if len(token) < 32:
        raise RuntimeError("Sandbox manager token is missing")
    if skill_digest:
        ((work_dir.parent if task_id else work_dir) / "skill-digest").write_text(skill_digest, encoding="ascii")
    with httpx.Client(timeout=timeout_seconds + 30, trust_env=False) as client:
        response = client.post(
            f"{url}/v1/script-task-calls" if task_id else f"{url}/v1/script-jobs",
            json={"task_id": task_key(task_id), "call_id": call_id, **({"execution_permit": execution_permit} if execution_permit else {})} if task_id else {"job_id": work_dir.name},
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.is_error:
            try:
                detail = str(response.json().get("detail") or "Sandbox job was rejected")
            except ValueError:
                detail = "Sandbox job was rejected"
            raise RuntimeError(detail)
        payload = response.json()
    completed = subprocess.CompletedProcess(
        args=["sandbox-script-job", work_dir.name],
        returncode=int(payload["exit_code"]),
        stdout=str(payload.get("stdout") or ""),
        stderr=str(payload.get("stderr") or ""),
    )
    completed.image_ref = str(payload.get("image_ref") or "")
    return completed
