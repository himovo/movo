from __future__ import annotations

import json
import uuid
from typing import Any, Dict
from urllib.parse import urlparse
from xml.sax.saxutils import escape

import httpx
import dashscope
from dashscope import MultiModalConversation

from app.core.config import get_settings
from app.services.image_generation import generate_image_asset as generate_configured_image_asset
from app.utils.oss_uploader import AliyunOSSUploader

settings = get_settings()
dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'


def is_valid_remote_image_url(value: str) -> bool:
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


async def generate_infographic_v1(
    *,
    prompt: str,
    negative_prompt: str = "",
    size: str = "1664*928",
    model: str = "qwen-image-max",
    timeout_seconds: float = 90.0,
) -> Dict[str, Any]:
    api_key = str(settings.DASHSCOPE_API_KEY or "").strip()
    if not api_key:
        return {"ok": False, "error": "missing_DASHSCOPE_API_KEY", "image_url": "", "request_id": ""}

    endpoint = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    payload = {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": str(prompt or "").strip()}],
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
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            resp = await client.post(endpoint, headers=headers, content=json.dumps(payload, ensure_ascii=False))
            text = resp.text or ""
            if resp.status_code >= 400:
                return {
                    "ok": False,
                    "error": f"http_{resp.status_code}",
                    "raw": text[:1200],
                    "image_url": "",
                    "request_id": "",
                }
            data = resp.json()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "image_url": "", "request_id": ""}

    image_url = ""
    try:
        choices = (((data or {}).get("output") or {}).get("choices") or [])
        first = choices[0] if choices else {}
        content = (((first.get("message") or {}).get("content")) or [])
        for item in content:
            if isinstance(item, dict) and str(item.get("image") or "").strip():
                image_url = str(item.get("image") or "").strip()
                break
    except Exception:
        image_url = ""

    image_url = image_url if is_valid_remote_image_url(image_url) else ""

    return {
        "ok": bool(image_url),
        "error": "" if image_url else "missing_image_url",
        "image_url": image_url,
        "request_id": str((data or {}).get("request_id") or ""),
        "usage": (data or {}).get("usage") or {},
    }


async def generate_infographic(
    *,
    prompt: str,
    negative_prompt: str = "",
    size: str = "1216*2176",  # Recommended for qwen-image-2.0? Or keep old?
    model: str = "qwen-image-2.0",
    images: Optional[List[str]] = None,
    timeout_seconds: float = 90.0,
) -> Dict[str, Any]:
    api_key = str(settings.DASHSCOPE_API_KEY or "").strip()
    if not api_key:
        return {"ok": False, "error": "missing_DASHSCOPE_API_KEY", "image_url": "", "request_id": ""}

    # Compatibility: if model is specifically older, fallback to v1
    if model in ("qwen-image-max", "qwen-image-plus") and not images:
        return await generate_infographic_v1(
            prompt=prompt,
            negative_prompt=negative_prompt,
            size=size,
            model=model,
            timeout_seconds=timeout_seconds
        )

    # Implement Qwen-Image-2.0 via SDK
    content_payload = []
    if images:
        for img_url in images:
            if is_valid_remote_image_url(img_url):
                content_payload.append({"image": img_url})
    
    content_payload.append({"text": str(prompt or "").strip()})

    messages = [
        {
            "role": "user",
            "content": content_payload
        }
    ]

    try:
        # Note: dashscope SDK call is blocking by default, but we should wrap it or use a separate executor if needed.
        # However, for simplicity and since we are in an async function, we'll use a thread pool or just run it.
        # The user's snippet uses:
        # response = MultiModalConversation.call(...)
        import asyncio
        from functools import partial

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            partial(
                MultiModalConversation.call,
                api_key=api_key,
                model=model,
                messages=messages,
                result_format='message',
                stream=False,
                n=1,
                watermark=False,
                negative_prompt=negative_prompt
            )
        )

        if response.status_code != 200:
            return {
                "ok": False,
                "error": f"sdk_{response.status_code}",
                "raw": str(response.message or response.code),
                "image_url": "",
                "request_id": str(response.request_id or ""),
            }

        image_url = ""
        output = getattr(response, "output", {}) or {}
        choices = output.get("choices") or []
        if choices:
            first = choices[0]
            content = (first.get("message") or {}).get("content") or []
            for item in content:
                if isinstance(item, dict) and item.get("image"):
                    image_url = str(item.get("image")).strip()
                    break

        return {
            "ok": bool(image_url),
            "error": "" if image_url else "missing_image_url_in_sdk_response",
            "image_url": image_url,
            "request_id": str(response.request_id or ""),
            "usage": output.get("usage") or {},
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "image_url": "", "request_id": ""}


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


