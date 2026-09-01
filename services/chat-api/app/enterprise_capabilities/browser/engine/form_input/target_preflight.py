from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


@dataclass(frozen=True)
class FillTargetPreflight:
    ok: bool
    ref: str
    reason: str = ""
    target: Optional[Dict[str, Any]] = None


def validate_fill_target(
    observation: Observation,
    args: Dict[str, Any],
) -> FillTargetPreflight:
    """Validate an observation-local ref before dispatching a fill mutation."""
    ref = str(args.get("ref") or "").strip()
    if not ref:
        return FillTargetPreflight(False, ref, "fill target ref is missing")

    target = next((
        item for item in observation.elements
        if isinstance(item, dict) and str(item.get("ref") or "").strip() == ref
    ), None)
    if target is None:
        return FillTargetPreflight(False, ref, "fill target is absent from the latest observation")
    if target.get("disabled"):
        return FillTargetPreflight(False, ref, "fill target is disabled", target)
    if target.get("visible") is False:
        return FillTargetPreflight(False, ref, "fill target is not visible", target)
    if not target.get("editable"):
        return FillTargetPreflight(False, ref, "fill target is not editable", target)
    return FillTargetPreflight(True, ref, target=target)


def is_stale_fill_target_error(error: Optional[str]) -> bool:
    """Return true for failures that mean the ref must be resolved again."""
    text = str(error or "").strip().lower()
    return any(marker in text for marker in (
        "unknown or stale element ref",
        "target_not_found",
        "target_not_editable",
        "fill target is not editable",
        "fill target is absent",
    ))


__all__ = [
    "FillTargetPreflight",
    "is_stale_fill_target_error",
    "validate_fill_target",
]
