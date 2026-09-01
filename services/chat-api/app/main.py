from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging
import os
import sys
import time
import uuid

from app.core.db import close_db, get_db, init_db
from app.core.config import get_settings
from app.infrastructure.observability.config import configure_logging
from app.infrastructure.observability.spans import log_span
from app.infrastructure.request_context import merge_request_context, reset_request_context
from app.infrastructure.runtime_services import action_receipt_store, token_usage_dispatcher
from pymongo.errors import OperationFailure


def _ensure_utf8_stdio() -> None:
    # Some runtime shells default to ASCII and crash when logging Chinese text.
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_ensure_utf8_stdio()

settings = get_settings()
configure_logging(settings)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MOVO Backend",
    description="API for Multi-Agent Platform",
    version="0.1.0"
)
_receipt_gc_task: asyncio.Task | None = None

origins = settings.allowed_origins_list()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def request_logging_middleware(request, call_next):
    http_request_id = request.headers.get("X-Request-ID") or f"http_{uuid.uuid4().hex[:12]}"
    started_at = time.monotonic()
    previous_context = merge_request_context(
        {
            "http_request_id": http_request_id,
            "method": request.method,
            "path": request.url.path,
        }
    )
    logger.info(
        "http request started",
        extra={
            "event": "http.request_started",
            "http_request_id": http_request_id,
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else "",
        },
    )
    try:
        async with log_span("http.request", method=request.method, path=request.url.path):
            response = await call_next(request)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        response.headers["X-Request-ID"] = http_request_id
        logger.info(
            "http request completed",
            extra={
                "event": "http.request_completed",
                "http_request_id": http_request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
    except Exception:
        duration_ms = int((time.monotonic() - started_at) * 1000)
        logger.exception(
            "http request failed",
            extra={
                "event": "http.request_failed",
                "http_request_id": http_request_id,
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
            },
        )
        raise
    finally:
        reset_request_context(previous_context)

from app.api.endpoints import (
    auth,
    dsh_chat,
    debug,
    documents,
    dsh_model_gateway,
    dsh_tool_gateway,
    external_tools,
    knowledge_sources,
    models,
    projects,
    quota,
    scheduled_tasks,
    sessions,
    site_profiles,
    skills,
    tasks,
    token_usage,
)
from app.scheduled_tasks import scheduled_task_scheduler
from app.governance.suspensions import suspension_service
from app.browser import ws_endpoint as browser_ws_endpoint

app.include_router(dsh_chat.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(debug.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(knowledge_sources.router, prefix="/api")
app.include_router(external_tools.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(skills.router, prefix="/api")
app.include_router(site_profiles.router, prefix="/api")
app.include_router(token_usage.router, prefix="/api")
app.include_router(quota.router, prefix="/api")
app.include_router(scheduled_tasks.router, prefix="/api")
app.include_router(browser_ws_endpoint.router, prefix="/api")
app.include_router(dsh_model_gateway.router)
app.include_router(dsh_tool_gateway.internal_router)
app.include_router(dsh_tool_gateway.public_router, prefix="/api")

if settings.ENABLE_DEMO_ENDPOINTS:
    from app.api.endpoints import (
        mock_manufacturing,
        mock_sales_review,
        mock_store_audit,
        mock_store_diagnosis,
    )

    app.include_router(mock_manufacturing.router, prefix="/api")
    app.include_router(mock_sales_review.router, prefix="/api")
    app.include_router(mock_store_audit.router, prefix="/api")
    app.include_router(mock_store_diagnosis.router, prefix="/api")

async def _ensure_end_user_login_name_index(db) -> None:
    desired_key = {"main_id": 1, "login_name": 1}
    async for index in db.end_users.list_indexes():
        if index.get("key") == desired_key and index.get("unique") is True:
            logger.info(
                "reusing existing end_users login_name unique index",
                extra={
                    "event": "db.index.reused",
                    "collection": "end_users",
                    "index_name": index.get("name", ""),
                },
            )
            return
    try:
        await db.end_users.create_index(
            [("main_id", 1), ("login_name", 1)],
            unique=True,
            name="user_main_login_name_unique",
            partialFilterExpression={"login_name": {"$exists": True, "$type": "string"}},
        )
    except OperationFailure as exc:
        if getattr(exc, "code", None) == 85:
            logger.warning(
                "end_users login_name unique index already exists with different options; reusing it",
                extra={
                    "event": "db.index.reused_conflict",
                    "collection": "end_users",
                    "error": str(exc),
                },
            )
            return
        raise

@app.on_event("startup")
async def startup_event() -> None:
    global _receipt_gc_task
    init_db()
    db = get_db()
    # Keep session history list query fast: find by user_id and sort by updated_at desc.
    await db.chat_sessions.create_index([("user_id", 1), ("updated_at", -1)])
    await db.chat_sessions.create_index([("user_id", 1), ("updated_at", -1), ("_id", -1)])
    await db.chat_sessions.create_index([("user_id", 1), ("created_at", -1)])
    await db.chat_sessions.create_index([("main_id", 1), ("user_id", 1), ("updated_at", -1)])
    await db.chat_sessions.create_index([("main_id", 1), ("user_id", 1), ("updated_at", -1), ("_id", -1)])
    await db.chat_messages.create_index([("main_id", 1), ("user_id", 1), ("session_id", 1), ("seq", 1)])
    await db.execution_logs.create_index([("main_id", 1), ("session_id", 1), ("message_id", 1)])
    await db.user_skills.create_index([("main_id", 1), ("user_id", 1), ("created_at", -1)])
    await db.site_profiles.create_index([("main_id", 1), ("owner_user_id", 1), ("updated_at", -1)])
    await db.external_tools.create_index([("main_id", 1), ("updated_at", -1)])
    await db.external_tools.create_index([("main_id", 1), ("status", 1), ("type", 1)])
    await db.external_tools.create_index([("main_id", 1), ("scope", 1), ("owner_user_id", 1), ("updated_at", -1)])
    await db.project_memories.create_index([("main_id", 1), ("user_id", 1), ("project_id", 1), ("key", 1)])
    await db.desktop_projects.create_index([("main_id", 1), ("user_id", 1), ("workspace_id", 1)], unique=True)
    await db.desktop_projects.create_index([("main_id", 1), ("user_id", 1), ("updated_at", -1)])
    await db.token_usage_logs.create_index([("main_id", 1), ("user_id", 1), ("created_at", -1)])
    await db.token_usage_logs.create_index([("session_id", 1), ("created_at", -1)])
    await db.token_usage_logs.create_index([("trace_id", 1), ("created_at", -1)])
    await db.token_usage_logs.create_index([("user_request_id", 1), ("created_at", -1)])
    await db.token_usage_logs.create_index("request_id", unique=True)
    await _ensure_end_user_login_name_index(db)
    await db.end_user_sessions.create_index([("token_id", 1)], unique=True)
    await db.end_user_sessions.create_index([("main_id", 1), ("user_id", 1), ("status", 1), ("expires_at", -1)])
    await db.end_user_sessions.create_index([("expires_at", 1)], expireAfterSeconds=0)
    await db.end_user_login_challenges.create_index([("challenge_token", 1)], unique=True)
    await db.end_user_login_challenges.create_index([("expires_at", 1)], expireAfterSeconds=0)
    from app.dsh_runtime.application import dsh_runtime_application
    await dsh_runtime_application.start()
    await action_receipt_store.ensure_indexes()
    await suspension_service.store.ensure_indexes()
    await action_receipt_store.recover_stale_running()
    await action_receipt_store.reconcile_abandoned()
    await token_usage_dispatcher.start()
    await scheduled_task_scheduler.start()
    async def _receipt_gc_loop() -> None:
        while True:
            try:
                await action_receipt_store.recover_stale_running()
                await action_receipt_store.reconcile_abandoned()
            except Exception:
                pass
            await asyncio.sleep(60)
    _receipt_gc_task = asyncio.create_task(_receipt_gc_loop())
    settings = get_settings()
    logger.info(
        "application startup complete",
        extra={
            "event": "app.startup",
            "debug": settings.DEBUG,
            "use_azure": settings.USE_AZURE,
            "azure_deployment": settings.AZURE_DEPLOYMENT_NAME,
            "pipeline_mode": settings.PIPELINE_MODE,
        },
    )


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global _receipt_gc_task
    if _receipt_gc_task is not None:
        _receipt_gc_task.cancel()
        _receipt_gc_task = None
    await scheduled_task_scheduler.stop()
    await token_usage_dispatcher.stop()
    from app.dsh_runtime.application import dsh_runtime_application
    await dsh_runtime_application.stop()
    close_db()

@app.get("/health")
async def health_check():
    """Health check endpoint to verify backend status."""
    from app.dsh_runtime.application import dsh_runtime_application
    dsh_healthy = await dsh_runtime_application.probe_host()
    return {
        "status": "ok",
        "version": "0.1.0",
        "service": "MOVO Backend",
        "agent_kernel": "dsh",
        "dsh_host": "healthy" if dsh_healthy else "degraded",
    }


@app.get("/ready")
async def readiness_check():
    """Readiness requires the out-of-process DSH kernel used by every chat turn."""
    from app.dsh_runtime.application import dsh_runtime_application
    if not await dsh_runtime_application.probe_host():
        raise HTTPException(status_code=503, detail="DSH Runtime Host is unavailable")
    return {
        "status": "ready",
        "service": "MOVO Backend",
        "agent_kernel": "dsh",
        "dsh_host": "healthy",
    }

@app.get("/")
async def root():
    return {"message": "Welcome to MOVO Agent Platform API"}
