from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from app.infrastructure.request_context import get_request_context


logger = logging.getLogger("app.observability.artifacts")


def write_debug_artifact(domain: str, name: str, payload: Any, *, enabled: bool | None = None) -> str:
    if enabled is None:
        try:
            from app.core.config import get_settings

            enabled = bool(get_settings().DEBUG_ARTIFACTS_ENABLED)
        except Exception:
            enabled = True
    if not enabled:
        return ""
    ctx = get_request_context()
    request_id = _safe_name(str(ctx.get("request_id") or ctx.get("message_id") or ctx.get("session_id") or "no_request"))
    today = datetime.now().strftime("%Y-%m-%d")
    root = Path(__file__).resolve().parents[3] / "static" / "debug_snapshots" / _safe_name(domain) / today / request_id
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{_safe_name(name)}.json"
    body = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    path.write_text(body, encoding="utf-8")
    rel = str(path.relative_to(Path(__file__).resolve().parents[3]))
    logger.info(
        "debug artifact written",
        extra={"event": "debug_artifact.written", "artifact_domain": domain, "artifact_name": name, "artifact_path": rel, "artifact_size": len(body)},
    )
    return rel


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip())[:120]
    return cleaned or "artifact"
