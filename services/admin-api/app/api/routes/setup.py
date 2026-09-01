from __future__ import annotations

import secrets
import re
import asyncio
import os
import socket
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from app.api.time_utils import utc_iso
from app.core.config import settings
from app.core.db import get_db
from app.core.product_edition import ensure_community_organization
from app.core.security import hash_password
from app.repositories.directory_repository import (
    DEPARTMENT_COLLECTION,
    USER_COLLECTION,
    USER_ORG_REL_COLLECTION,
    ensure_root_department,
)
from app.repositories.org_user_repository import ensure_bootstrap_account, ensure_group_exists
from app.repositories.model_repository import ensure_indexes as ensure_model_indexes
from app.repositories.setup_repository import ensure_indexes, get_setup_state, mark_setup_completed
from app.position_roles.repository import PositionRoleRepository
from app.services.setup_model import (
    SetupModelError,
    create_setup_model,
    get_active_setup_providers,
    inspect_setup_model,
    test_setup_model,
)
from app.services.setup_cleanup import cleanup_failed_setup
from app.services.external_search_provider import ExternalSearchConfigError
from app.services.setup_external_search import (
    save_setup_search,
    setup_provider_catalog,
    test_setup_search,
)
from app.services.setup_quota import configure_setup_quotas
from app.services.setup_knowledge import configure_setup_knowledge_models

router = APIRouter()


class SetupServiceStatus(BaseModel):
    key: str
    label: str
    ok: bool
    message: str = ""


class SetupUrls(BaseModel):
    userWeb: str = ""
    adminWeb: str = ""
    desktopService: str = ""
    agentWebSocket: str = ""


class SetupStatusResponse(BaseModel):
    completed: bool
    orgName: str = ""
    mainId: str = ""
    initializedAt: str = ""
    ready: bool = False
    services: list[SetupServiceStatus] = Field(default_factory=list)
    urls: SetupUrls = Field(default_factory=SetupUrls)


class SetupModelRequest(BaseModel):
    providerId: str = Field(min_length=1)
    displayName: str = Field(min_length=1, max_length=80)
    modelName: str = Field(min_length=1, max_length=120)
    baseUrl: str = Field(min_length=1, max_length=300)
    apiVersion: str = Field(default="", max_length=40)
    apiKey: str = Field(min_length=1, max_length=600)
    capability: str = Field(default="chat", pattern=r"^(chat|embedding|rerank|vision|image)$")


class SetupExternalSearchRequest(BaseModel):
    provider: str = Field(pattern=r"^(tavily|serper|serpapi|baidu_qianfan|volc_ark)$")
    apiKey: str = Field(min_length=1, max_length=1000)
    endpoint: str = Field(default="", max_length=500)
    baseUrl: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=200)
    query: str = Field(default="MOVO enterprise AI", max_length=300)


class SetupInitRequest(BaseModel):
    orgName: str = Field(min_length=2, max_length=120)
    adminUsername: str = Field(min_length=3, max_length=64)
    adminPassword: str = Field(min_length=6, max_length=128)
    adminDisplayName: str = Field(default="系统管理员", min_length=2, max_length=64)
    employeeUsername: str = Field(min_length=3, max_length=64)
    employeePassword: str = Field(min_length=6, max_length=128)
    employeeName: str = Field(min_length=2, max_length=64)
    orgTotalTokens: int = Field(gt=0)
    defaultUserTokens: int = Field(gt=0)
    quotaPeriod: str = Field(default="monthly", pattern=r"^(monthly|daily|hourly)$")
    quotaTimezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=80)
    model: SetupModelRequest
    additionalModels: list[SetupModelRequest] = Field(default_factory=list, max_length=4)
    externalSearch: SetupExternalSearchRequest | None = None


def _fmt(value: datetime | None) -> str:
    return utc_iso(value)


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return cleaned or "org"


async def _next_main_id(org_name: str) -> str:
    db = get_db()
    base = _slug(org_name)[:12]
    for _ in range(12):
        candidate = f"{base}-{secrets.token_hex(12)}"
        exists = await db["admin_accounts"].find_one({"main_id": candidate}, {"_id": 1})
        if not exists:
            return candidate
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="main_id generation failed")


def _request_public_base(request: Request) -> str:
    configured = str(settings.public_base_url or "").strip().rstrip("/")
    if configured:
        return configured
    scheme = str(request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",", 1)[0].strip()
    host = str(request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc).split(",", 1)[0].strip()
    return f"{scheme}://{host}".rstrip("/")


def _connection_urls(request: Request) -> SetupUrls:
    base = _request_public_base(request)
    ws_base = f"wss://{base[8:]}" if base.startswith("https://") else f"ws://{base[7:]}" if base.startswith("http://") else base
    return SetupUrls(
        userWeb=f"{base}/",
        adminWeb=f"{base}/admin/",
        desktopService=base,
        agentWebSocket=f"{ws_base}/api/agent/connect",
    )


