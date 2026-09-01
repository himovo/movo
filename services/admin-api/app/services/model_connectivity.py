from __future__ import annotations

import asyncio
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterator

try:
    import certifi
except Exception:  # pragma: no cover - optional dependency
    certifi = None

from app.core.config import settings


def backend_model_test_events(instance_id: str, main_id: str, prompt: str) -> Iterator[dict[str, object]]:
    base_url = str(settings.backend_base_url or "http://127.0.0.1:8000").rstrip("/")
    path_id = urllib.parse.quote(instance_id, safe="")
    request = urllib.request.Request(
        f"{base_url}/api/models/{path_id}/test/stream",
        data=json.dumps(
            {
                "main_id": main_id,
                "prompt": prompt or "Reply with one short sentence to confirm the connection.",
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "X-MOVO-Service-Token": settings.backend_service_token,
        },
        method="POST",
    )
    try:
        yield from _iter_backend_sse_events(request)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        yield {"type": "error", "message": f"Model runtime returned HTTP {exc.code}: {detail[:600]}"}
    except urllib.error.URLError as exc:
        yield {"type": "error", "message": f"Unable to reach the model runtime: {exc.reason}"}
    except Exception as exc:
        yield {"type": "error", "message": f"Model connection test failed: {exc}"}


async def run_saved_model_test(instance_id: str, main_id: str, prompt: str = "") -> tuple[bool, str]:
    return await asyncio.to_thread(_consume_test_events, instance_id, main_id, prompt)


def next_event(iterator: Iterator[dict[str, object]]) -> tuple[bool, dict[str, object] | None]:
    try:
        return True, next(iterator)
    except StopIteration:
        return False, None


def _consume_test_events(instance_id: str, main_id: str, prompt: str) -> tuple[bool, str]:
    response_text = ""
    for event in backend_model_test_events(instance_id, main_id, prompt):
        event_type = str(event.get("type") or "")
        if event_type == "delta":
            response_text += str(event.get("content") or "")
        elif event_type == "error":
            return False, str(event.get("message") or "Model connection test failed")
    return True, response_text or "Model connection test succeeded."


def _iter_backend_sse_events(request: urllib.request.Request) -> Iterator[dict[str, object]]:
    with urllib.request.urlopen(request, timeout=120, context=_build_ssl_context()) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or line.startswith(":") or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                yield event


def _build_ssl_context() -> ssl.SSLContext:
    if settings.model_test_insecure_skip_verify:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    if settings.model_test_ca_bundle.strip():
        return ssl.create_default_context(cafile=settings.model_test_ca_bundle.strip())
    if certifi is not None:
        try:
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
    return ssl.create_default_context()
