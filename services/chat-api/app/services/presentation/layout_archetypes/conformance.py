from __future__ import annotations

import re

from app.services.presentation.contracts import FreeformBlock, FreeformPageBlueprint

from .catalog import archetype_by_id


_TEXT_TYPES = frozenset({
    "text_box",
    "text",
    "title",
    "subtitle",
    "heading",
    "paragraph",
    "body",
    "label",
    "caption",
})


_SAFE_FALLBACKS = {
    "editorial": "dominant_panel",
    "structured": "numbered_list",
    "comparison_data": "left_right_comparison",
    "process_system": "layered_band",
    "media": "asymmetric_split",
}


def safe_fallback_archetype(archetype_id: str) -> str:
    spec = archetype_by_id(archetype_id)
    return _SAFE_FALLBACKS[spec.family]


def layout_conformance_issues(
    page: FreeformPageBlueprint,
    *,
    expected_archetype_id: str,
) -> list[str]:
    spec = archetype_by_id(expected_archetype_id)
    issues: list[str] = []
    if str(page.layout_type or "").strip() != expected_archetype_id:
        issues.append(f"layout_type_must_equal:{expected_archetype_id}")

    blocks = list(_flatten(list(page.blocks or [])))
    groups = [block for block in blocks if _type(block) == "group"]
    structural = [block for block in blocks if _type(block) in {"group", "rectangle"}]
    images = [block for block in blocks if _type(block) == "image"]
    charts = [
        block for block in blocks
        if "chart" in _type(block) or bool(dict(block.chart_data or {}))
    ]
    numeric_texts = [
        block for block in blocks
        if _is_text(block) and re.search(r"\d", str(block.content or ""))
    ]
    lines = [block for block in blocks if _type(block) == "line"]
    visible = [block for block in blocks if _visible(block)]
    visible_texts = [
        block for block in blocks
        if _is_text(block) and bool(str(block.content or "").strip())
    ]

    if len(visible) < 2:
        issues.append("layout_has_too_few_visible_blocks")
    if not visible_texts:
        issues.append("layout_has_no_visible_text")
    if spec.requires_image and not images:
        issues.append("assigned_layout_requires_image_block")
    if spec.requires_data and not charts and len(numeric_texts) < 2:
        issues.append("assigned_layout_requires_chart_or_metrics")
    if spec.requires_comparison and not _has_two_sides(blocks):
        issues.append("assigned_layout_requires_two_sides")
    if spec.requires_sequence and len(lines) == 0 and len(structural) < 3:
        issues.append("assigned_layout_requires_ordered_structure")
    if expected_archetype_id == "radial_feature_ring" and len(groups) < 4:
        issues.append("radial_feature_ring_requires_center_and_surrounding_groups")
    if expected_archetype_id == "architecture_blueprint" and len(structural) < 4:
        issues.append("architecture_blueprint_requires_layered_modules")
    if expected_archetype_id == "card_grid" and len(groups) < 3:
        issues.append("card_grid_requires_peer_groups")
    return issues


def _flatten(blocks: list[FreeformBlock]):
    for block in blocks:
        yield block
        yield from _flatten(list(block.children or []))


def _type(block: FreeformBlock) -> str:
    return str(block.type or "").strip().lower()


def _visible(block: FreeformBlock) -> bool:
    if _is_text(block):
        return bool(str(block.content or "").strip())
    return float(block.w or 0.0) > 0 and float(block.h or 0.0) > 0


def _is_text(block: FreeformBlock) -> bool:
    return _type(block) in _TEXT_TYPES


def _has_two_sides(blocks: list[FreeformBlock]) -> bool:
    left = any(_visible(block) and float(block.x or 0.0) < 0.42 for block in blocks)
    right = any(_visible(block) and float(block.x or 0.0) > 0.48 for block in blocks)
    return left and right


__all__ = ["layout_conformance_issues", "safe_fallback_archetype"]
