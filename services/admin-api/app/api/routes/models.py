from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
import asyncio
from datetime import datetime
from typing import Any, Iterator

try:
    import certifi
except Exception:  # pragma: no cover - optional dependency
    certifi = None

from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError
from starlette.responses import StreamingResponse

from app.api.deps import get_current_admin_user
from app.api.time_utils import utc_iso
from app.core.config import settings
from app.repositories.model_repository import (
    create_instance,
    delete_instance,
    decrypt_secret,
    find_instance_by_id,
    find_provider_by_id,
    list_instances,
    list_providers,
    set_default_instance,
    update_instance_health,
    update_instance,
)
from app.services.model_connectivity import backend_model_test_events, next_event

router = APIRouter()


def _as_time(value: datetime | None) -> str:
    return utc_iso(value)


def _format_provider(doc: dict[str, Any]) -> dict[str, object]:
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "code": doc.get("code", ""),
        "providerType": doc.get("provider_type", "openai_compatible"),
        "defaultBaseUrl": doc.get("default_base_url", ""),
        "authType": doc.get("auth_type", "bearer"),
        "status": doc.get("status", "active"),
        "updatedAt": _as_time(doc.get("updated_at")),
    }


def _format_instance(doc: dict[str, Any], provider_map: dict[str, dict[str, Any]]) -> dict[str, object]:
    provider_id = str(doc.get("provider_id", ""))
    provider = provider_map.get(provider_id, {})
    return {
        "id": str(doc["_id"]),
        "mainId": doc.get("main_id", ""),
        "providerId": provider_id,
        "providerName": provider.get("name", ""),
        "providerCode": provider.get("code", ""),
        "providerType": provider.get("provider_type", "openai_compatible"),
        "orgId": doc.get("org_id", ""),
        "displayName": doc.get("display_name", ""),
        "modelName": doc.get("model_name", ""),
        "baseUrl": doc.get("base_url", "") or provider.get("default_base_url", ""),
        "apiVersion": doc.get("api_version", ""),
        "apiKeyMasked": doc.get("api_key_masked", ""),
        "apiSecretMasked": doc.get("api_secret_masked", ""),
        "capabilities": doc.get("capabilities", []),
        "maxContextTokens": doc.get("max_context_tokens", 0),
        "status": doc.get("status", "active"),
        "healthStatus": doc.get("health_status", "unknown"),
        "lastError": doc.get("last_error", ""),
        "isDefault": bool(doc.get("is_default", False)),
        "priority": doc.get("priority", 100),
        "updatedAt": _as_time(doc.get("updated_at")),
    }


class ModelInstancePayload(BaseModel):
    providerId: str = Field(min_length=1)
    orgId: str = Field(default="", max_length=80)
    displayName: str = Field(min_length=1, max_length=80)
    modelName: str = Field(min_length=1, max_length=120)
    baseUrl: str = Field(default="", max_length=300)
    apiVersion: str = Field(default="", max_length=40)
    apiKey: str = Field(default="", max_length=600)
    apiSecret: str = Field(default="", max_length=600)
    capabilities: list[str] = Field(default_factory=lambda: ["chat"])
    maxContextTokens: int = Field(default=0, ge=0, le=5000000)
    status: str = Field(default="active", pattern=r"^(active|disabled)$")
    isDefault: bool = False
    priority: int = Field(default=100, ge=1, le=999)


class ModelTestPayload(BaseModel):
    prompt: str = Field(default="请用一句话回复当前模型连接测试。", max_length=500)


@router.get("/providers")
async def get_model_providers(current_user: dict = Depends(get_current_admin_user)) -> list[dict[str, object]]:
    del current_user
    providers = await list_providers()
    return [_format_provider(item) for item in providers]


@router.get("/instances")
async def get_model_instances(current_user: dict = Depends(get_current_admin_user)) -> list[dict[str, object]]:
    main_id = str(current_user.get("main_id", "default"))
    providers = await list_providers()
    provider_map = {str(item["_id"]): item for item in providers}
    instances = await list_instances(main_id)
    return [_format_instance(item, provider_map) for item in instances]


