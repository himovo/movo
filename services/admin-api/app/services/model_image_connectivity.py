from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.core.config import settings
from app.services.model_test_tls import build_model_test_ssl_context


async def run_saved_image_model_test(
    instance_id: str,
    main_id: str,
    *,
    prompt: str,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _request_image_test,
        instance_id,
        main_id,
        prompt,
    )


def _request_image_test(instance_id: str, main_id: str, prompt: str) -> dict[str, Any]:
    base_url = str(settings.backend_base_url or "http://127.0.0.1:8000").rstrip("/")
    path_id = urllib.parse.quote(instance_id, safe="")
    request = urllib.request.Request(
        f"{base_url}/api/models/{path_id}/test-image",
        data=json.dumps(
            {
                "main_id": main_id,
                "prompt": prompt or "生成一张简洁的科技感演示文稿封面，不要文字。",
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-MOVO-Service-Token": settings.backend_service_token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=900, context=build_model_test_ssl_context()) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"图片模型运行时返回 HTTP {exc.code}: {detail[:800]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接图片模型运行时: {exc.reason}") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError("图片模型运行时返回了无效响应")
    return data
__all__ = ["run_saved_image_model_test"]