async def persist_image_asset(
    *,
    image_url: str,
    user_id: str,
    file_prefix: str = "visual",
    timeout_seconds: float = 45.0,
) -> Dict[str, Any]:
    src = str(image_url or "").strip()
    uid = str(user_id or "anonymous").strip() or "anonymous"
    if not src.startswith(("http://", "https://")) or not is_valid_remote_image_url(src):
        return {"ok": False, "error": "invalid_image_url", "url": src}
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            resp = await client.get(src)
            if resp.status_code >= 400:
                return {"ok": False, "error": f"http_{resp.status_code}", "url": src}
            content = bytes(resp.content or b"")
            if not content:
                return {"ok": False, "error": "empty_image_content", "url": src}
            content_type = str(resp.headers.get("content-type") or "").strip()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "url": src}

    try:
        uploader = AliyunOSSUploader()
        ext = _guess_ext(src, content_type)
        file_name = f"{file_prefix}_{uuid.uuid4().hex[:10]}.{ext}"
        public_url, object_path = uploader.upload_bytes_with_path(
            content,
            uid,
            file_name,
            content_type=content_type or None,
        )
        signed_url = uploader.sign_url(object_path)
        return {
            "ok": True,
            "url": signed_url or public_url,
            "public_url": public_url,
            "signed_url": signed_url,
            "object_path": object_path,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "url": src}


async def generate_infographic_asset(
    *,
    prompt: str,
    user_id: str,
    negative_prompt: str = "",
    size: str = "1216*2176",
    model: str = "qwen-image-2.0",
    timeout_seconds: float = 90.0,
) -> Dict[str, Any]:
    output_spec = {
        "image_model_name_hint": str(model or "").strip(),
    }
    return await generate_configured_image_asset(
        prompt=prompt,
        user_id=user_id,
        negative_prompt=negative_prompt,
        size=size,
        timeout_seconds=timeout_seconds,
        output_spec=output_spec,
        file_prefix="infographic",
    )


async def generate_svg_placeholder_asset(
    *,
    title: str,
    subtitle: str,
    user_id: str,
    file_prefix: str = "infographic_placeholder",
) -> Dict[str, Any]:
    safe_title = escape(str(title or "").strip()[:64] or "Visual")
    safe_subtitle = escape(str(subtitle or "").strip()[:180] or "Placeholder visual generated by runtime")
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1664" height="928" viewBox="0 0 1664 928">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1e293b"/>
    </linearGradient>
  </defs>
  <rect width="1664" height="928" fill="url(#bg)"/>
  <rect x="64" y="64" width="1536" height="800" rx="28" fill="#ffffff" opacity="0.96"/>
  <rect x="112" y="122" width="320" height="10" rx="5" fill="#2563eb"/>
  <text x="112" y="240" font-size="72" font-family="Arial, Helvetica, sans-serif" font-weight="700" fill="#0f172a">{safe_title}</text>
  <foreignObject x="112" y="290" width="1320" height="320">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: Arial, Helvetica, sans-serif; color:#334155; font-size:34px; line-height:1.45;">
      {safe_subtitle}
    </div>
  </foreignObject>
  <rect x="112" y="700" width="1440" height="1" fill="#cbd5e1"/>
  <text x="112" y="770" font-size="30" font-family="Arial, Helvetica, sans-serif" fill="#475569">Runtime fallback visual asset</text>
</svg>"""
    try:
        uploader = AliyunOSSUploader()
        file_name = f"{file_prefix}_{uuid.uuid4().hex[:10]}.svg"
        public_url, object_path = uploader.upload_bytes_with_path(
            svg.encode("utf-8"),
            str(user_id or "anonymous").strip() or "anonymous",
            file_name,
            content_type="image/svg+xml",
        )
        signed_url = uploader.sign_url(object_path)
        return {
            "ok": True,
            "error": "",
            "image_url": signed_url or public_url,
            "source_image_url": "",
            "object_path": object_path,
            "request_id": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "image_url": "",
            "source_image_url": "",
            "object_path": "",
            "request_id": "",
        }
