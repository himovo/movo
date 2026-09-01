"""Durable, turn-scoped contracts for retryable content production calls."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.db import get_db


_CONTENT_ARGUMENTS = {
    "request", "content_form", "audience", "tone", "writing_mode",
    "required_sections", "min_words", "max_words", "visual_min", "visual_max",
}


def content_request_fingerprint(arguments: dict[str, Any]) -> str:
    request = re.sub(r"\s+", " ", str(arguments.get("request") or "")).strip()
    return hashlib.sha256(request.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResolvedContentInvocation:
    arguments: dict[str, Any]
    recovered_fields: tuple[str, ...] = ()
    fingerprint: str = ""


class ContentInvocationContractRepository:
    """Keep the first complete tool contract available across DSH retries."""

    COLLECTION = "agent_kernel_bindings"

    async def resolve(
        self,
        *,
        tenant_id: str,
        user_id: str,
        kernel_session_id: str,
        message_id: str,
        arguments: dict[str, Any],
    ) -> ResolvedContentInvocation:
        incoming = {key: value for key, value in dict(arguments or {}).items() if key in _CONTENT_ARGUMENTS}
        fingerprint = content_request_fingerprint(incoming)
        if not message_id or not str(incoming.get("request") or "").strip():
            return ResolvedContentInvocation(incoming, fingerprint=fingerprint)

        scope = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "kernel_session_id": kernel_session_id,
            "active_turn.message_id": message_id,
            "active_turn.status": "running",
        }
        db = get_db()
        row = await db[self.COLLECTION].find_one(
            scope,
            {"active_turn.content_invocation_contracts": 1},
        )
        contracts = list(((row or {}).get("active_turn") or {}).get("content_invocation_contracts") or [])
        saved = next(
            (
                dict(item.get("arguments") or {})
                for item in reversed(contracts)
                if isinstance(item, dict) and str(item.get("fingerprint") or "") == fingerprint
            ),
            None,
        )
        if saved is not None:
            recovered = tuple(sorted(key for key in saved if key not in incoming))
            return ResolvedContentInvocation(
                {**saved, **incoming},
                recovered_fields=recovered,
                fingerprint=fingerprint,
            )

        result = await db[self.COLLECTION].update_one(
            scope,
            {
                "$push": {
                    "active_turn.content_invocation_contracts": {
                        "$each": [{
                            "fingerprint": fingerprint,
                            "arguments": incoming,
                            "created_at": datetime.utcnow(),
                        }],
                        "$slice": -8,
                    }
                }
            },
        )
        if getattr(result, "matched_count", 1) != 1:
            raise LookupError("active content invocation scope is unavailable")
        return ResolvedContentInvocation(incoming, fingerprint=fingerprint)


__all__ = [
    "ContentInvocationContractRepository",
    "ResolvedContentInvocation",
    "content_request_fingerprint",
]