@router.get("/available")
async def get_available_chat_models(
    main_id: str = "default",
    current_user: dict = Depends(get_current_admin_user),
) -> list[dict[str, object]]:
    main_id = str(current_user.get("main_id") or main_id or "default")
    providers = await list_providers()
    provider_map = {str(item["_id"]): item for item in providers}
    instances = await list_instances(str(main_id or "default"))
    result: list[dict[str, object]] = []
    for item in instances:
        if item.get("status") != "active":
            continue
        capabilities = list(item.get("capabilities") or [])
        if "chat" not in capabilities and "text" not in capabilities:
            continue
        formatted = _format_instance(item, provider_map)
        result.append(
            {
                "id": formatted["id"],
                "displayName": formatted["displayName"],
                "modelName": formatted["modelName"],
                "providerName": formatted["providerName"],
                "providerType": formatted["providerType"],
                "isDefault": formatted["isDefault"],
                "healthStatus": formatted["healthStatus"],
            }
        )
    return result


@router.post("/instances", status_code=status.HTTP_201_CREATED)
async def post_model_instance(
    payload: ModelInstancePayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, object]:
    main_id = str(current_user.get("main_id", "default"))
    try:
        provider = await find_provider_by_id(payload.providerId)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="供应商ID无效") from exc
    if provider is None or provider.get("status") != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="供应商不存在或已禁用")
    if not payload.apiKey.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API Key 不能为空")

    try:
        instance_id = await create_instance(
            {
                **payload.model_dump(),
                "provider_id": payload.providerId,
                "org_id": payload.orgId,
                "display_name": payload.displayName,
                "model_name": payload.modelName,
                "base_url": payload.baseUrl,
                "api_version": payload.apiVersion,
                "api_key": payload.apiKey,
                "api_secret": payload.apiSecret,
                "max_context_tokens": payload.maxContextTokens,
                "is_default": payload.isDefault,
                "main_id": main_id,
            }
        )
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="模型配置已存在") from exc

    created = await find_instance_by_id(instance_id, main_id)
    if created is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="模型配置创建失败")
    providers = await list_providers()
    provider_map = {str(item["_id"]): item for item in providers}
    return _format_instance(created, provider_map)


@router.put("/instances/{instance_id}")
async def put_model_instance(
    instance_id: str,
    payload: ModelInstancePayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, object]:
    main_id = str(current_user.get("main_id", "default"))
    try:
        provider = await find_provider_by_id(payload.providerId)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="供应商ID无效") from exc
    if provider is None or provider.get("status") != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="供应商不存在或已禁用")

    try:
        ok = await update_instance(
            instance_id,
            {
                **payload.model_dump(),
                "provider_id": payload.providerId,
                "org_id": payload.orgId,
                "display_name": payload.displayName,
                "model_name": payload.modelName,
                "base_url": payload.baseUrl,
                "api_version": payload.apiVersion,
                "api_key": payload.apiKey,
                "api_secret": payload.apiSecret,
                "max_context_tokens": payload.maxContextTokens,
                "is_default": payload.isDefault,
                "main_id": main_id,
            },
        )
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模型配置ID无效") from exc
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="模型配置已存在") from exc
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型配置不存在")

    updated = await find_instance_by_id(instance_id, main_id)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型配置不存在")
    providers = await list_providers()
    provider_map = {str(item["_id"]): item for item in providers}
    return _format_instance(updated, provider_map)


