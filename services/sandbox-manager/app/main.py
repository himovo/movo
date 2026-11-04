"""Narrow control-plane API for per-job containers."""

from __future__ import annotations

import hmac
import os
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .docker_engine import DockerEngine
from .jobs import ScriptJobs
from .plugin_runtimes import PluginRuntimes
from .skill_environments import DependencyPreparationError
from .skill_build_records import MAX_LOG_CHARS, SkillBuildRecords
from .task_containers import TaskContainers


@asynccontextmanager
async def lifespan(_app: FastAPI):
    SkillBuildRecords().recover_interrupted()
    yield


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
_jobs: ScriptJobs | None = None
_plugins: PluginRuntimes | None = None
_tasks: TaskContainers | None = None
_jobs_lock = threading.Lock()


def jobs() -> ScriptJobs:
    global _jobs
    with _jobs_lock:
        if _jobs is None:
            _jobs = ScriptJobs(DockerEngine())
    return _jobs


def plugins() -> PluginRuntimes:
    global _plugins
    with _jobs_lock:
        if _plugins is None:
            _plugins = PluginRuntimes(DockerEngine())
    return _plugins


def tasks() -> TaskContainers:
    global _tasks
    environments = jobs().environments
    with _jobs_lock:
        if _tasks is None:
            _tasks = TaskContainers(DockerEngine(), environments=environments)
    return _tasks


class ExecuteScriptRequest(BaseModel):
    job_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class ExecuteTaskCallRequest(BaseModel):
    task_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    call_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class CreatePluginRuntimeRequest(BaseModel):
    isolation_key: str = Field(min_length=1, max_length=512)


class UpdateSettingsRequest(BaseModel):
    max_pending: int = Field(ge=0, le=100)


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
    return {"ok": True, **jobs().status(), **plugins().status()}


@app.get("/v1/readiness")
def readiness(authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    from .readiness import script_readiness
    return script_readiness()


@app.post("/v1/script-jobs")
def run_script(payload: ExecuteScriptRequest, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    try:
        return jobs().execute(payload.job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DependencyPreparationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@app.post("/v1/script-task-calls")
def run_task_call(payload: ExecuteTaskCallRequest, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    try:
        return tasks().execute(payload.task_id, payload.call_id)
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


@app.put("/v1/settings")
def update_settings(payload: UpdateSettingsRequest, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    return jobs().set_max_pending(payload.max_pending)


@app.post("/v1/plugin-runtimes")
def create_plugin_runtime(payload: CreatePluginRuntimeRequest, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    return plugins().create(payload.isolation_key)


@app.delete("/v1/plugin-runtimes/{lease_id}")
def dispose_plugin_runtime(lease_id: str, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    plugins().dispose(lease_id)
    return {"disposed": True}
