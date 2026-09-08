from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation
from .fill_outcome import resolve_fill_outcome
from .identity import find_field


def apply_confirmed_fill(
    observation: Observation,
    *,
    args: Dict[str, Any],
    result: Any,
    ok: bool,
    before: Observation,
) -> Observation:
    """Apply an atomic fill receipt without requiring a full DOM rescan."""
    if not ok or not isinstance(result, dict):
        return observation
    receipt = result.get("fill_receipt")
    if not isinstance(receipt, dict) or resolve_fill_outcome(result=result, ok=ok).status != "confirmed":
        return observation
    ref = str(args.get("ref") or "")
    if not ref:
        return observation
    originals = [item for item in before.elements if item.get("ref") == ref]
    if len(originals) != 1 or before.url != observation.url:
        return observation
    original = originals[0]
    target = find_field(observation.elements, original, ref if before is observation else "")
    if target is None:
        return observation
    # A selector may identify a replacement editor, but a prior receipt does
    # not prove that replacement contains the value. Keep its observed value.
    if before is not observation and (
        not original.get("backendNodeId")
        or target.get("backendNodeId") != original.get("backendNodeId")
    ):
        return observation
    expected = str(args.get("value") or "")
    changed = False
    elements = []
    for item in observation.elements:
        if item is not target:
            elements.append(item)
            continue
        updated = dict(item)
        updated["value"] = expected
        elements.append(updated)
        changed = True
    return replace(observation, elements=elements) if changed else observation


__all__ = ["apply_confirmed_fill"]