@router.delete("/instances/{instance_id}")
async def remove_model_instance(
    instance_id: str,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, bool]:
    main_id = str(current_user.get("main_id", "default"))
    try:
        ok = await delete_instance(instance_id, main_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模型配置ID无效") from exc
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型配置不存在")
    return {"success": True}


@router.post("/instances/{instance_id}/default")
async def make_default_model_instance(
    instance_id: str,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, bool]:
    main_id = str(current_user.get("main_id", "default"))
    try:
        ok = await set_default_instance(instance_id, main_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模型配置ID无效") from exc
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型配置不存在")
    return {"success": True}


@router.post("/instances/{instance_id}/test")
async def test_model_instance(
    instance_id: str,
    payload: ModelTestPayload | None = None,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, object]:
    main_id = str(current_user.get("main_id", "default"))
    try:
        instance = await find_instance_by_id(instance_id, main_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模型配置ID无效") from exc
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型配置不存在")
    prompt = (payload.prompt if payload else "") or "请用一句话回复当前模型连接测试。"
    result_text = ""
    error_text = ""
    for event in backend_model_test_events(instance_id, main_id, prompt):
        if event["type"] == "delta":
            result_text += str(event.get("content") or "")
        elif event["type"] == "error":
            error_text = str(event.get("message") or "模型连接测试失败")
            break
    if error_text:
        await update_instance_health(instance_id, main_id, "failed", error_text)
        return {"success": False, "status": "failed", "message": error_text}
    return {
        "success": True,
        "status": "healthy",
        "message": result_text or "模型连接测试成功。",
    }


@router.post("/instances/{instance_id}/test/stream")
async def stream_model_instance_test(
    instance_id: str,
    payload: ModelTestPayload,
    current_user: dict = Depends(get_current_admin_user),
) -> StreamingResponse:
    main_id = str(current_user.get("main_id", "default"))
    try:
        instance = await find_instance_by_id(instance_id, main_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模型配置ID无效") from exc
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型配置不存在")
    async def event_stream():
        final_text = ""
        await update_instance_health(instance_id, main_id, "unknown", "")
        yield _sse({"type": "start", "message": "正在连接 backend 模型运行时..."})
        iterator = backend_model_test_events(instance_id, main_id, payload.prompt)
        while True:
            has_event, event = await asyncio.to_thread(next_event, iterator)
            if not has_event:
                break
            if event["type"] == "delta":
                final_text += str(event.get("content") or "")
            if event["type"] == "error":
                await update_instance_health(instance_id, main_id, "failed", str(event.get("message") or ""))
                yield _sse(event)
                return
            yield _sse(event)
        await update_instance_health(instance_id, main_id, "healthy", "")
        yield _sse({"type": "done", "message": final_text or "模型连接测试成功。"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: dict[str, object] | None) -> str:
    return f"data: {json.dumps(event or {}, ensure_ascii=False)}\n\n"


def _provider_test_events(
    instance: dict[str, Any],
    provider: dict[str, Any],
    prompt: str,
) -> Iterator[dict[str, object]]:
    provider_type = str(provider.get("provider_type") or "openai_compatible").strip()
    if provider_type == "azure_openai":
        return _azure_openai_test_events(instance, provider, prompt)
    return _openai_compatible_test_events(instance, provider, prompt)


def _iter_sse_response_chunks(
    request: urllib.request.Request,
) -> Iterator[dict[str, object]]:
    context = _build_ssl_context()
    with urllib.request.urlopen(request, timeout=60, context=context) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") if isinstance(chunk, dict) else None
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content") or delta.get("reasoning_content") or ""
            if content:
                yield {"type": "delta", "content": content}


def _is_max_tokens_unsupported(exc: urllib.error.HTTPError) -> bool:
    if exc.code != 400:
        return False
    try:
        detail = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return False
    text = detail.lower()
    return "unsupported parameter" in text and "max_tokens" in text and "max_completion_tokens" in text


def _is_temperature_value_unsupported(exc: urllib.error.HTTPError) -> bool:
    if exc.code != 400:
        return False
    try:
        detail = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return False
    text = detail.lower()
    return "unsupported value" in text and "temperature" in text and "default (1)" in text


def _stream_chat_completion_with_token_fallback(
    url: str,
    headers: dict[str, str],
    body: dict[str, object],
) -> Iterator[dict[str, object]]:
    current_body = dict(body)
    for _ in range(3):
        request = urllib.request.Request(
            url,
            data=json.dumps(current_body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            yield from _iter_sse_response_chunks(request)
            return
        except urllib.error.HTTPError as exc:
            if _is_max_tokens_unsupported(exc):
                max_tokens = current_body.pop("max_tokens", None)
                if max_tokens is not None and "max_completion_tokens" not in current_body:
                    current_body["max_completion_tokens"] = max_tokens
                continue
            if _is_temperature_value_unsupported(exc):
                current_body["temperature"] = 1
                continue
            raise


def _build_ssl_context() -> ssl.SSLContext:
    if settings.model_test_insecure_skip_verify:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    if settings.model_test_ca_bundle.strip():
        return ssl.create_default_context(cafile=settings.model_test_ca_bundle.strip())
    # Prefer certifi bundle when available to avoid local system trust-store issues.
    if certifi is not None:
        try:
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
    return ssl.create_default_context()


def _format_url_error(exc: urllib.error.URLError) -> str:
    reason_text = str(exc.reason)
    if "CERTIFICATE_VERIFY_FAILED" in reason_text:
        return (
            "模型接口 TLS 证书校验失败。"
            "请在 admin/api 环境变量配置 ASKAI_ADMIN_MODEL_TEST_CA_BUNDLE=<CA证书路径>；"
            "仅开发环境可临时设置 ASKAI_ADMIN_MODEL_TEST_INSECURE_SKIP_VERIFY=true。"
            f" 原始错误: {reason_text}"
        )
    return f"模型接口连接失败: {reason_text}"


def _decrypt_api_key(instance: dict[str, Any]) -> tuple[str, str]:
    api_key_encrypted = str(instance.get("api_key_encrypted") or "")
    try:
        return decrypt_secret(api_key_encrypted), ""
    except Exception:
        return "", "API Key 解密失败，请重新保存模型配置"


def _azure_openai_test_events(
    instance: dict[str, Any],
    provider: dict[str, Any],
    prompt: str,
) -> Iterator[dict[str, object]]:
    deployment = str(instance.get("model_name") or "").strip()
    endpoint = str(instance.get("base_url") or provider.get("default_base_url") or "").strip().rstrip("/")
    api_version = str(instance.get("api_version") or "").strip() or "2024-10-21"
    api_key, key_error = _decrypt_api_key(instance)
    if key_error:
        yield {"type": "error", "message": key_error}
        return
    if not deployment:
        yield {"type": "error", "message": "Azure Deployment 名称不能为空（使用模型 ID 字段填写）"}
        return
    if not endpoint:
        yield {"type": "error", "message": "Azure Endpoint 不能为空"}
        return
    if not api_key:
        yield {"type": "error", "message": "API Key 不能为空"}
        return

    path_deployment = urllib.parse.quote(deployment, safe="")
    query = urllib.parse.urlencode({"api-version": api_version})
    url = f"{endpoint}/openai/deployments/{path_deployment}/chat/completions?{query}"
    body = {
        "messages": [
            {"role": "system", "content": "You are a concise model connectivity test assistant."},
            {"role": "user", "content": prompt or "请用一句话回复当前模型连接测试。"},
        ],
        "stream": True,
        "temperature": 0,
        "max_tokens": 120,
    }
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    try:
        yield from _stream_chat_completion_with_token_fallback(url, headers, body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        yield {"type": "error", "message": f"模型接口返回 {exc.code}: {detail[:600]}"}
    except urllib.error.URLError as exc:
        yield {"type": "error", "message": _format_url_error(exc)}
    except TimeoutError:
        yield {"type": "error", "message": "模型接口连接超时"}
    except Exception as exc:
        yield {"type": "error", "message": f"模型连接测试失败: {exc}"}


def _openai_compatible_test_events(
    instance: dict[str, Any],
    provider: dict[str, Any],
    prompt: str,
) -> Iterator[dict[str, object]]:
    model_name = str(instance.get("model_name") or "").strip()
    base_url = str(instance.get("base_url") or provider.get("default_base_url") or "").strip().rstrip("/")
    if not model_name:
        yield {"type": "error", "message": "模型 ID 不能为空"}
        return
    if not base_url:
        yield {"type": "error", "message": "Base URL 不能为空"}
        return
    api_key, key_error = _decrypt_api_key(instance)
    if key_error:
        yield {"type": "error", "message": key_error}
        return
    if not api_key:
        yield {"type": "error", "message": "API Key 不能为空"}
        return

    url = f"{base_url}/chat/completions"
    body = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are a concise model connectivity test assistant."},
            {"role": "user", "content": prompt or "请用一句话回复当前模型连接测试。"},
        ],
        "stream": True,
        "temperature": 0,
        "max_tokens": 120,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    try:
        yield from _stream_chat_completion_with_token_fallback(url, headers, body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        yield {"type": "error", "message": f"模型接口返回 {exc.code}: {detail[:600]}"}
    except urllib.error.URLError as exc:
        yield {"type": "error", "message": _format_url_error(exc)}
    except TimeoutError:
        yield {"type": "error", "message": "模型接口连接超时"}
    except Exception as exc:
        yield {"type": "error", "message": f"模型连接测试失败: {exc}"}