async def _probe_http(key: str, label: str, url: str) -> SetupServiceStatus:
    def request_url() -> None:
        with urllib.request.urlopen(url, timeout=2.5) as response:
            if int(response.status) >= 400:
                raise RuntimeError(f"HTTP {response.status}")

    try:
        await asyncio.to_thread(request_url)
        return SetupServiceStatus(key=key, label=label, ok=True, message="已就绪")
    except Exception as exc:
        return SetupServiceStatus(key=key, label=label, ok=False, message=str(exc)[:160])


async def _probe_mongo() -> SetupServiceStatus:
    try:
        await get_db().command("ping")
        return SetupServiceStatus(key="mongo", label="MongoDB", ok=True, message="已就绪")
    except Exception as exc:
        return SetupServiceStatus(key="mongo", label="MongoDB", ok=False, message=str(exc)[:160])


async def _probe_redis() -> SetupServiceStatus:
    parsed = urllib.parse.urlparse(str(settings.redis_url or "redis://127.0.0.1:6379/0"))

    def connect() -> None:
        with socket.create_connection((parsed.hostname or "127.0.0.1", parsed.port or 6379), timeout=2.5):
            return

    try:
        await asyncio.to_thread(connect)
        return SetupServiceStatus(key="redis", label="Redis", ok=True, message="已就绪")
    except Exception as exc:
        return SetupServiceStatus(key="redis", label="Redis", ok=False, message=str(exc)[:160])


async def _probe_storage() -> SetupServiceStatus:
    paths = [settings.knowledge_local_storage_dir, settings.admin_static_dir]
    try:
        for raw_path in paths:
            path = os.path.abspath(os.path.expanduser(str(raw_path)))
            os.makedirs(path, exist_ok=True)
            if not os.access(path, os.W_OK):
                raise PermissionError(f"目录不可写: {path}")
        return SetupServiceStatus(key="storage", label="持久化存储", ok=True, message="已就绪")
    except Exception as exc:
        return SetupServiceStatus(key="storage", label="持久化存储", ok=False, message=str(exc)[:160])


async def _deployment_services() -> list[SetupServiceStatus]:
    chat_health = f"{str(settings.backend_base_url).rstrip('/')}/ready"
    document_ready = f"{str(settings.document_processing_base_url).rstrip('/')}/api/ready"
    weaviate_ready = f"{str(settings.weaviate_endpoint).rstrip('/')}/v1/.well-known/ready"
    results = await asyncio.gather(
        _probe_mongo(),
        _probe_redis(),
        _probe_storage(),
        _probe_http("chat-api", "Chat API 与 DSH Runtime", chat_health),
        _probe_http("document-processing", "文档处理与 Worker", document_ready),
        _probe_http("weaviate", "Weaviate", weaviate_ready),
    )
    return list(results)


async def _ensure_setup_open() -> None:
    state = await get_setup_state()
    if state and bool(state.get("completed")):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="setup already completed")


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(request: Request) -> SetupStatusResponse:
    await ensure_indexes()
    state = await get_setup_state()
    services = await _deployment_services()
    common = {
        "ready": all(item.ok for item in services),
        "services": services,
        "urls": _connection_urls(request),
    }
    if not state or not bool(state.get("completed")):
        return SetupStatusResponse(completed=False, **common)
    return SetupStatusResponse(
        completed=True,
        orgName=str(state.get("org_name") or ""),
        mainId=str(state.get("main_id") or ""),
        initializedAt=_fmt(state.get("updated_at")),
        **common,
    )


@router.get("/model-providers")
async def setup_model_providers() -> list[dict[str, object]]:
    await _ensure_setup_open()
    await ensure_model_indexes()
    return await get_active_setup_providers()


@router.post("/model/test")
async def setup_model_test(payload: SetupModelRequest) -> dict[str, object]:
    await _ensure_setup_open()
    await ensure_model_indexes()
    try:
        message = await test_setup_model(payload.model_dump())
    except SetupModelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"success": True, "message": message}


@router.get("/search-providers")
async def setup_search_providers() -> list[dict[str, str]]:
    await _ensure_setup_open()
    return setup_provider_catalog()


@router.post("/search/test")
async def setup_search_test(payload: SetupExternalSearchRequest) -> dict[str, Any]:
    await _ensure_setup_open()
    try:
        results = await test_setup_search(payload.model_dump())
    except ExternalSearchConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)[:1000]) from exc
    if not results:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="搜索服务未返回结果")
    return {"success": True, "message": "搜索连接测试成功", "resultCount": len(results)}


