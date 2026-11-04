"""Read bounded Skill preparation records from the sandbox manager."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from fastapi import HTTPException


def _request(digest: str, record_id: str = "") -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or (record_id and not re.fullmatch(r"[0-9a-f]{32}", record_id)):
        raise HTTPException(status_code=400, detail="invalid_preparation_record")
    base = os.environ.get("MOVO_SANDBOX_MANAGER_URL", "").strip().rstrip("/")
    token = os.environ.get("MOVO_SANDBOX_MANAGER_TOKEN", "")
    if not base or not token:
        raise HTTPException(status_code=503, detail="sandbox_manager_unavailable")
    suffix = f"/{record_id}" if record_id else ""
    request = urllib.request.Request(
        f"{base}/v1/skill-environments/{digest}/records{suffix}",
        headers={"Authorization": f"Bearer {token}"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise HTTPException(status_code=404, detail="preparation_record_not_found") from exc
        raise HTTPException(status_code=503, detail="sandbox_manager_unavailable") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="sandbox_manager_unavailable") from exc


def list_records(digest: str) -> list[dict]:
    return list(_request(digest).get("items") or [])


def get_record(digest: str, record_id: str) -> dict:
    return _request(digest, record_id)
