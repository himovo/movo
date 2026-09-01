from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from app.enterprise_capabilities.browser.engine.action_target import element_can_receive, locator_match_score


@dataclass(frozen=True)
class ReplayTargetResolution:
    ref: str = ""
    reason: str = ""
    candidate_refs: tuple[str, ...] = ()


def resolve_replay_target(
    locator: Mapping[str, Any],
    elements: Iterable[object],
    *,
    tool: str,
) -> ReplayTargetResolution:
    """Resolve one cached target without changing ordinary planner policy.

    Semantic identity is the admission gate.  Live activation evidence is only
    a tie breaker between exact semantic matches, so unrelated controls can
    never be promoted merely because they are native buttons.
    """

    candidates: list[tuple[int, int, str, Mapping[str, Any]]] = []
    for raw in elements:
        if not isinstance(raw, Mapping) or not element_can_receive(tool, raw):
            continue
        semantic = locator_match_score(locator, raw)
        ref = str(raw.get("ref") or "").strip()
        if semantic <= 0 or not ref:
            continue
        candidates.append((semantic, _activation_rank(raw), ref, raw))
    if not candidates:
        return ReplayTargetResolution(reason="no_actionable_semantic_match")
    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    best_semantic = candidates[0][0]
    semantic_peers = [item for item in candidates if item[0] == best_semantic]
    best_activation = max(item[1] for item in semantic_peers)
    finalists = [item for item in semantic_peers if item[1] == best_activation]
    refs = tuple(item[2] for item in finalists)
    if len(finalists) == 1:
        return ReplayTargetResolution(ref=finalists[0][2], candidate_refs=refs)
    physical = {_physical_surface(item[3]) for item in finalists}
    if len(physical) == 1 and "" not in physical:
        return ReplayTargetResolution(
            ref=sorted(finalists, key=lambda item: item[2])[0][2],
            reason="equivalent_physical_surface",
            candidate_refs=refs,
        )
    return ReplayTargetResolution(
        reason="ambiguous_distinct_action_surfaces",
        candidate_refs=refs,
    )


def _activation_rank(element: Mapping[str, Any]) -> int:
    rank = 0
    if element.get("activationVerified") is True:
        rank += 40
    tag = str(element.get("tag") or "").casefold()
    role = str(element.get("role") or "").casefold()
    element_type = str(element.get("type") or "").casefold()
    if tag in {"button", "a", "input", "summary"}:
        rank += 20
    if role in {"button", "link", "menuitem", "option", "tab", "treeitem"}:
        rank += 10
    if element_type in {"button", "submit"}:
        rank += 8
    if element.get("controlledSurfaceId"):
        rank += 4
    return rank


def _physical_surface(element: Mapping[str, Any]) -> str:
    controlled = str(element.get("controlledSurfaceId") or "").strip()
    if controlled:
        return f"controlled:{controlled}"
    backend = str(element.get("backendNodeId") or "").strip()
    if backend:
        return f"backend:{element.get('frameDepth') or 0}:{backend}"
    selector = str(element.get("selector") or "").strip()
    return f"selector:{selector}" if selector else ""


__all__ = ["ReplayTargetResolution", "resolve_replay_target"]
