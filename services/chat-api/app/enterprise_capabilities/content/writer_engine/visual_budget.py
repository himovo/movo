from __future__ import annotations

from typing import Any, Dict


def resolve_sectional_visual_budget(
    *,
    visual_policy: Dict[str, Any],
    visual_plan: Dict[str, Any],
    section_count: int,
) -> Dict[str, int]:
    """Resolve image bounds for per-section generation without overriding explicit bounds."""
    policy = dict(visual_policy or {})
    plan = dict(visual_plan or {})
    minimum = max(0, int(policy.get("min_visuals_per_report") or 0))
    maximum = max(0, int(policy.get("max_visuals_per_report") or 0))
    has_visual_intent = bool(
        plan.get("required")
        or list(plan.get("assets") or [])
        or int(plan.get("min_assets") or 0) > 0
        or int(plan.get("max_assets") or 0) > 0
    )

    if minimum > 0:
        return {"min_visuals": minimum, "max_visuals": max(minimum, maximum)}
    if maximum > 0:
        return {
            "min_visuals": 1 if has_visual_intent else 0,
            "max_visuals": maximum,
        }
    if not has_visual_intent:
        return {"min_visuals": 0, "max_visuals": 0}

    sections = max(1, int(section_count or 1))
    adaptive_maximum = max(1, min(8, (sections + 1) // 2))
    return {"min_visuals": 1, "max_visuals": adaptive_maximum}
