from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from app.services.presentation.contracts import FreeformBlock
from app.services.presentation.layout_protocol import text_geometry_requirements


Rect = Tuple[float, float, float, float]


@dataclass(frozen=True)
class ReflowConfig:
    min_gap: float = 0.006
    default_gap: float = 0.012
    row_band_tolerance: float = 0.05
    max_row_items: int = 8
    title_font_floor: int = 28
    body_font_floor: int = 20
    label_font_floor: int = 18
    container_inner_padding: float = 0.008


class ContentDrivenReflowEngine:
    """Deterministic same-page reflow engine (no split page, no coordinate mapping)."""

    _CONTAINER_TYPES = frozenset({"rectangle", "circle", "image", "group"})
    _TEXT_TYPES = frozenset({"text_box", "icon"})

    def __init__(self, *, config: ReflowConfig | None = None) -> None:
        self._cfg = config or ReflowConfig()

    def reflow_page(self, blocks: List[FreeformBlock], *, page_rect: Rect = (0.0, 0.0, 1.0, 1.0)) -> List[FreeformBlock]:
        return self._reflow_level(list(blocks or []), container_rect=page_rect)

    def _reflow_level(self, siblings: List[FreeformBlock], *, container_rect: Rect) -> List[FreeformBlock]:
        adjusted = [b.model_copy(deep=True) for b in list(siblings or [])]

        for idx, block in enumerate(adjusted):
            if str(block.type or "").strip().lower() == "group" and block.children:
                group_rect = (
                    float(block.x or 0.0),
                    float(block.y or 0.0),
                    max(float(block.w or 0.0), 0.001),
                    max(float(block.h or 0.0), 0.001),
                )
                block.children = self._reflow_level(list(block.children or []), container_rect=group_rect)
                adjusted[idx] = block

        adjusted = self._reflow_rows(adjusted, container_rect=container_rect)
        return adjusted

    def _reflow_rows(self, siblings: List[FreeformBlock], *, container_rect: Rect) -> List[FreeformBlock]:
        if len(siblings) < 3:
            return siblings
        cx, cy, cw, ch = container_rect
        if cw <= 0 or ch <= 0:
            return siblings

        row_bands: Dict[int, List[int]] = {}
        tol = max(self._cfg.row_band_tolerance * ch, 0.035)
        for idx, block in enumerate(siblings):
            b_type = str(block.type or "").strip().lower()
            if b_type not in self._CONTAINER_TYPES:
                continue
            if self._is_background_like(block):
                continue
            y_mid = float(block.y or 0.0) + float(block.h or 0.0) / 2.0
            band = int(round((y_mid - cy) / max(tol, 0.001)))
            row_bands.setdefault(band, []).append(idx)

        for _, indices in row_bands.items():
            if len(indices) < 3 or len(indices) > self._cfg.max_row_items:
                continue
            indices.sort(key=lambda i: float(siblings[i].x or 0.0))
            if not self._needs_row_refit(siblings, indices, container_rect):
                continue
            self._refit_row(siblings, indices, container_rect)
            self._reflow_bound_content_in_row(siblings, indices)

        return siblings

    def _needs_row_refit(self, siblings: List[FreeformBlock], indices: List[int], container_rect: Rect) -> bool:
        cx, _, cw, _ = container_rect
        row = [siblings[i] for i in indices]
        left = min(float(item.x or 0.0) for item in row)
        right = max(float(item.x or 0.0) + max(float(item.w or 0.0), 0.001) for item in row)
        span = right - left
        overflow = right > cx + cw + 0.005
        underfilled = span < cw * 0.72
        overlap = self._has_row_overlap(row)
        return overflow or overlap or underfilled

    def _has_row_overlap(self, row: List[FreeformBlock]) -> bool:
        for i in range(len(row) - 1):
            a = row[i]
            b = row[i + 1]
            ax = float(a.x or 0.0) + max(float(a.w or 0.0), 0.001)
            bx = float(b.x or 0.0)
            if bx < ax - 0.004:
                return True
        return False

    def _refit_row(self, siblings: List[FreeformBlock], indices: List[int], container_rect: Rect) -> None:
        cx, _, cw, _ = container_rect
        row = [siblings[i] for i in indices]
        original_widths = [max(float(item.w or 0.0), 0.001) for item in row]
        min_widths = [max(w * 0.62, 0.07) for w in original_widths]
        count = len(row)
        target_gap = self._cfg.default_gap
        gaps_total = target_gap * max(count - 1, 0)
        available = max(cw - gaps_total, 0.001)

        width_sum = sum(original_widths)
        if width_sum <= available:
            new_widths = list(original_widths)
        else:
            min_total = sum(min_widths)
            if min_total > available:
                target_gap = max(self._cfg.min_gap, (cw - min_total) / max(count - 1, 1))
                gaps_total = target_gap * max(count - 1, 0)
                available = max(cw - gaps_total, 0.001)
            scale = max(min(available / max(width_sum, 0.001), 1.0), 0.0)
            scaled = [w * scale for w in original_widths]
            new_widths = [max(scaled[i], min_widths[i]) for i in range(count)]
            overflow = sum(new_widths) - available
            if overflow > 0:
                shrinkable = [new_widths[i] - min_widths[i] for i in range(count)]
                shrink_total = sum(max(s, 0.0) for s in shrinkable)
                if shrink_total > 0:
                    ratio = min(1.0, overflow / shrink_total)
                    new_widths = [
                        new_widths[i] - max(shrinkable[i], 0.0) * ratio
                        for i in range(count)
                    ]
            # Final hard clamp: if still overflowing after shrink, scale row to fit.
            post_total = sum(new_widths)
            if post_total > available and post_total > 0:
                fit_scale = available / post_total
                new_widths = [max(w * fit_scale, 0.001) for w in new_widths]

        total_width = sum(new_widths) + target_gap * max(count - 1, 0)
        start_x = cx + max((cw - total_width) / 2.0, 0.0)

        for rank, idx in enumerate(indices):
            block = siblings[idx]
            block.x = start_x + rank * target_gap + sum(new_widths[:rank])
            max_allowed_w = max((cx + cw) - float(block.x or 0.0), 0.001)
            block.w = min(max(new_widths[rank], 0.001), max_allowed_w)
            siblings[idx] = block

    def _reflow_bound_content_in_row(self, siblings: List[FreeformBlock], row_indices: List[int]) -> None:
        row_set = set(row_indices)
        for container_idx in row_indices:
            container = siblings[container_idx]
            bound = self._bound_content_indices_for_container(siblings, row_set=row_set, container_idx=container_idx)
            if not bound:
                continue
            self._layout_content_inside_container(siblings, container_idx=container_idx, content_indices=bound)

    def _bound_content_indices_for_container(
        self,
        siblings: List[FreeformBlock],
        *,
        row_set: set[int],
        container_idx: int,
    ) -> List[int]:
        container = siblings[container_idx]
        cid = str(container.id or "").strip()
        c_rect = (
            float(container.x or 0.0),
            float(container.y or 0.0),
            max(float(container.w or 0.0), 0.001),
            max(float(container.h or 0.0), 0.001),
        )
        bound: List[int] = []
        for idx, block in enumerate(siblings):
            if idx in row_set:
                continue
            block_type = str(block.type or "").strip().lower()
            if block_type not in self._TEXT_TYPES:
                continue

            if str(block.container_id or "").strip() == cid:
                bound.append(idx)
                continue

            if self._center_inside(block, c_rect):
                bound.append(idx)
                continue
        bound.sort(key=lambda i: (float(siblings[i].y or 0.0), float(siblings[i].x or 0.0)))
        return bound

    def _layout_content_inside_container(
        self,
        siblings: List[FreeformBlock],
        *,
        container_idx: int,
        content_indices: List[int],
    ) -> None:
        container = siblings[container_idx]
        cx = float(container.x or 0.0)
        cy = float(container.y or 0.0)
        cw = max(float(container.w or 0.0), 0.001)
        ch = max(float(container.h or 0.0), 0.001)
        pad = self._cfg.container_inner_padding
        ix = cx + pad
        iy = cy + pad
        iw = max(cw - 2 * pad, 0.02)
        ih = max(ch - 2 * pad, 0.02)
        gap = max(self._cfg.min_gap, 0.008)
        if len(content_indices) > 1:
            gap = min(gap, ih / max(len(content_indices) * 2, 1))

        items = [siblings[i].model_copy(deep=True) for i in content_indices]
        heights = [self._target_item_height(item, inner_w=iw) for item in items]
        total_h = sum(heights) + gap * max(len(items) - 1, 0)

        if total_h > ih and len(items) > 0:
            self._shrink_text_group(items, target_height=ih, widths=[iw] * len(items))
            heights = [self._target_item_height(item, inner_w=iw) for item in items]
            total_h = sum(heights) + gap * max(len(items) - 1, 0)

        if total_h > ih:
            ratio = ih / max(total_h, 0.001)
            heights = [max(h * ratio, 0.001) for h in heights]
            total_h = sum(heights) + gap * max(len(items) - 1, 0)
        # Hard fit pass: if floors still overflow, scale heights to fit exactly.
        if total_h > ih and sum(heights) > 0:
            space_for_heights = max(ih - gap * max(len(items) - 1, 0), 0.001)
            fit_ratio = space_for_heights / max(sum(heights), 0.001)
            heights = [max(h * fit_ratio, 0.001) for h in heights]
            total_h = sum(heights) + gap * max(len(items) - 1, 0)

        y = iy + max((ih - total_h) / 2.0, 0.0)
        for idx, item in enumerate(items):
            item_type = str(item.type or "").strip().lower()
            if item_type == "icon":
                icon_size = min(max(heights[idx], 0.02), min(iw * 0.30, 0.06))
                item.w = icon_size
                item.h = icon_size
                item.x = ix + max((iw - icon_size) / 2.0, 0.0)
                item.y = y
            else:
                item.x = ix
                item.y = y
                item.w = iw
                item.h = max(heights[idx], 0.02)
                self._finalize_text_item(item, inner_w=iw, inner_h=ih)
            y += heights[idx] + gap
            siblings[content_indices[idx]] = item

    def _shrink_text_if_needed(self, block: FreeformBlock, *, bounds: Rect) -> None:
        text = str(block.content or "").strip()
        if not text:
            return
        _, _, bw, bh = bounds
        font_size = self._style_number(dict(block.style or {}).get("font_size")) or 24.0
        line_height = self._style_number(dict(block.style or {}).get("line_height")) or 1.35
        floor = self._font_floor(block)

        while font_size > floor:
            needed_h = self._estimate_text_height(text, width=max(float(block.w or 0.0), 0.001), font_size=font_size, line_height=line_height)
            if needed_h <= min(float(block.h or 0.0), bh):
                break
            font_size -= 1.0

        block.style = dict(block.style or {})
        block.style["font_size"] = int(max(font_size, floor))
        min_w, min_h = text_geometry_requirements(text, font_size=font_size)
        block.w = max(float(block.w or 0.0), min(min_w, bw))
        block.h = max(float(block.h or 0.0), min(min_h, bh))

    def _target_item_height(self, block: FreeformBlock, *, inner_w: float) -> float:
        block_type = str(block.type or "").strip().lower()
        if block_type == "icon":
            return min(max(float(block.h or 0.0), 0.03), 0.06)
        text = str(block.content or "").strip()
        if not text:
            return max(float(block.h or 0.0), 0.04)
        style = dict(block.style or {})
        font_size = self._style_number(style.get("font_size")) or 24.0
        line_height = self._style_number(style.get("line_height")) or 1.35
        needed = self._estimate_text_height(text, width=max(inner_w, 0.02), font_size=font_size, line_height=line_height)
        min_w, min_h = text_geometry_requirements(text, font_size=font_size)
        floor_h = min_h
        return max(needed, floor_h, 0.04)

    def _shrink_text_group(self, items: List[FreeformBlock], *, target_height: float, widths: List[float]) -> None:
        if not items:
            return
        max_reducible = 0
        for item in list(items or []):
            if str(item.type or "").strip().lower() != "text_box":
                continue
            style = dict(item.style or {})
            size = int(self._style_number(style.get("font_size")) or 24.0)
            floor = int(self._font_floor(item))
            max_reducible = max(max_reducible, max(size - floor, 0))
        max_iters = max(8, max_reducible + 2)
        # Reduce only text font sizes, keep hierarchy by role floors.
        for _ in range(max_iters):
            current = 0.0
            for i, item in enumerate(items):
                h = self._target_item_height(item, inner_w=widths[i])
                current += h
            current += 0.008 * max(len(items) - 1, 0)
            if current <= target_height:
                return

            changed = False
            for item in items:
                if str(item.type or "").strip().lower() != "text_box":
                    continue
                style = dict(item.style or {})
                size = self._style_number(style.get("font_size")) or 24.0
                floor = self._font_floor(item)
                if size > floor:
                    style["font_size"] = int(size - 1.0)
                    item.style = style
                    changed = True
            if not changed:
                return

    def _finalize_text_item(self, block: FreeformBlock, *, inner_w: float, inner_h: float) -> None:
        self._shrink_text_if_needed(block, bounds=(float(block.x or 0.0), float(block.y or 0.0), inner_w, inner_h))

    def _font_floor(self, block: FreeformBlock) -> int:
        role = str(block.role or "").strip().lower()
        if role in {"title", "heading", "subtitle"}:
            return self._cfg.title_font_floor
        if role == "label":
            return self._cfg.label_font_floor
        return self._cfg.body_font_floor

    def _estimate_text_height(self, text: str, *, width: float, font_size: float, line_height: float) -> float:
        width_px = max(width * 1600.0, 40.0)
        chars_per_line = max(int(math.floor(width_px / max(font_size * 0.95, 10.0))), 2)
        lines = self._estimate_line_count(text, chars_per_line)
        return (lines * font_size * line_height) / 900.0 + 0.01

    def _estimate_line_count(self, text: str, chars_per_line: int) -> int:
        cleaned = str(text or "").replace("<br/>", "\n").strip()
        if not cleaned:
            return 1
        total = 0
        for part in cleaned.split("\n"):
            chunk = reflow_len(part)
            total += max(1, int(math.ceil(chunk / max(chars_per_line, 1))))
        return max(total, 1)

    def _is_background_like(self, block: FreeformBlock) -> bool:
        role = str(block.role or "").strip().lower()
        if role in {"background", "surface"}:
            return True
        return float(block.w or 0.0) >= 0.90 and float(block.h or 0.0) >= 0.90

    def _clamp_rect(self, block: FreeformBlock, container: Rect) -> Rect:
        cx, cy, cw, ch = container
        w = max(min(float(block.w or 0.0), cw), 0.001)
        h = max(min(float(block.h or 0.0), ch), 0.001)
        x = max(cx, min(float(block.x or 0.0), cx + cw - w))
        y = max(cy, min(float(block.y or 0.0), cy + ch - h))
        return x, y, w, h

    def _intersection_area(self, left: Rect, right: Rect) -> float:
        lx, ly, lw, lh = left
        rx, ry, rw, rh = right
        overlap_w = min(lx + lw, rx + rw) - max(lx, rx)
        overlap_h = min(ly + lh, ry + rh) - max(ly, ry)
        if overlap_w <= 0.0 or overlap_h <= 0.0:
            return 0.0
        return overlap_w * overlap_h

    def _center_inside(self, block: FreeformBlock, container: Rect) -> bool:
        bx = float(block.x or 0.0)
        by = float(block.y or 0.0)
        bw = max(float(block.w or 0.0), 0.001)
        bh = max(float(block.h or 0.0), 0.001)
        cx = bx + bw / 2.0
        cy = by + bh / 2.0
        rx, ry, rw, rh = container
        return rx <= cx <= rx + rw and ry <= cy <= ry + rh

    def _style_number(self, value: object) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except Exception:
            return None


def reflow_len(text: str) -> int:
    token = str(text or "").strip()
    if not token:
        return 0
    # Count CJK as 1; latin words and punctuation are already represented in char count.
    return len(token)