@router.post("/initialize")
async def setup_initialize(payload: SetupInitRequest) -> dict[str, Any]:
    await ensure_indexes()
    await _ensure_setup_open()
    await ensure_model_indexes()

    services = await _deployment_services()
    unavailable = [item.label for item in services if not item.ok]
    if unavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"以下服务尚未就绪：{', '.join(unavailable)}",
        )

    if payload.adminUsername.strip() == payload.employeeUsername.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="管理员账号和员工账号不能相同")
    if payload.defaultUserTokens > payload.orgTotalTokens:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="员工默认 Token 不能超过企业总 Token")
    if payload.model.capability != "chat":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="基础对话模型能力必须为 chat")
    capabilities = [item.capability for item in payload.additionalModels]
    if len(capabilities) != len(set(capabilities)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="每种可选模型只能配置一个")
    if any(item == "chat" for item in capabilities):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="可选模型不能重复配置 chat 能力")

    embedding_dimension: int | None = None
    try:
        await inspect_setup_model(payload.model.model_dump())
        for item in payload.additionalModels:
            if item.capability in {"embedding", "rerank"}:
                inspection = await inspect_setup_model(item.model_dump())
                if item.capability == "embedding":
                    embedding_dimension = inspection.dimension
    except SetupModelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if payload.externalSearch is not None:
        try:
            search_results = await test_setup_search(payload.externalSearch.model_dump())
        except ExternalSearchConfigError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"搜索连接测试失败：{str(exc)[:800]}") from exc
        if not search_results:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="搜索服务未返回结果")

    main_id = await _next_main_id(payload.orgName)
    org_name = payload.orgName.strip()
    now = datetime.now(timezone.utc)

    try:
        await ensure_group_exists(
            name="系统管理员",
            code="system_admin",
            main_id=main_id,
            description="系统内置账号组",
        )
        await ensure_bootstrap_account(
            main_id=main_id,
            username=payload.adminUsername.strip(),
            password=payload.adminPassword,
            display_name=payload.adminDisplayName.strip(),
            role_name="平台超级管理员",
            org_name=org_name,
            group_code="system_admin",
        )

        await ensure_root_department(main_id)
        db = get_db()
        root = await db[DEPARTMENT_COLLECTION].find_one({"main_id": main_id, "code": "root"})
        if not root:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="root department init failed")
        root_id = str(root["_id"])

        password_hash, password_salt = hash_password(payload.employeePassword)
        try:
            result = await db[USER_COLLECTION].insert_one(
                {
                    "main_id": main_id,
                    "name": payload.employeeName.strip(),
                    "mobile": "",
                    "email": "",
                    "status": "active",
                    "source": "local",
                    "source_user_id": "",
                    "primary_org_id": root_id,
                    "login_name": payload.employeeUsername.strip(),
                    "password_hash": password_hash,
                    "password_salt": password_salt,
                    "org_name": org_name,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        except DuplicateKeyError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="员工登录名已存在") from exc

        user_id = str(result.inserted_id)
        await ensure_community_organization(
            main_id=main_id,
            org_name=org_name,
            owner_user_id=user_id,
            total_points=payload.orgTotalTokens,
        )
        await db[USER_ORG_REL_COLLECTION].insert_one(
            {
                "main_id": main_id,
                "user_id": user_id,
                "org_id": root_id,
                "is_primary": True,
                "created_at": now,
                "updated_at": now,
            }
        )

        position_roles = PositionRoleRepository(db)
        await position_roles.ensure_indexes()
        full_access_role = await position_roles.ensure_full_access_role(main_id)
        await position_roles.assign_role(
            main_id,
            user_id,
            str(full_access_role["_id"]),
            primary=True,
            actor=payload.adminUsername.strip(),
        )
        await position_roles.complete_migration(main_id, payload.adminUsername.strip())

        await configure_setup_quotas(
            main_id=main_id,
            total_tokens=payload.orgTotalTokens,
            default_user_tokens=payload.defaultUserTokens,
            period=payload.quotaPeriod,
            timezone_name=payload.quotaTimezone,
            operator=payload.adminUsername.strip(),
        )
        model_instance_id = await create_setup_model(payload.model.model_dump(), main_id)
        additional_model_ids = [
            await create_setup_model(item.model_dump(), main_id)
            for item in payload.additionalModels
        ]
        await configure_setup_knowledge_models(
            main_id=main_id,
            configured_models=[
                (item.model_dump(), instance_id)
                for item, instance_id in zip(payload.additionalModels, additional_model_ids)
            ],
            operator=payload.adminUsername.strip(),
            embedding_dimension=embedding_dimension,
        )
        if payload.externalSearch is not None:
            await save_setup_search(payload.externalSearch.model_dump(), main_id)

        await mark_setup_completed(
            main_id=main_id,
            org_name=org_name,
            admin_username=payload.adminUsername.strip(),
            employee_username=payload.employeeUsername.strip(),
        )
    except Exception as exc:
        await cleanup_failed_setup(main_id)
        if isinstance(exc, SetupModelError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raise
    return {
        "completed": True,
        "mainId": main_id,
        "orgName": org_name,
        "modelInstanceId": model_instance_id,
        "additionalModelInstanceIds": additional_model_ids,
    }
