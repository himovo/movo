from __future__ import annotations

import math
from typing import List, Tuple

from app.services.presentation.contracts import FreeformBlock


Rect = Tuple[float, float, float, float]


def id_stem(value: str) -> str:
    stem = str(value or "").strip().lower()
    if not stem:
        return ""
    for suffix in ("_title", "_subtitle", "_text", "_body", "_label", "_header", "_content", "_main"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    return stem


def rect_intersection_area(left: Rect, right: Rect) -> float:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    if not all(math.isfinite(v) for v in (lx, ly, lw, lh, rx, ry, rw, rh)):
        return 0.0
    overlap_w = min(lx + lw, rx + rw) - max(lx, rx)
    overlap_h = min(ly + lh, ry + rh) - max(ly, ry)
    if overlap_w <= 0.0 or overlap_h <= 0.0:
        return 0.0
    return overlap_w * overlap_h


def is_text_over_container_intended(first: FreeformBlock, second: FreeformBlock) -> bool:
    first_type = str(first.type or "").strip().lower()
    second_type = str(second.type or "").strip().lower()
    if first_type == "text_box" and second_type in {"rectangle", "circle", "image", "group"}:
        text_block, container = first, second
    elif second_type == "text_box" and first_type in {"rectangle", "circle", "image", "group"}:
        text_block, container = second, first
    else:
        return False

    container_id = str(text_block.container_id or "").strip()
    if container_id and container_id == str(container.id or "").strip():
        return True

    text_block_stem = id_stem(str(text_block.id or ""))
    shape_stem = id_stem(str(container.id or ""))
    if text_block_stem and shape_stem and text_block_stem == shape_stem:
        return True

    tx, ty, tw, th = float(text_block.x or 0.0), float(text_block.y or 0.0), float(text_block.w or 0.0), float(text_block.h or 0.0)
    cx, cy, cw, ch = float(container.x or 0.0), float(container.y or 0.0), float(container.w or 0.0), float(container.h or 0.0)
    inter = rect_intersection_area((tx, ty, tw, th), (cx, cy, cw, ch))
    text_area = max(tw * th, 0.0001)
    covered_ratio = inter / text_area
    if covered_ratio < 0.60:
        return False

    role = str(container.role or "").strip().lower()
    block_id = str(container.id or "").strip().lower()
    if role in {"background", "surface"} and float(container.w or 0) >= 0.90 and float(container.h or 0) >= 0.90:
        return True
    return role in {"container", "panel", "card", "band", "group", "surface", "slab"} or any(
        token in block_id for token in ("panel", "card", "container", "band", "box", "block", "bg", "background", "slab")
    )


def render_order_key(block: FreeformBlock) -> tuple[int, float]:
    block_type = str(block.type or "").strip().lower()
    role = str(block.role or "").strip().lower()
    if role in {"background", "surface", "container", "panel", "card"}:
        layer = 0
    elif block_type == "group":
        layer = 1
    elif block_type in {"rectangle", "circle", "image"}:
        layer = 2
    elif block_type == "line":
        layer = 3
    else:
        layer = 4
    return (layer, float(block.y or 0.0))


def flatten_blocks(blocks: List[FreeformBlock]) -> List[FreeformBlock]:
    flat: List[FreeformBlock] = []
    for block in list(blocks or []):
        flat.append(block)
        if block.children:
            flat.extend(flatten_blocks(list(block.children or [])))
    return flat


def children_bbox(blocks: List[FreeformBlock]) -> tuple[float, float, float, float]:
    x1 = 1.0
    y1 = 1.0
    x2 = 0.0
    y2 = 0.0
    for block in list(blocks or []):
        bx1 = float(block.x or 0.0)
        by1 = float(block.y or 0.0)
        bx2 = float(block.x2 if block.x2 is not None else (block.x or 0.0) + (block.w or 0.0))
        by2 = float(block.y2 if block.y2 is not None else (block.y or 0.0) + (block.h or 0.0))
        x1 = min(x1, bx1)
        y1 = min(y1, by1)
        x2 = max(x2, bx2)
        y2 = max(y2, by2)
    return x1, y1, x2, y2
