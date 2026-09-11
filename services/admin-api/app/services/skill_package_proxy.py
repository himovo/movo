from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from fastapi import HTTPException, status

from app.core.config import settings


def install_organization_skill_zip(*, main_id: str, filename: str, content: bytes) -> dict[str, Any]:
    boundary = f"movo-skill-{uuid.uuid4().hex}"
    safe_name = str(filename or "skill.zip").replace('"', "_").replace("\r", "_").replace("\n", "_")
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'.encode(),
        b"Content-Type: application/zip\r\n\r\n",
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    base_url = str(settings.backend_base_url or "http://127.0.0.1:8000").rstrip("/")
    query = urllib.parse.urlencode({"mainId": main_id})
    request = urllib.request.Request(
        f"{base_url}/api/organization-skills/install-zip?{query}",
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-MOVO-Service-Token": settings.backend_service_token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw).get("detail") or raw
        except json.JSONDecodeError:
            detail = raw or str(exc)
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"backend 不可用：{exc.reason}") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="ZIP 安装服务返回了无效结果")
    return data
