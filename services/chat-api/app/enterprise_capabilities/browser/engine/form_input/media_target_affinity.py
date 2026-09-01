from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


@dataclass(frozen=True)
class MediaTargetHint:
    selector: str = ""
    scope_id: str = ""
    semantic_purpose: str = ""
    tag: str = ""
    name: str = ""


def capture_media_target_hint(
    observation: Optional[Observation],
    ref: str,
) -> Optional[MediaTargetHint]:
    if observation is None or not ref:
        return None
    target = next((
        element
        for element in list(observation.elements or [])
        if isinstance(element, dict)
        and str(element.get("ref") or "").strip() == ref
    ), None)
    if target is None:
        return None
    return MediaTargetHint(
        selector=str(target.get("selector") or "").strip(),
        scope_id=str(
            target.get("scopeId") or target.get("scope_id") or ""
        ).strip(),
        semantic_purpose=str(
            target.get("semanticPurpose") or ""
        ).strip().casefold(),
        tag=str(target.get("tag") or "").strip().casefold(),
        name=str(target.get("name") or target.get("text") or "").strip().casefold(),
    )


def media_target_affinity_score(
    element: Dict[str, Any],
    hint: Optional[MediaTargetHint],
) -> int:
    if hint is None:
        return 0
    selector = str(element.get("selector") or "").strip()
    if hint.selector and selector == hint.selector:
        return 1000

    score = 0
    scope_id = str(
        element.get("scopeId") or element.get("scope_id") or ""
    ).strip()
    purpose = str(element.get("semanticPurpose") or "").strip().casefold()
    tag = str(element.get("tag") or "").strip().casefold()
    name = str(element.get("name") or element.get("text") or "").strip().casefold()
    if hint.scope_id and scope_id == hint.scope_id:
        score += 30
    if hint.semantic_purpose and purpose == hint.semantic_purpose:
        score += 25
    if hint.tag and tag == hint.tag:
        score += 10
    if hint.name and name == hint.name:
        score += 15
    return score


__all__ = [
    "MediaTargetHint",
    "capture_media_target_hint",
    "media_target_affinity_score",
]
