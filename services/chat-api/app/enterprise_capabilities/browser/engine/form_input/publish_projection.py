"""Build one coherent browser-publish payload from predecessor artifacts."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from app.enterprise_capabilities.content.publish_assembly.media_anchors import end_of_body_anchor


_PRIMARY_CONTENT_KEYS: Tuple[Tuple[str, int], ...] = (
    ("final_publish_markdown", 120),
    ("article_markdown", 110),
    ("report_markdown", 100),
    ("edited_markdown", 90),
    ("transformed_markdown", 80),
    ("markdown", 70),
    ("content", 60),
    ("dynamic_markdown", 30),
)


@dataclass(frozen=True)
class BrowserPublishProjection:
    source_id: str
    payload: Dict[str, Any]


def project_browser_publish_payload(
    artifacts: Mapping[str, Any],
    *,
    output_spec: Mapping[str, Any] | None = None,
) -> BrowserPublishProjection | None:
    """Select one authoritative body and safely merge supporting media.

    Each browser-bound generation node owns a local ``publish_payload``.
    When several such nodes feed one browser node, their body-relative media
    anchors are not interchangeable. This projection keeps title/body/media
    from one authoritative payload and only imports additional media when the
    authoritative payload does not already satisfy the requested media count.
    """

    sources = _payload_sources(artifacts)
    if not sources:
        return None

    primary_id, _primary_artifact, primary_payload, _primary_index = max(
        sources,
        key=lambda item: (
            _content_authority(item[1], item[2]),
            -item[3],
        ),
    )
    projected = deepcopy(primary_payload)
    primary_media = _valid_media(projected.get("media"))
    projected["media"] = primary_media

    requested = _requested_media_count(output_spec or {})
    if requested is None:
        requested = len(primary_media) if primary_media else None
    missing = max(0, requested - len(primary_media)) if requested is not None else None
    if missing == 0:
        return BrowserPublishProjection(source_id=primary_id, payload=projected)

    body_markdown = str(projected.get("body_markdown") or "")
    body_plain = str(projected.get("body_plain_text") or body_markdown)
    seen = {
        str(item.get("source_url") or "").strip()
        for item in primary_media
        if isinstance(item, dict)
    }
    supplements: List[Dict[str, Any]] = []
    for source_id, _artifact, payload, _index in sources:
        if source_id == primary_id:
            continue
        for item in _valid_media(payload.get("media")):
            url = str(item.get("source_url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            supplements.append(
                _rebase_media(
                    item,
                    body_markdown=body_markdown,
                    body_plain=body_plain,
                )
            )
            if missing is not None and len(supplements) >= missing:
                break
        if missing is not None and len(supplements) >= missing:
            break

    for item in supplements:
        item["order"] = len(projected["media"])
        projected["media"].append(item)
    return BrowserPublishProjection(source_id=primary_id, payload=projected)


def _payload_sources(
    artifacts: Mapping[str, Any],
) -> List[Tuple[str, Dict[str, Any], Dict[str, Any], int]]:
    out: List[Tuple[str, Dict[str, Any], Dict[str, Any], int]] = []
    for index, (source_id, raw_artifact) in enumerate(artifacts.items()):
        if not isinstance(raw_artifact, dict):
            continue
        payload = raw_artifact.get("publish_payload")
        if not _is_publish_payload(payload):
            continue
        out.append((str(source_id), raw_artifact, dict(payload), index))
    return out


def _is_publish_payload(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and str(value.get("schema_version") or "").strip() == "1.0"
        and any(
            str(value.get(key) or "").strip()
            for key in ("title", "body_markdown", "body_plain_text", "body_html")
        )
    )


def _content_authority(artifact: Dict[str, Any], payload: Dict[str, Any]) -> int:
    score = 0
    for key, weight in _PRIMARY_CONTENT_KEYS:
        if str(artifact.get(key) or "").strip():
            score = max(score, weight)
    if str(payload.get("title") or "").strip():
        score += 8
    body = str(payload.get("body_markdown") or payload.get("body_plain_text") or "")
    score += min(12, len(body) // 500)
    return score


def _requested_media_count(output_spec: Mapping[str, Any]) -> int | None:
    roots: Iterable[Any] = (
        output_spec,
        output_spec.get("effective_policy"),
        output_spec.get("generation_policy"),
    )
    for root in roots:
        if not isinstance(root, dict):
            continue
        compose = root.get("compose_policy") if isinstance(root.get("compose_policy"), dict) else root
        preferences = (
            compose.get("visual_preferences")
            if isinstance(compose.get("visual_preferences"), dict)
            else {}
        )
        counts: Dict[str, int] = {}
        for key in ("min_images", "max_images"):
            value = preferences.get(key)
            if isinstance(value, bool):
                continue
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
            if count >= 0:
                counts[key] = count
        if counts.get("min_images", 0) > 0:
            return counts["min_images"]
        if counts.get("max_images", 0) > 0:
            return counts["max_images"]
        if counts:
            return 0
    return None


def _valid_media(value: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in list(value or []):
        if not isinstance(item, dict):
            continue
        if not str(item.get("source_url") or "").strip():
            continue
        out.append(deepcopy(item))
    return out


def _rebase_media(
    item: Dict[str, Any],
    *,
    body_markdown: str,
    body_plain: str,
) -> Dict[str, Any]:
    media = deepcopy(item)
    if _anchor_resolves(media, body_plain):
        return media
    fallback = end_of_body_anchor(body_markdown or body_plain)
    media["anchor_after_text"] = fallback.anchor_after_text
    media["anchor_before_text"] = fallback.anchor_before_text
    media["anchor_plain_offset"] = fallback.anchor_plain_offset
    return media


def _anchor_resolves(item: Dict[str, Any], body_plain: str) -> bool:
    body = _compact(body_plain)
    if not body:
        return False
    after = _compact(str(item.get("anchor_after_text") or ""))
    before = _compact(str(item.get("anchor_before_text") or ""))
    return bool((after and after in body) or (before and before in body))


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


__all__ = ["BrowserPublishProjection", "project_browser_publish_payload"]
