"""Narrow control-plane API for per-job containers."""

from __future__ import annotations

from typing import Literal

import asyncio
import hmac
import os
import threading
from uuid import uuid4
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .execution_workers import run_script_work
from .execution_permits import ExecutionPermits
from .resident_capacity import ResidentCapacity
from .permit_markers import PermitMarkers
from .storage_paths import manager_state_root
from .execution_permit_routes import permit_router
from .docker_engine import DockerEngine
from .jobs import ScriptJobs
from .plugin_runtimes import PluginRuntimes
from .skill_environments import DependencyPreparationError
from .skill_build_records import MAX_LOG_CHARS, SkillBuildRecords
from .task_containers import TaskContainers
from .offline_routes import router as offline_router
from .image_archive_routes import router as image_archive_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    SkillBuildRecords().recover_interrupted()
    await run_script_work(lambda: tasks().recover_interrupted())
    await run_script_work(lambda: permits().markers.recover(plugins().recover_interrupted_owner))
    async def reap():
        while True:
            await asyncio.sleep(10)
            if _permits is not None:
                await run_script_work(lambda: _permits.expire(on_expire=plugins().recover_interrupted_owner))
    reaper = asyncio.create_task(reap())
    try:
        yield
    finally:
        reaper.cancel()
        await asyncio.gather(reaper, return_exceptions=True)


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.include_router(offline_router)
app.include_router(image_archive_router)
_jobs: ScriptJobs | None = None
_plugins: PluginRuntimes | None = None
_tasks: TaskContainers | None = None
_resident_capacity = ResidentCapacity(int(os.environ.get("MOVO_SANDBOX_MAX_TASKS", "10")))
_permits = None
_permits_lock = threading.Lock()
_jobs_lock = threading.Lock()
_tasks_lock = threading.Lock()
_plugins_lock = threading.Lock()
_instance_id = uuid4().hex


def jobs() -> ScriptJobs:
    global _jobs
    with _jobs_lock:
        if _jobs is None:
            _jobs = ScriptJobs(DockerEngine(), residents=_resident_capacity)
    return _jobs


def permits() -> ExecutionPermits:
    global _permits
    scheduler = jobs().scheduler
    with _permits_lock:
        if _permits is None:
            _permits = ExecutionPermits(scheduler, markers=PermitMarkers(manager_state_root()))
    return _permits


def plugins() -> PluginRuntimes:
    global _plugins
    admission = permits()
    with _plugins_lock:
        if _plugins is None:
            _plugins = PluginRuntimes(DockerEngine(), scheduler=admission.scheduler, permits=admission, residents=_resident_capacity)
    return _plugins


def tasks() -> TaskContainers:
    global _tasks
    script_jobs = jobs()
    environments = script_jobs.environments
    with _tasks_lock:
        if _tasks is None:
            _tasks = TaskContainers(DockerEngine(), environments=environments, scheduler=script_jobs.scheduler, permits=permits(), residents=_resident_capacity)
    return _tasks


class ExecuteScriptRequest(BaseModel):
    job_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class ExecuteTaskCallRequest(BaseModel):
    task_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    call_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    execution_permit: str = Field(default="", max_length=128)


class CreatePluginRuntimeRequest(BaseModel):
    isolation_key: str = Field(min_length=1, max_length=512)
    personal_space_key: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    startup_guard: bool = False


class UpdateSettingsRequest(BaseModel):
    runtime_mode: Literal["on_demand", "forced"] | None = None
    plugin_idle_seconds: int | None = Field(default=None, ge=0, le=604800)
    max_pending: int | None = Field(default=None, ge=0, le=100)
    capacity: int | None = Field(default=None, ge=1, le=100)


class PrepareSkillRequest(BaseModel):
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def _authorize(authorization: str | None) -> None:
    token = os.environ["MOVO_SANDBOX_MANAGER_TOKEN"]
    supplied = (authorization or "").removeprefix("Bearer ")
    if not token or not hmac.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health(authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    try:
        DockerEngine().request("GET", "/_ping")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Docker Engine unavailable") from exc
    return {"ok": True, **jobs().status(), **jobs().scheduler.runtime_policy(), **plugins().status(), **_resident_capacity.status(),
            "task_capacity": _tasks.capacity if _tasks is not None else int(os.environ.get("MOVO_SANDBOX_MAX_TASKS", "10"))}


@app.get("/v1/readiness")
def readiness(authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    from .readiness import script_readiness
    return script_readiness()


@app.get("/v1/skill-environments/base")
def skill_environment_base(authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    image = os.environ.get("MOVO_SANDBOX_SCRIPT_IMAGE", "").strip()
    engine = DockerEngine()
    try:
        return {"instanceId": _instance_id, "baseImageId": engine.image_id(image) if image else ""}
    finally:
        engine.client.close()


@app.post("/v1/script-jobs")
async def run_script(payload: ExecuteScriptRequest, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    try:
        return await run_script_work(lambda: jobs().execute(payload.job_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DependencyPreparationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@app.post("/v1/script-task-calls")
async def run_task_call(payload: ExecuteTaskCallRequest, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    try:
        return await run_script_work(lambda: tasks().execute(payload.task_id, payload.call_id, execution_permit=payload.execution_permit))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DependencyPreparationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@app.delete("/v1/script-tasks/{task_id}")
def dispose_task(task_id: str, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    try:
        tasks().dispose(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"disposed": True}


@app.post("/v1/script-tasks/{task_id}/freeze")
def freeze_task(task_id: str, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    try:
        tasks().freeze(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"frozen": True}


@app.post("/v1/skill-environments", status_code=202)
def prepare_skill(payload: PrepareSkillRequest, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    try:
        return {"status": jobs().environments.start(payload.digest, retry_failed=True)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/skill-environments/{digest}")
def skill_environment_status(digest: str, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    try:
        return {"status": jobs().environments.status(digest)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/skill-environments/{digest}/records")
def skill_environment_records(digest: str, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    try:
        return {"items": jobs().environments.records.list(digest)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/skill-environments/{digest}/records/{record_id}")
def skill_environment_record(digest: str, record_id: str, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    try:
        record = jobs().environments.records.get(digest, record_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Preparation record not found")
    if record["status"] == "preparing":
        try:
            live = jobs().environments.live_output(digest)
            combined = record["log"] + live
            record["truncated"] = record["truncated"] or len(combined) > MAX_LOG_CHARS
            record["log"] = combined[-MAX_LOG_CHARS:]
        except Exception:
            pass
    return record


@app.get("/v1/settings")
def get_settings(authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    return jobs().scheduler.runtime_policy()


@app.put("/v1/settings")
def update_settings(payload: UpdateSettingsRequest, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    return jobs().scheduler.configure(**payload.model_dump(exclude_none=True))


@app.post("/v1/plugin-runtimes")
async def create_plugin_runtime(payload: CreatePluginRuntimeRequest, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    try:
        return await run_script_work(lambda: plugins().create(
            payload.isolation_key, payload.personal_space_key, startup_guard=payload.startup_guard))
    except RuntimeError as exc:
        raise HTTPException(429, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/v1/plugin-runtimes/{lease_id}")
async def dispose_plugin_runtime(lease_id: str, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    await run_script_work(lambda: plugins().dispose(lease_id))
    return {"disposed": True}


app.include_router(permit_router(_authorize, permits))
