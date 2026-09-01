"""Business-level progress signatures for browser loop convergence."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def browser_progress_signature(
    observation: Observation,
    *,
    state_ledger: Optional[Dict[str, Any]] = None,
) -> tuple[str, str, str]:
    """Ignore transient refs, field values and live counters.

    Progress means a route, interaction surface, or durable mission milestone
    changed. Re-render noise alone must not reset the executor's loop budget.
    """
    ledger = dict(state_ledger or {})
    mission = dict(ledger.get("mission") or {})
    durable = {
        "phase": ledger.get("phase"),
        "completed_signals": ledger.get("completed_signals") or [],
        "remaining_signals": ledger.get("remaining_signals") or [],
        "mission": {
            "confirmed_operations": mission.get("confirmed_operations"),
            "current_query": mission.get("current_query"),
            "search_cycles": mission.get("search_cycles") or [],
        },
    }
    surfaces = []
    for item in observation.elements:
        if not isinstance(item, dict):
            continue
        if not (
            item.get("editable")
            or str(item.get("role") or "").lower() in {
                "button", "link", "textbox", "searchbox", "dialog",
            }
        ):
            continue
        surfaces.append({
            "role": item.get("role"),
            "name": item.get("name"),
            "type": item.get("type"),
            "disabled": bool(item.get("disabled")),
            "editable": bool(item.get("editable")),
            "scope": item.get("scopeId") or item.get("scopeSelector"),
        })
        if len(surfaces) >= 120:
            break
    raw = json.dumps(
        {"durable": durable, "surfaces": surfaces},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    semantic_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return (
        str(observation.url or ""),
        str(observation.title or ""),
        semantic_hash,
    )


__all__ = ["browser_progress_signature"]
