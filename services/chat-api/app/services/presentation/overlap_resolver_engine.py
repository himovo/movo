from __future__ import annotations

from typing import Callable, List

from app.services.presentation.contracts import FreeformBlock
from app.services.presentation.layout_protocol import SIBLING_OVERLAP_RATIO_THRESHOLD


IntentionalOverlapFn = Callable[[FreeformBlock, FreeformBlock], bool]
BackgroundFn = Callable[[FreeformBlock], bool]
ShiftChildrenFn = Callable[[FreeformBlock, float, float], None]
RectIntersectionFn = Callable[[tuple[float, float, float, float], tuple[float, float, float, float]], float]
ClampRectFn = Callable[..., tuple[float, float, float, float]]


class OverlapResolverEngine:
    """Resolve severe top-level overlaps while preserving intended overlay semantics."""

    def resolve_top_level_overlaps(
        self,
        blocks: List[FreeformBlock],
        *,
        is_text_over_container_intended: IntentionalOverlapFn,
        is_background_block: BackgroundFn,
        shift_children: ShiftChildrenFn,
        rect_intersection_area: RectIntersectionFn,
        clamp_rect_to_container: ClampRectFn,
    ) -> List[FreeformBlock]:
        adjusted = [b.model_copy(deep=True) for b in list(blocks or [])]
        page_rect = (0.0, 0.0, 1.0, 1.0)
        non_line = [
            (i, adjusted[i])
            for i in range(len(adjusted))
            if str(adjusted[i].type or "").strip().lower() != "line"
            and not is_background_block(adjusted[i])
        ]
        for ii, (_, left) in enumerate(non_line):
            left_type = str(left.type or "").strip().lower()
            for jj in range(ii + 1, len(non_line)):
                _, right = non_line[jj]
                right_type = str(right.type or "").strip().lower()
                if is_text_over_container_intended(left, right):
                    continue
                left_area = float(left.w or 0) * float(left.h or 0)
                right_area = float(right.w or 0) * float(right.h or 0)
                if right_type == "text_box" or (left_type != "text_box" and right_area <= left_area):
                    mover, anchor = right, left
                else:
                    mover, anchor = left, right
                attempt = 0
                while attempt < 10:
                    left_rect = (float(left.x or 0), float(left.y or 0), float(left.w or 0), float(left.h or 0))
                    right_rect = (float(right.x or 0), float(right.y or 0), float(right.w or 0), float(right.h or 0))
                    inter = rect_intersection_area(left_rect, right_rect)
                    smaller = min(
                        max(float(left.w or 0) * float(left.h or 0), 0.0001),
                        max(float(right.w or 0) * float(right.h or 0), 0.0001),
                    )
                    if inter <= 0 or inter / smaller < SIBLING_OVERLAP_RATIO_THRESHOLD:
                        break
                    old_x, old_y = float(mover.x or 0), float(mover.y or 0)
                    if mover is left:
                        move_x, move_y = self._separation_delta(anchor_rect=right_rect, mover_rect=left_rect)
                    else:
                        move_x, move_y = self._separation_delta(anchor_rect=left_rect, mover_rect=right_rect)
                    mover.x = old_x + move_x
                    mover.y = old_y + move_y
                    mover.x, mover.y, mover.w, mover.h = clamp_rect_to_container(
                        x=float(mover.x or 0),
                        y=float(mover.y or 0),
                        w=max(float(mover.w or 0), 0.001),
                        h=max(float(mover.h or 0), 0.001),
                        container=page_rect,
                    )
                    delta_x = float(mover.x or 0) - old_x
                    delta_y = float(mover.y or 0) - old_y
                    if delta_x == 0.0 and delta_y == 0.0:
                        if mover is left:
                            alt_x, alt_y = self._separation_delta(
                                anchor_rect=right_rect,
                                mover_rect=left_rect,
                                prefer_secondary_axis=True,
                            )
                        else:
                            alt_x, alt_y = self._separation_delta(
                                anchor_rect=left_rect,
                                mover_rect=right_rect,
                                prefer_secondary_axis=True,
                            )
                        mover.x = old_x + alt_x
                        mover.y = old_y + alt_y
                        mover.x, mover.y, mover.w, mover.h = clamp_rect_to_container(
                            x=float(mover.x or 0),
                            y=float(mover.y or 0),
                            w=max(float(mover.w or 0), 0.001),
                            h=max(float(mover.h or 0), 0.001),
                            container=page_rect,
                        )
                        delta_x = float(mover.x or 0) - old_x
                        delta_y = float(mover.y or 0) - old_y
                        if delta_x == 0.0 and delta_y == 0.0:
                            break
                    if (delta_x != 0 or delta_y != 0) and mover.children:
                        shift_children(mover, delta_x, delta_y)
                    attempt += 1
        return adjusted

    def _separation_delta(
        self,
        *,
        anchor_rect: tuple[float, float, float, float],
        mover_rect: tuple[float, float, float, float],
        prefer_secondary_axis: bool = False,
    ) -> tuple[float, float]:
        ax, ay, aw, ah = anchor_rect
        mx, my, mw, mh = mover_rect
        overlap_w = min(ax + aw, mx + mw) - max(ax, mx)
        overlap_h = min(ay + ah, my + mh) - max(ay, my)
        if overlap_w <= 0.0 or overlap_h <= 0.0:
            return 0.0, 0.0
        margin = 0.014
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
