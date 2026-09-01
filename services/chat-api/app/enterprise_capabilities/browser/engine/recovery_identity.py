"""Stable identities for deduplicating browser recovery handoffs."""
from __future__ import annotations

import hashlib
import json
from typing import Mapping

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def browser_recovery_dedupe_key(
    observation: Observation,
    *,
    family: str,
) -> str:
    return ":".join((
        "browser_recovery",
        str(family or "interaction").strip().lower(),
        str(observation.url or "").strip(),
        _page_state_key(observation),
    ))


def _page_state_key(observation: Observation) -> str:
    explicit = str(observation.state_fingerprint or "").strip()
    if explicit:
        return explicit
    visible_elements = [
        {
            "ref": str(item.get("ref") or ""),
            "role": str(item.get("role") or ""),
            "name": str(item.get("name") or item.get("text") or "")[:120],
        }
        for item in list(observation.elements or [])[:80]
        if isinstance(item, Mapping)
    ]
    payload = {
        "title": str(observation.title or "")[:160],
        "text": str(observation.page_text or "")[:1000],
        "elements": visible_elements,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


__all__ = ["browser_recovery_dedupe_key"]
