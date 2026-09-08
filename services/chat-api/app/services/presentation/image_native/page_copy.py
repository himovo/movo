from __future__ import annotations

import re
from typing import Any

from app.services.presentation.contracts import PageBrief


def source_texts_from_page(page_brief: PageBrief) -> list[dict[str, Any]]:
    """Build the grounded copy pool the page planner may condense for the slide."""

    if str(page_brief.page_type or "").strip().lower() == "cover":
        return _cover_texts(page_brief)

    texts: list[dict[str, Any]] = []
    _append_unique(texts, role="title", text=page_brief.key_takeaway, priority=10)
    for index, item in enumerate(list(page_brief.must_include or [])[:8], start=1):
        _append_unique(texts, role="body", text=item, priority=7, text_id=f"fact_{index}")
    return texts


def normalized_final_texts(
    planned_texts: list[Any],
    *,
    fallback: list[dict[str, Any]],
    max_items: int = 6,
    max_characters: int = 260,
) -> list[dict[str, Any]]:
    """Keep image-rendered copy concise, unique and bounded without truncation."""

    candidates = [_as_payload(item) for item in planned_texts]
    candidates = [item for item in candidates if str(item.get("text") or "").strip()]
    if not candidates:
        candidates = [dict(item) for item in fallback]

    ordered = sorted(
        enumerate(candidates),
        key=lambda pair: (-int(pair[1].get("priority") or 0), pair[0]),
    )
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    used_characters = 0
    for _index, item in ordered:
        text = str(item.get("text") or "").strip()
        if not text or text in seen or len(selected) >= max_items:
            continue
        if selected and used_characters + len(text) > max_characters:
            continue
        selected.append({
            "id": str(item.get("id") or f"copy_{len(selected) + 1}").strip(),
            "role": str(item.get("role") or "body").strip(),
            "text": text,
            "priority": int(item.get("priority") or 5),
        })
        seen.add(text)
        used_characters += len(text)
    return selected


def _cover_texts(page_brief: PageBrief) -> list[dict[str, Any]]:
    texts: list[dict[str, Any]] = []
    _append_unique(texts, role="title", text=page_brief.key_takeaway, priority=10)
    for item in list(page_brief.must_include or []) + list(page_brief.must_visualize or []):
        raw = str(item or "").strip()
        if _looks_like_time_or_metadata(raw):
            role = "subtitle" if re.search(r"(19|20)\d{2}|至今|today|present", raw, re.I) else "label"
            _append_unique(texts, role=role, text=raw, priority=7)
        if len(texts) >= 3:
            break
    return texts


def _append_unique(
    target: list[dict[str, Any]],
    *,
    role: str,
    text: Any,
    priority: int,
    text_id: str = "",
) -> None:
    raw = str(text or "").strip()
    if not raw or any(item["text"] == raw for item in target):
        return
    target.append({
        "id": text_id or role,
        "role": role,
        "text": raw,
        "priority": priority,
    })


def _looks_like_time_or_metadata(text: str) -> bool:
    lowered = text.lower()
    return bool(re.search(r"(19|20)\d{2}", text)) or any(
        token in lowered
        for token in ("至今", "today", "present", "演讲者", "讲者", "汇报人", "speaker", "内部分享")
    )


def _as_payload(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, "model_dump"):
        return dict(item.model_dump())
    return {}


__all__ = ["normalized_final_texts", "source_texts_from_page"]
