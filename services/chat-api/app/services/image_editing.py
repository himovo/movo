"""Provider-specific image editing over the existing configured model service."""

import asyncio
import base64
import ipaddress
import mimetypes
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.llm.image_json_protocol import build_image_payload, image_endpoint
from app.llm.image_model_runtime import dashscope_native_endpoint, resolve_image_runtime_kind
from app.llm.providers.azure_gpt_image import AzureGptImageClient, AzureGptImageConfig
from app.services.image_generation import _service, _detect_content_type
from app.utils.oss_uploader import AliyunOSSUploader
from app.services.image_edit_model import resolve_edit_model


def public_image_url(value: str) -> bool:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host or host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return "." in host


async def provider_image_source(storage: Any, object_path: str) -> str:
    signed_url = await asyncio.to_thread(storage.sign_url, object_path)
    if public_image_url(signed_url or ""):
        return signed_url
    raw = await asyncio.to_thread(storage.read_bytes, object_path)
    if not raw or len(raw) > 50 * 1024 * 1024:
        raise ValueError("image_source_unavailable")
    mime = _detect_content_type(raw)
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def edit_request(config: dict[str, Any], *, prompt: str, source_url: str) -> tuple[str, dict, dict, str]:
    settings = dict(config.get("settings") or {})
    kind = resolve_image_runtime_kind(config)
    model = str(config.get("model_name") or "")
    key = str(config.get("api_key") or "")
    if not key or not model:
        raise ValueError("image_model_unavailable")
    headers = {"Authorization": f"Bearer {key}"}
    if kind == "dashscope_image":
        parameters = {k: settings[k] for k in ("size", "quality", "output_format") if settings.get(k)}
        parameters["n"] = 1
        return dashscope_native_endpoint(str(config.get("base_url") or "")), headers, {
            "model": model,
            "input": {"messages": [{"role": "user", "content": [{"image": source_url}, {"text": prompt}]}]},
            "parameters": parameters,
        }, "json"
    payload = build_image_payload(model=model, prompt=prompt, settings=settings)
    payload["n"] = 1
    mode = str(settings.get("edit_request_format") or ("json" if kind == "custom_images" else "multipart"))
    path = str(settings.get("edit_request_path") or (settings.get("request_path") if kind == "custom_images" else "") or "/images/edits")
    if kind == "azure_openai_images":
        client = AzureGptImageClient(AzureGptImageConfig(
            endpoint=str(config.get("base_url") or ""), api_key=key, deployment=model,
            api_version=str(config.get("api_version") or "2024-02-01"),
            api_style=str(settings.get("api_style") or "v1"),
            include_api_version=bool(settings.get("include_api_version")),
        ))
        url = client.image_generation_endpoint("edits")
        headers = {"api-key": key}
    else:
        url = image_endpoint(str(config.get("base_url") or ""), path)
    if mode == "json":
        payload[str(settings.get("edit_image_field") or "image")] = source_url
    else:
        payload.pop("image", None)
    return url, headers, payload, mode


async def edit_image_asset(*, object_path: str, prompt: str, tenant_id: str, user_id: str, image_model_id: str) -> dict[str, Any]:
    config = await resolve_edit_model(image_model_id, tenant_id=tenant_id, user_id=user_id)
    storage = AliyunOSSUploader()
    url, headers, payload, mode = edit_request(config, prompt=prompt, source_url="")
    if mode == "json":
        source_url = await provider_image_source(storage, object_path)
        url, headers, payload, mode = edit_request(config, prompt=prompt, source_url=source_url)
    timeout = float((config.get("settings") or {}).get("timeout_seconds") or 180)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if mode == "json":
            response = await client.post(url, headers=headers, json=payload)
        else:
            raw = await asyncio.to_thread(storage.read_bytes, object_path)
            if not raw or len(raw) > 50 * 1024 * 1024:
                raise ValueError("image_source_unavailable")
            filename = PurePosixPath(object_path).name
            response = await client.post(url, headers=headers,
                data={k: str(v) for k, v in payload.items()},
                files={"image": (filename, raw, mimetypes.guess_type(filename)[0] or "image/png")})
    if response.status_code >= 400:
        # Provider errors can contain credentials and source URLs.
        raise RuntimeError("image_edit_provider_failed")
    data = response.json()
    kind = resolve_image_runtime_kind(config)
    if kind == "dashscope_image":
        source = _service._extract_dashscope_v1_image_url(data)
        image_bytes = await _service._download_remote_image(source, timeout_seconds=timeout)
    elif kind == "custom_images":
        settings = config.get("settings") or {}
        image_bytes = await _service._decode_configured_image_response(data,
            url_path=str(settings.get("response_url_path") or "data.0.url"),
            base64_path=str(settings.get("response_base64_path") or "data.0.b64_json"), timeout_seconds=timeout)
    else:
        image_bytes = await _service._decode_image_response(data, timeout_seconds=timeout)
    mime = _detect_content_type(image_bytes)
    result = await asyncio.to_thread(_service._upload_bytes,
        image_bytes=image_bytes, user_id=user_id, file_prefix="edited_image", content_type=mime)
    return {
        "type": PurePosixPath(result["object_path"]).suffix.lstrip("."),
        "filename": PurePosixPath(result["object_path"]).name,
        "title": prompt[:240], "url": result["url"], "object_path": result["object_path"],
        "content_type": mime, "source_object_path": object_path,
        "image_model_id": image_model_id,
    }
