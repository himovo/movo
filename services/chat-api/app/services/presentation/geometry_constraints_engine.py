from __future__ import annotations

import logging
from typing import Callable, List, Tuple

from app.services.presentation.contracts import FreeformBlock
from app.services.presentation.layout_protocol import (
    MIN_LINE_LENGTH,
    SIBLING_OVERLAP_RATIO_THRESHOLD,
    text_geometry_requirements,
)
from app.services.presentation.layout_utils import rect_intersection_area as rect_intersection_area_util


Rect = Tuple[float, float, float, float]
IntentionalOverlapFn = Callable[[FreeformBlock, FreeformBlock], bool]
ShiftChildrenFn = Callable[[FreeformBlock, float, float], None]
DedupeFn = Callable[[List[FreeformBlock]], List[FreeformBlock]]

logger = logging.getLogger(__name__)


class GeometryConstraintsEngine:
    """Deterministic geometry constraint solver for already-absolutized blocks."""

    def apply_geometry_constraints(
        self,
        blocks: List[FreeformBlock],
        *,
        parent_rect: Rect = (0.0, 0.0, 1.0, 1.0),
        is_text_over_container_intended: IntentionalOverlapFn,
        shift_children: ShiftChildrenFn,
        dedupe_siblings: DedupeFn,
    ) -> List[FreeformBlock]:
        fixed: List[FreeformBlock] = []
        for block in list(blocks or []):
            out = self._fix_block_geometry(
                block,
                parent_rect=parent_rect,
                is_text_over_container_intended=is_text_over_container_intended,
                shift_children=shift_children,
                dedupe_siblings=dedupe_siblings,
            )
            if out is not None:
                fixed.append(out)
        return fixed

    def final_constrain_children(self, blocks: List[FreeformBlock]) -> List[FreeformBlock]:
        result: List[FreeformBlock] = []
        for block in list(blocks or []):
            out = block.model_copy(deep=True)
            if str(out.type or "").strip().lower() == "group" and out.children:
                group_rect = (float(out.x or 0), float(out.y or 0), float(out.w or 0), float(out.h or 0))
                out.children = self._constrain_children_within_group(list(out.children or []), group_rect=group_rect)
                out.children = self.final_constrain_children(list(out.children or []))
            result.append(out)
        return result

    def clamp_rect_to_container(
        self,
        *,
        x: float,
        y: float,
        w: float,
        h: float,
        container: Rect,
    ) -> Rect:
        cx, cy, cw, ch = container
        max_w = max(cw, 0.001)
        max_h = max(ch, 0.001)
        w = max(0.001, min(w, max_w))
        h = max(0.001, min(h, max_h))
        if w >= cw:
            x = cx
        if h >= ch:
            y = cy
        x = max(cx, min(x, cx + cw - w))
        y = max(cy, min(y, cy + ch - h))
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        w = max(0.001, min(w, 1.0 - x))
        h = max(0.001, min(h, 1.0 - y))
        return x, y, w, h

    def clamp_point_to_container(self, point: tuple[float, float], container: Rect) -> tuple[float, float]:
        x, y = point
        cx, cy, cw, ch = container
        px = max(cx, min(x, cx + cw))
        py = max(cy, min(y, cy + ch))
        return max(0.0, min(1.0, px)), max(0.0, min(1.0, py))

    @staticmethod
    def rect_intersection_area(left: Rect, right: Rect) -> float:
        return rect_intersection_area_util(left, right)

    def _fix_block_geometry(
        self,
        block: FreeformBlock,
        *,
        parent_rect: Rect,
        is_text_over_container_intended: IntentionalOverlapFn,
        shift_children: ShiftChildrenFn,
        dedupe_siblings: DedupeFn,
    ) -> FreeformBlock | None:
        out = block.model_copy(deep=True)
        block_type = str(out.type or "").strip().lower()
        if block_type == "line":
            return self.fix_line_geometry(out, parent_rect=parent_rect)

        out.x, out.y, out.w, out.h = self.clamp_rect_to_container(
            x=float(out.x or 0.0),
            y=float(out.y or 0.0),
            w=max(float(out.w or 0.0), 0.001),
            h=max(float(out.h or 0.0), 0.001),
            container=parent_rect,
        )

        if block_type == "text_box":
            out = self.enforce_text_readability_bounds(out, parent_rect=parent_rect)

        if out.children:
            child_parent = (out.x, out.y, out.w, out.h) if block_type == "group" else parent_rect
            out.children = self.apply_geometry_constraints(
                list(out.children or []),
                parent_rect=child_parent,
                is_text_over_container_intended=is_text_over_container_intended,
                shift_children=shift_children,
                dedupe_siblings=dedupe_siblings,
            )
            if block_type == "group":
                out.children = dedupe_siblings(list(out.children or []))
                out.children = self._constrain_children_within_group(list(out.children or []), group_rect=child_parent)
                out.children = self._resolve_group_sibling_overlaps(
                    list(out.children or []),
                    group_rect=child_parent,
                    is_text_over_container_intended=is_text_over_container_intended,
                    shift_children=shift_children,
                )

        return out

    def fix_line_geometry(self, block: FreeformBlock, *, parent_rect: Rect) -> FreeformBlock | None:
        out = block.model_copy(deep=True)
        x1 = float(out.x or 0.0)
        y1 = float(out.y or 0.0)
        x2 = float(out.x2 if out.x2 is not None else x1)
        y2 = float(out.y2 if out.y2 is not None else y1)
        route = str(out.style.get("route") or "auto").strip().lower()
        if route in {"h", "horizontal"}:
            y2 = y1
        elif route in {"v", "vertical"}:
            x2 = x1
        else:
            if abs(x2 - x1) >= abs(y2 - y1):
                y2 = y1
            else:
                x2 = x1
            route = "auto"
        x1, y1 = self.clamp_point_to_container((x1, y1), parent_rect)
        x2, y2 = self.clamp_point_to_container((x2, y2), parent_rect)
        if abs(x2 - x1) < MIN_LINE_LENGTH and abs(y2 - y1) < MIN_LINE_LENGTH:
            logger.debug(
                "presentation_drop_short_line id=%s len=(%.4f,%.4f)",
                str(out.id or "").strip(),
                abs(x2 - x1),
                abs(y2 - y1),
            )
            return None
        out.style["route"] = route
        out.x = min(x1, x2)
        out.y = min(y1, y2)
        out.w = max(abs(x2 - x1), 0.001)
        out.h = max(abs(y2 - y1), 0.001)
        out.x2 = x2
        out.y2 = y2
        return out

    def enforce_text_readability_bounds(self, block: FreeformBlock, *, parent_rect: Rect) -> FreeformBlock:
        out = block.model_copy(deep=True)
        text = str(out.content or "").strip()
        if not text:
            return out
        style = dict(out.style or {})
        try:
            font_size = float(style.get("font_size")) if style.get("font_size") not in (None, "") else None
        except Exception:
            font_size = None
        min_w, min_h = text_geometry_requirements(text, font_size=font_size)
        out.w = max(float(out.w or 0.0), min_w)
        out.h = max(float(out.h or 0.0), min_h)
        out.x, out.y, out.w, out.h = self.clamp_rect_to_container(
            x=float(out.x or 0.0),
            y=float(out.y or 0.0),
            w=float(out.w or 0.0),
            h=float(out.h or 0.0),
            container=parent_rect,
        )
        return out

    def _constrain_children_within_group(self, children: List[FreeformBlock], *, group_rect: Rect) -> List[FreeformBlock]:
        constrained: List[FreeformBlock] = []
        for child in list(children or []):
            out = child.model_copy(deep=True)
            block_type = str(out.type or "").strip().lower()
            if block_type == "line":
                fixed_line = self.fix_line_geometry(out, parent_rect=group_rect)
                if fixed_line is not None:
                    constrained.append(fixed_line)
                continue
            out.x, out.y, out.w, out.h = self.clamp_rect_to_container(
                x=float(out.x or 0.0),
                y=float(out.y or 0.0),
                w=max(float(out.w or 0.0), 0.001),
                h=max(float(out.h or 0.0), 0.001),
                container=group_rect,
            )
            constrained.append(out)
        return constrained

    def _resolve_group_sibling_overlaps(
        self,
        children: List[FreeformBlock],
        *,
        group_rect: Rect,
        is_text_over_container_intended: IntentionalOverlapFn,
        shift_children: ShiftChildrenFn,
    ) -> List[FreeformBlock]:
        adjusted = [child.model_copy(deep=True) for child in list(children or [])]
        for index in range(len(adjusted)):
            left = adjusted[index]
            left_type = str(left.type or "").strip().lower()
            if left_type == "line":
                continue
            for right_index in range(index + 1, len(adjusted)):
                right = adjusted[right_index]
                right_type = str(right.type or "").strip().lower()
                if right_type == "line":
                    continue
                if is_text_over_container_intended(left, right):
                    continue
                attempt = 0
                while attempt < 8:
                    left_rect = (float(left.x or 0.0), float(left.y or 0.0), float(left.w or 0.0), float(left.h or 0.0))
                    right_rect = (float(right.x or 0.0), float(right.y or 0.0), float(right.w or 0.0), float(right.h or 0.0))
                    overlap = self.rect_intersection_area(left_rect, right_rect)
                    smaller = min(max(float(left.w or 0.0) * float(left.h or 0.0), 0.0001), max(float(right.w or 0.0) * float(right.h or 0.0), 0.0001))
                    if overlap <= 0.0 or overlap / smaller < SIBLING_OVERLAP_RATIO_THRESHOLD:
                        break
                    old_rx, old_ry = float(right.x or 0.0), float(right.y or 0.0)
                    dx, dy = self._separation_delta(anchor_rect=left_rect, mover_rect=right_rect)
                    right.x = old_rx + dx
                    right.y = old_ry + dy
                    right.x, right.y, right.w, right.h = self.clamp_rect_to_container(
                        x=float(right.x or 0.0),
                        y=float(right.y or 0.0),
                        w=max(float(right.w or 0.0), 0.001),
                        h=max(float(right.h or 0.0), 0.001),
                        container=group_rect,
                    )
                    delta_x = float(right.x or 0) - old_rx
                    delta_y = float(right.y or 0) - old_ry
                    if delta_x == 0.0 and delta_y == 0.0:
                        alt_dx, alt_dy = self._separation_delta(anchor_rect=left_rect, mover_rect=right_rect, prefer_secondary_axis=True)
                        right.x = old_rx + alt_dx
                        right.y = old_ry + alt_dy
                        right.x, right.y, right.w, right.h = self.clamp_rect_to_container(
                            x=float(right.x or 0.0),
                            y=float(right.y or 0.0),
                            w=max(float(right.w or 0.0), 0.001),
                            h=max(float(right.h or 0.0), 0.001),
                            container=group_rect,
                        )
                        delta_x = float(right.x or 0) - old_rx
                        delta_y = float(right.y or 0) - old_ry
                    if (delta_x != 0 or delta_y != 0) and right.children:
                        shift_children(right, delta_x, delta_y)
                    attempt += 1
        return adjusted

    def _separation_delta(
        self,
        *,
        anchor_rect: Rect,
        mover_rect: Rect,
        prefer_secondary_axis: bool = False,
    ) -> tuple[float, float]:
        ax, ay, aw, ah = anchor_rect
        mx, my, mw, mh = mover_rect
        overlap_w = min(ax + aw, mx + mw) - max(ax, mx)
        overlap_h = min(ay + ah, my + mh) - max(ay, my)
        if overlap_w <= 0.0 or overlap_h <= 0.0:
            return 0.0, 0.0
        margin = 0.012
        move_x_first = overlap_w <= overlap_h
        if prefer_secondary_axis:
            move_x_first = not move_x_first
        acx = ax + aw / 2.0
        acy = ay + ah / 2.0
        mcx = mx + mw / 2.0
        mcy = my + mh / 2.0
        sign_x = 1.0 if mcx >= acx else -1.0
        sign_y = 1.0 if mcy >= acy else -1.0
        if move_x_first:
            return sign_x * (overlap_w + margin), 0.0
        return 0.0, sign_y * (overlap_h + margin)
