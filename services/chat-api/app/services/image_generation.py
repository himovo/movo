from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, Dict
from urllib.parse import urlparse

import dashscope
import httpx
from dashscope import MultiModalConversation

from app.core.tenant import resolve_main_id
from app.llm.configured_image_models import get_default_image_model_config, get_image_model_config
from app.llm.configured_models import ModelConfigError
from app.llm.providers.azure_gpt_image import AzureGptImageClient, AzureGptImageConfig
from app.infrastructure.request_context import get_request_context
from app.utils.oss_uploader import AliyunOSSUploader

logger = logging.getLogger(__name__)

LogHook = Callable[[str, Dict[str, Any]], None]


@dataclass(frozen=True)
class ImageGenerationResult:
    image_bytes: bytes
    response: Dict[str, Any]
    request_id: str
    provider_type: str
    runtime_kind: str
    model_id: str
    model_name: str
    model_source: str


def _is_valid_remote_image_url(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw or any(ch in raw for ch in (" ", "\n", "\r", "\t", "\"", "'")):
        return False
    if raw.startswith(("/askai-api/api/files/", "/api/files/")):
        return True
    try:
        parsed = urlparse(raw)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return False
    return True


def _guess_ext(image_url: str, content_type: str) -> str:
    parsed = urlparse(str(image_url or ""))
    path = str(parsed.path or "").lower()
    if path.endswith(".jpg") or path.endswith(".jpeg"):
        return "jpg"
    if path.endswith(".webp"):
        return "webp"
    if path.endswith(".gif"):
        return "gif"
    if path.endswith(".svg"):
        return "svg"
    if path.endswith(".png"):
        return "png"
    ctype = str(content_type or "").lower()
    if "jpeg" in ctype:
        return "jpg"
    if "webp" in ctype:
        return "webp"
    if "gif" in ctype:
        return "gif"
    if "svg" in ctype:
        return "svg"
    return "png"


def _detect_content_type(image_bytes: bytes, hinted_format: str | None = None) -> str:
    hinted = str(hinted_format or "").strip().lower()
    if hinted in {"png", "jpeg", "jpg", "webp", "gif", "svg+xml"}:
        token = "jpeg" if hinted == "jpg" else hinted
        return f"image/{token}"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    return "image/png"


def _normalize_settings(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("settings")
    return dict(raw or {}) if isinstance(raw, dict) else {}


def _normalize_size(size: str | None, *, runtime_kind: str) -> str:
    raw = str(size or "").strip().lower()
    if not raw:
        return ""
    if runtime_kind == "dashscope_image":
        return raw.replace("x", "*")
    return raw.replace("*", "x")


class ConfiguredImageGenerationService:
    async def generate(
        self,
        *,
        prompt: str,
        user_id: str,
        negative_prompt: str = "",
        size: str | None = None,
        quality: str | None = None,
        output_format: str | None = None,
        timeout_seconds: float | None = None,
        output_spec: dict[str, Any] | None = None,
        log_hook: LogHook | None = None,
    ) -> ImageGenerationResult:
        prompt_text = str(prompt or "").strip()
        if not prompt_text:
            raise ValueError("image prompt is required")
        _ = str(user_id or "anonymous").strip() or "anonymous"
        merged_output_spec = dict(get_request_context() or {})
        if isinstance(output_spec, dict):
            merged_output_spec.update(output_spec)
        config, model_source = await self._resolve_image_model_config(output_spec=merged_output_spec)
        if config is None:
            raise ModelConfigError(
                "未配置可用的图片生成模型，请在管理后台的模型中心添加并启用 image_generation 模型"
            )
        return await self._generate_from_model_config(
            config=config,
            prompt=prompt_text,
            negative_prompt=negative_prompt,
            size=size,
            quality=quality,
            output_format=output_format,
            timeout_seconds=timeout_seconds,
            model_source=model_source,
            log_hook=log_hook,
        )

    async def generate_and_persist(
        self,
        *,
        prompt: str,
        user_id: str,
        negative_prompt: str = "",
        size: str | None = None,
        quality: str | None = None,
        output_format: str | None = None,
        timeout_seconds: float | None = None,
        output_spec: dict[str, Any] | None = None,
        file_prefix: str = "visual",
        log_hook: LogHook | None = None,
    ) -> dict[str, Any]:
        result = await self.generate(
            prompt=prompt,
            user_id=user_id,
            negative_prompt=negative_prompt,
            size=size,
            quality=quality,
            output_format=output_format,
            timeout_seconds=timeout_seconds,
            output_spec=output_spec,
            log_hook=log_hook,
        )
        persisted = self._upload_bytes(
            image_bytes=result.image_bytes,
            user_id=user_id,
            file_prefix=file_prefix,
            content_type=_detect_content_type(result.image_bytes, output_format),
        )
        return {
            "ok": True,
            "error": "",
            "image_url": str(persisted.get("url") or ""),
            "source_image_url": "",
            "object_path": str(persisted.get("object_path") or ""),
            "request_id": result.request_id,
            "model_id": result.model_id,
            "model_name": result.model_name,
            "model_source": result.model_source,
            "provider_type": result.provider_type,
            "runtime_kind": result.runtime_kind,
            "response": result.response,
            "bytes": result.image_bytes,
        }

    async def _resolve_image_model_config(
        self,
        *,
        output_spec: dict[str, Any] | None,
    ) -> tuple[dict[str, Any] | None, str]:
        merged_output_spec = dict(get_request_context() or {})
        if isinstance(output_spec, dict):
            merged_output_spec.update(output_spec)
        main_id = resolve_main_id(merged_output_spec.get("main_id") or merged_output_spec.get("mainId"))
        image_model_id = str(
            merged_output_spec.get("image_model_id")
            or merged_output_spec.get("imageModelId")
            or ""
        ).strip()
        if image_model_id:
            config = await get_image_model_config(image_model_id, main_id)
            if config is None:
                raise ModelConfigError("图片模型配置不存在或不可用")
            return config, "admin_config"
        config = await get_default_image_model_config(main_id)
        if config is None:
            return None, "admin_config"
        return config, "admin_config"

    async def _generate_from_model_config(
        self,
        *,
        config: dict[str, Any],
        prompt: str,
        negative_prompt: str,
        size: str | None,
        quality: str | None,
        output_format: str | None,
        timeout_seconds: float | None,
        model_source: str,
        log_hook: LogHook | None,
    ) -> ImageGenerationResult:
        settings = _normalize_settings(config)
        provider_type = str(config.get("provider_type") or "openai_compatible").strip() or "openai_compatible"
        runtime_kind = (
            str(config.get("runtime_kind") or "").strip()
            or ("azure_openai_images" if provider_type == "azure_openai" else "openai_images")
        )
        if runtime_kind == "azure_openai_images":
            return await self._generate_with_azure_config(
                config=config,
                settings=settings,
                prompt=prompt,
                size=size,
                quality=quality,
                output_format=output_format,
                timeout_seconds=timeout_seconds,
                model_source=model_source,
                log_hook=log_hook,
            )
        if runtime_kind == "dashscope_image":
            return await self._generate_with_dashscope_config(
                config=config,
                settings=settings,
                prompt=prompt,
                negative_prompt=negative_prompt,
                size=size,
                timeout_seconds=timeout_seconds,
                model_source=model_source,
            )
        return await self._generate_with_openai_config(
            config=config,
            settings=settings,
            prompt=prompt,
            size=size,
            quality=quality,
            output_format=output_format,
            timeout_seconds=timeout_seconds,
            model_source=model_source,
        )

    async def _generate_with_azure_config(
        self,
        *,
        config: dict[str, Any],
        settings: dict[str, Any],
        prompt: str,
        size: str | None,
        quality: str | None,
        output_format: str | None,
        timeout_seconds: float | None,
        model_source: str,
        log_hook: LogHook | None,
    ) -> ImageGenerationResult:
        client = AzureGptImageClient(
            config=AzureGptImageConfig(
                endpoint=str(config.get("base_url") or ""),
                api_key=str(config.get("api_key") or ""),
                api_version=str(config.get("api_version") or settings.get("api_version") or "2024-02-01"),
                deployment=str(config.get("model_name") or ""),
                size=_normalize_size(size or settings.get("size") or "1536x864", runtime_kind="azure_openai_images"),
                quality=str(quality or settings.get("quality") or "low"),
                api_style=str(settings.get("generation_api_style") or settings.get("api_style") or "v1"),
                include_api_version=bool(settings.get("include_api_version")),
                max_retries=int(settings.get("max_retries") or 3),
                retry_base_seconds=float(settings.get("retry_base_seconds") or 1.5),
                retry_max_seconds=float(settings.get("retry_max_seconds") or 30.0),
                connect_timeout=float(settings.get("http_connect_timeout") or 30.0),
                read_timeout=float(timeout_seconds or settings.get("http_read_timeout") or 600.0),
                write_timeout=float(settings.get("http_write_timeout") or 600.0),
                pool_timeout=float(settings.get("http_pool_timeout") or 30.0),
                keepalive_connections=int(settings.get("http_keepalive") or 0),
                max_connections=int(settings.get("http_max_connections") or 2),
            )
        )
        result = await client.generate_image_async(prompt, log_hook=log_hook)
        return ImageGenerationResult(
            image_bytes=result.image_bytes,
            response=result.response,
            request_id=str(result.response.get("request_id") or ""),
            provider_type=str(config.get("provider_type") or "azure_openai"),
            runtime_kind="azure_openai_images",
            model_id=str(config.get("id") or config.get("model_name") or ""),
            model_name=str(config.get("model_name") or ""),
            model_source=model_source,
        )

    async def _generate_with_openai_config(
        self,
        *,
        config: dict[str, Any],
        settings: dict[str, Any],
        prompt: str,
        size: str | None,
        quality: str | None,
        output_format: str | None,
        timeout_seconds: float | None,
        model_source: str,
    ) -> ImageGenerationResult:
        endpoint = str(config.get("base_url") or "").rstrip("/")
        if not endpoint:
            raise ModelConfigError("图片模型 Base URL 不能为空")
        api_key = str(config.get("api_key") or "").strip()
        if not api_key:
            raise ModelConfigError("图片模型 API Key 不能为空")
        url = f"{endpoint}/images/generations"
        resolved_format = str(output_format or settings.get("output_format") or "png").strip() or "png"
        payload = {
            "model": str(config.get("model_name") or "").strip(),
            "prompt": prompt,
            "size": _normalize_size(size or settings.get("size") or "1024x1024", runtime_kind="openai_images"),
            "quality": str(quality or settings.get("quality") or "standard"),
            "n": 1,
            "output_format": resolved_format,
        }
        background = str(settings.get("background") or "").strip()
        if background:
            payload["background"] = background
        timeout_value = float(timeout_seconds or settings.get("timeout_seconds") or 90.0)
        async with httpx.AsyncClient(timeout=timeout_value, follow_redirects=True) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload, ensure_ascii=False),
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"image generation failed http_{resp.status_code}: {resp.text[:1200]}")
        data = resp.json()
        image_bytes = await self._decode_image_response(data, timeout_seconds=timeout_value)
        return ImageGenerationResult(
            image_bytes=image_bytes,
            response=dict(data or {}),
            request_id=str((data or {}).get("request_id") or ""),
            provider_type=str(config.get("provider_type") or "openai_compatible"),
            runtime_kind="openai_images",
            model_id=str(config.get("id") or config.get("model_name") or ""),
            model_name=str(config.get("model_name") or ""),
            model_source=model_source,
        )

    async def _generate_with_dashscope_config(
        self,
        *,
        config: dict[str, Any],
        settings: dict[str, Any],
        prompt: str,
        negative_prompt: str,
        size: str | None,
        timeout_seconds: float | None,
        model_source: str,
    ) -> ImageGenerationResult:
        api_key = str(config.get("api_key") or "").strip()
        if not api_key:
            raise ModelConfigError("图片模型 API Key 不能为空")
        model_name = str(config.get("model_name") or "").strip()
        if not model_name:
            raise ModelConfigError("图片模型 ID 不能为空")
        resolved_size = _normalize_size(size or settings.get("size") or "1216*2176", runtime_kind="dashscope_image")
        timeout_value = float(timeout_seconds or settings.get("timeout_seconds") or 90.0)
        if model_name in {"qwen-image-max", "qwen-image-plus"}:
            data = await self._call_dashscope_v1(
                api_key=api_key,
                prompt=prompt,
                negative_prompt=negative_prompt,
                model_name=model_name,
                size=resolved_size,
                timeout_seconds=timeout_value,
            )
            image_url = self._extract_dashscope_v1_image_url(data)
            image_bytes = await self._download_remote_image(image_url, timeout_seconds=timeout_value)
            return ImageGenerationResult(
                image_bytes=image_bytes,
                response=dict(data or {}),
                request_id=str((data or {}).get("request_id") or ""),
                provider_type=str(config.get("provider_type") or "openai_compatible"),
                runtime_kind="dashscope_image",
                model_id=str(config.get("id") or model_name),
                model_name=model_name,
                model_source=model_source,
            )
        data = await self._call_dashscope_multimodal(
            api_key=api_key,
            prompt=prompt,
            negative_prompt=negative_prompt,
            model_name=model_name,
            timeout_seconds=timeout_value,
        )
        image_url = self._extract_dashscope_multimodal_image_url(data)
        image_bytes = await self._download_remote_image(image_url, timeout_seconds=timeout_value)
        return ImageGenerationResult(
            image_bytes=image_bytes,
            response=dict(data or {}),
            request_id=str((data or {}).get("request_id") or ""),
            provider_type=str(config.get("provider_type") or "openai_compatible"),
            runtime_kind="dashscope_image",
            model_id=str(config.get("id") or model_name),
            model_name=model_name,
            model_source=model_source,
        )

    async def _call_dashscope_v1(
        self,
        *,
        api_key: str,
        prompt: str,
        negative_prompt: str,
        model_name: str,
        size: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        endpoint = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
        payload = {
            "model": model_name,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ]
            },
            "parameters": {
                "negative_prompt": str(negative_prompt or "").strip(),
                "prompt_extend": True,
                "watermark": False,
                "size": size,
            },
        }
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            resp = await client.post(
                endpoint,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                content=json.dumps(payload, ensure_ascii=False),
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"dashscope image generation failed http_{resp.status_code}: {resp.text[:1200]}")
        return dict(resp.json() or {})

    async def _call_dashscope_multimodal(
        self,
        *,
        api_key: str,
        prompt: str,
        negative_prompt: str,
        model_name: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        if getattr(dashscope, "base_http_api_url", ""):
            # Preserve existing process-wide behavior while still using the per-model API key.
            dashscope.base_http_api_url = str(dashscope.base_http_api_url)
        response = await loop.run_in_executor(
            None,
            partial(
                MultiModalConversation.call,
                api_key=api_key,
                model=model_name,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                result_format="message",
                stream=False,
                n=1,
                watermark=False,
                negative_prompt=str(negative_prompt or "").strip(),
            ),
        )
        status_code = int(getattr(response, "status_code", 500) or 500)
        if status_code != 200:
            raise RuntimeError(
                "dashscope multimodal image generation failed "
                f"sdk_{status_code}: {str(getattr(response, 'message', '') or getattr(response, 'code', ''))[:1200]}"
            )
        return {
            "request_id": str(getattr(response, "request_id", "") or ""),
            "output": getattr(response, "output", {}) or {},
        }

    def _extract_dashscope_v1_image_url(self, data: dict[str, Any]) -> str:
        choices = (((data or {}).get("output") or {}).get("choices") or [])
        first = choices[0] if choices else {}
        content = (((first.get("message") or {}).get("content")) or [])
        for item in content:
            if isinstance(item, dict) and str(item.get("image") or "").strip():
                return str(item.get("image") or "").strip()
        raise RuntimeError("dashscope image response missing image_url")

    def _extract_dashscope_multimodal_image_url(self, data: dict[str, Any]) -> str:
        output = data.get("output") if isinstance(data.get("output"), dict) else {}
        choices = output.get("choices") or []
        first = choices[0] if choices else {}
        content = (first.get("message") or {}).get("content") or []
        for item in content:
            if isinstance(item, dict) and str(item.get("image") or "").strip():
                return str(item.get("image") or "").strip()
        raise RuntimeError("dashscope multimodal image response missing image_url")

    async def _decode_image_response(self, data: Dict[str, Any], *, timeout_seconds: float) -> bytes:
        items = data.get("data") or []
        if not items:
            raise RuntimeError(f"image response has no data: {str(data)[:800]}")
        first = items[0]
        if first.get("b64_json"):
            return base64.b64decode(first["b64_json"])
        url = str(first.get("url") or "").strip()
        if not url:
            raise RuntimeError(f"image response has no b64_json/url: {str(data)[:800]}")
        return await self._download_remote_image(url, timeout_seconds=timeout_seconds)

    async def _download_remote_image(self, image_url: str, *, timeout_seconds: float) -> bytes:
        src = str(image_url or "").strip()
        if not _is_valid_remote_image_url(src):
            raise RuntimeError("invalid remote image url")
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            resp = await client.get(src)
        if resp.status_code >= 400:
            raise RuntimeError(f"download image failed http_{resp.status_code}")
        content = bytes(resp.content or b"")
        if not content:
            raise RuntimeError("empty image content")
        return content

    def _upload_bytes(
        self,
        *,
        image_bytes: bytes,
        user_id: str,
        file_prefix: str,
        content_type: str,
    ) -> dict[str, Any]:
        uid = str(user_id or "anonymous").strip() or "anonymous"
        uploader = AliyunOSSUploader()
        ext = _guess_ext("", content_type)
        file_name = f"{file_prefix}_{uuid.uuid4().hex[:10]}.{ext}"
        public_url, object_path = uploader.upload_bytes_with_path(
            image_bytes,
            uid,
            file_name,
            content_type=content_type or None,
        )
        signed_url = uploader.sign_url(object_path)
        return {
            "url": signed_url or public_url,
            "public_url": public_url,
            "signed_url": signed_url,
            "object_path": object_path,
        }


_service = ConfiguredImageGenerationService()


async def generate_image_asset(
    *,
    prompt: str,
    user_id: str,
    negative_prompt: str = "",
    size: str | None = None,
    quality: str | None = None,
    output_format: str | None = None,
    timeout_seconds: float | None = None,
    output_spec: dict[str, Any] | None = None,
    file_prefix: str = "visual",
    log_hook: LogHook | None = None,
) -> dict[str, Any]:
    return await _service.generate_and_persist(
        prompt=prompt,
        user_id=user_id,
        negative_prompt=negative_prompt,
        size=size,
        quality=quality,
        output_format=output_format,
        timeout_seconds=timeout_seconds,
        output_spec=output_spec,
        file_prefix=file_prefix,
        log_hook=log_hook,
    )


async def generate_image(
    *,
    prompt: str,
    user_id: str,
    negative_prompt: str = "",
    size: str | None = None,
    quality: str | None = None,
    output_format: str | None = None,
    timeout_seconds: float | None = None,
    output_spec: dict[str, Any] | None = None,
    log_hook: LogHook | None = None,
) -> ImageGenerationResult:
    return await _service.generate(
        prompt=prompt,
        user_id=user_id,
        negative_prompt=negative_prompt,
        size=size,
        quality=quality,
        output_format=output_format,
        timeout_seconds=timeout_seconds,
        output_spec=output_spec,
        log_hook=log_hook,
    )
