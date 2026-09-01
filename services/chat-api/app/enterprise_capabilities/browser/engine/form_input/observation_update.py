from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def apply_confirmed_fill(
    observation: Observation,
    *,
    args: Dict[str, Any],
    result: Any,
    ok: bool,
) -> Observation:
    """Apply an atomic fill receipt without requiring a full DOM rescan."""
    if not ok or not isinstance(result, dict):
        return observation
    receipt = result.get("fill_receipt")
    if not isinstance(receipt, dict) or receipt.get("status") != "confirmed":
        return observation
    ref = str(args.get("ref") or "")
    if not ref:
        return observation
    expected = str(args.get("value") or "")
    changed = False
    elements = []
    for item in observation.elements:
        if not isinstance(item, dict) or str(item.get("ref") or "") != ref:
            elements.append(item)
            continue
        updated = dict(item)
        updated["value"] = expected
        elements.append(updated)
        changed = True
    return replace(observation, elements=elements) if changed else observation


__all__ = ["apply_confirmed_fill"]
