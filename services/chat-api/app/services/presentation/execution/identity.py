from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PresentationJobIdentity:
    business_key: str
    job_id: str
    continuation_token: str
    request_fingerprint: str


def build_presentation_job_identity(
    *,
    tenant_id: str,
    user_id: str,
    conversation_id: str,
    message_id: str,
    generation_mode: str,
    arguments: dict[str, Any],
) -> PresentationJobIdentity:
    """Build a stable identity that survives DSH action-id retries."""

    request_payload = {
        "generation_mode": str(generation_mode or "llm").strip().lower(),
        "arguments": _normalized(arguments),
    }
    request_json = json.dumps(
        request_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    request_fingerprint = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
    scope = "\x1f".join((
        str(tenant_id or ""),
        str(user_id or ""),
        str(conversation_id or ""),
        str(message_id or ""),
        request_fingerprint,
    ))
    digest = hashlib.sha256(scope.encode("utf-8")).hexdigest()
    return PresentationJobIdentity(
        business_key=f"presentation:{digest}",
        job_id=f"pptjob-{digest[:32]}",
        continuation_token=f"ppt-resume-{digest}",
        request_fingerprint=request_fingerprint,
    )


def _normalized(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalized(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalized(item) for item in value]
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)


__all__ = ["PresentationJobIdentity", "build_presentation_job_identity"]
