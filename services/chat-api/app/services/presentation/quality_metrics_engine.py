from __future__ import annotations

from typing import Any, Callable, Dict, List

from app.services.presentation.contracts import FreeformBlock, FreeformDeckBlueprint, FreeformPageBlueprint
from app.services.presentation.layout_protocol import (
    CHILD_OUTSIDE_CONTAINER_RATIO_LIMIT,
    MIN_LINE_LENGTH,
    SEVERE_OVERLAP_AREA_THRESHOLD,
    SIBLING_OVERLAP_RATIO_THRESHOLD,
    TEXT_TEXT_OVERLAP_RATIO_THRESHOLD,
    text_geometry_requirements,
)
from app.services.presentation.layout_utils import (
    flatten_blocks as flatten_blocks_util,
    rect_intersection_area as rect_intersection_area_util,
)


IntentionalOverlapFn = Callable[[FreeformBlock, FreeformBlock], bool]


class QualityMetricsEngine:
    def evaluate_deck_quality(
        self,
        deck: FreeformDeckBlueprint,
        *,
        is_text_over_container_intended: IntentionalOverlapFn,
    ) -> Dict[str, Any]:
        page_metrics = [
            self.page_quality_metrics(page, is_text_over_container_intended=is_text_over_container_intended)
            for page in list(deck.pages or [])
        ]
        total_text = sum(int(m["text_count"]) for m in page_metrics)
        readable_text = sum(int(m["readable_text_count"]) for m in page_metrics)
        readability_eval_text = sum(int(m["readability_eval_text_count"]) for m in page_metrics)
        readability_eval_readable = sum(int(m["readability_eval_readable_count"]) for m in page_metrics)
        total_children = sum(int(m["group_child_count"]) for m in page_metrics)
        outside_children = sum(int(m["children_outside_count"]) for m in page_metrics)

        metrics: Dict[str, Any] = {
            "page_count": len(page_metrics),
            "out_of_bounds_count": sum(int(m["out_of_bounds_count"]) for m in page_metrics),
            "point_line_count": sum(int(m["point_line_count"]) for m in page_metrics),
            "line_missing_endpoint_count": sum(int(m["line_missing_endpoint_count"]) for m in page_metrics),
            "overlapping_siblings_count": sum(int(m["overlapping_siblings_count"]) for m in page_metrics),
            "severe_overlapping_siblings_count": sum(int(m["severe_overlapping_siblings_count"]) for m in page_metrics),
            "children_outside_container_count": outside_children,
            "children_outside_container_ratio": (outside_children / max(total_children, 1)),
            "text_count": total_text,
            "readable_text_count": readable_text,
            "text_readability_rate": (readable_text / max(total_text, 1)),
            "readability_eval_text_count": readability_eval_text,
            "readability_eval_readable_count": readability_eval_readable,
            "readability_eval_rate": (readability_eval_readable / max(readability_eval_text, 1)),
            "readability_eval_severe_narrow_count": sum(int(m["readability_eval_severe_narrow_count"]) for m in page_metrics),
            "pages": page_metrics,
        }
        hard_issues: List[str] = []
        if int(metrics["out_of_bounds_count"]) > 0:
            hard_issues.append("out_of_bounds_geometry")
        if int(metrics["point_line_count"]) > 0:
            hard_issues.append("degenerate_lines")
        if int(metrics["line_missing_endpoint_count"]) > 0:
            hard_issues.append("line_missing_endpoints")

        max_severe_per_page = max(
            (int(m["severe_overlapping_siblings_count"]) for m in page_metrics),
            default=0,
        )
        if max_severe_per_page >= 3:
            hard_issues.append("overlapping_siblings")
        if float(metrics["children_outside_container_ratio"]) > CHILD_OUTSIDE_CONTAINER_RATIO_LIMIT:
            hard_issues.append("children_outside_container")
        max_severe_narrow_per_page = max(
            (int(m["readability_eval_severe_narrow_count"]) for m in page_metrics),
            default=0,
        )
        if max_severe_narrow_per_page >= 4:
            hard_issues.append("text_box_too_narrow")
        metrics["hard_issues"] = hard_issues
        metrics["passed"] = len(hard_issues) == 0
        return metrics

    def page_quality_metrics(
        self,
        page: FreeformPageBlueprint,
        *,
        is_text_over_container_intended: IntentionalOverlapFn,
    ) -> Dict[str, Any]:
        flat = self.flatten_blocks(list(page.blocks or []))
        out_of_bounds_count = 0
        point_line_count = 0
        line_missing_endpoint_count = 0
        text_count = 0
        readable_text_count = 0
        readability_eval_text_count = 0
        readability_eval_readable_count = 0
        readability_eval_severe_narrow_count = 0
        for block in flat:
            x = float(block.x or 0.0)
            y = float(block.y or 0.0)
            w = max(float(block.w or 0.0), 0.0)
            h = max(float(block.h or 0.0), 0.0)
            eps = 1e-4
            if not (-eps <= x <= 1.0 + eps and -eps <= y <= 1.0 + eps and 0.0 <= w <= 1.0 + eps and 0.0 <= h <= 1.0 + eps and x + w <= 1.0 + eps and y + h <= 1.0 + eps):
                out_of_bounds_count += 1
            block_type = str(block.type or "").strip().lower()
            if block_type == "line":
                if block.x2 is None or block.y2 is None:
                    line_missing_endpoint_count += 1
                else:
                    dx = abs(float(block.x2) - float(block.x or 0.0))
                    dy = abs(float(block.y2) - float(block.y or 0.0))
                    if max(dx, dy) < MIN_LINE_LENGTH:
                        point_line_count += 1
            if block_type == "text_box" and str(block.content or "").strip():
                text_count += 1
                style = dict(block.style or {})
                try:
                    font_size = float(style.get("font_size")) if style.get("font_size") not in (None, "") else None
                except Exception:
                    font_size = None
                min_w, min_h = text_geometry_requirements(str(block.content or ""), font_size=font_size)
                is_readable = bool(w >= min_w and h >= min_h)
                if is_readable:
                    readable_text_count += 1
                if self.needs_strict_text_readability(block):
                    readability_eval_text_count += 1
                    if is_readable:
                        readability_eval_readable_count += 1
                    if self.is_severe_narrow_text(block, min_w=min_w, min_h=min_h, w=w, h=h):
                        readability_eval_severe_narrow_count += 1

        outside_count, child_count = self.count_children_outside(list(page.blocks or []))
        overlapping_siblings_count, severe_overlapping_siblings_count = self.count_overlapping_siblings(
            list(page.blocks or []),
            is_text_over_container_intended=is_text_over_container_intended,
        )
        return {
            "page_id": str(page.page_id or "").strip(),
            "out_of_bounds_count": out_of_bounds_count,
            "point_line_count": point_line_count,
            "line_missing_endpoint_count": line_missing_endpoint_count,
            "overlapping_siblings_count": overlapping_siblings_count,
            "severe_overlapping_siblings_count": severe_overlapping_siblings_count,
            "children_outside_count": outside_count,
            "group_child_count": child_count,
            "text_count": text_count,
            "readable_text_count": readable_text_count,
            "readability_eval_text_count": readability_eval_text_count,
            "readability_eval_readable_count": readability_eval_readable_count,
            "readability_eval_severe_narrow_count": readability_eval_severe_narrow_count,
        }

    @staticmethod
    def needs_strict_text_readability(block: FreeformBlock) -> bool:
        if str(block.type or "").strip().lower() != "text_box":
            return False
        text = str(block.content or "").replace("<br/>", "\n").strip()
        if not text:
            return False
        role = str(block.role or "").strip().lower()
        if role in {"label", "caption", "badge", "tag"} and len(text) <= 18 and "\n" not in text:
            return False
        if len(text) <= 10 and "\n" not in text:
            return False
        return True

    def is_severe_narrow_text(
        self,
        block: FreeformBlock,
        *,
        min_w: float,
        min_h: float,
        w: float,
        h: float,
    ) -> bool:
        if not self.needs_strict_text_readability(block):
            return False
        return bool(w < (min_w * 0.78) or h < (min_h * 0.78))

    def count_children_outside(self, blocks: List[FreeformBlock]) -> tuple[int, int]:
        outside = 0
        checked = 0

        def walk_group(group: FreeformBlock) -> None:
            nonlocal outside, checked
            gx, gy, gw, gh = float(group.x or 0.0), float(group.y or 0.0), float(group.w or 0.0), float(group.h or 0.0)
            for child in list(group.children or []):
                if str(child.type or "").strip().lower() == "line":
                    continue
                checked += 1
                cx, cy, cw, ch = float(child.x or 0.0), float(child.y or 0.0), float(child.w or 0.0), float(child.h or 0.0)
                if cx < gx - 0.01 or cy < gy - 0.01 or cx + cw > gx + gw + 0.01 or cy + ch > gy + gh + 0.01:
                    outside += 1
                if str(child.type or "").strip().lower() == "group":
                    walk_group(child)

        for block in list(blocks or []):
            if str(block.type or "").strip().lower() == "group":
                walk_group(block)
        return outside, checked

    def count_overlapping_siblings(
        self,
        blocks: List[FreeformBlock],
        *,
        is_text_over_container_intended: IntentionalOverlapFn,
    ) -> tuple[int, int]:
        count, severe = self.count_layer_overlap(
            blocks,
            is_text_over_container_intended=is_text_over_container_intended,
        )
        for block in list(blocks or []):
            if str(block.type or "").strip().lower() == "group":
                sub_count, sub_severe = self.count_overlapping_siblings(
                    list(block.children or []),
                    is_text_over_container_intended=is_text_over_container_intended,
                )
                count += sub_count
                severe += sub_severe
        return count, severe

    def count_layer_overlap(
        self,
        siblings: List[FreeformBlock],
        *,
        is_text_over_container_intended: IntentionalOverlapFn,
    ) -> tuple[int, int]:
        overlap = 0
        severe = 0
        items = [s for s in list(siblings or []) if str(s.type or "").strip().lower() != "line"]
        for index, left in enumerate(items):
            left_rect = (float(left.x or 0.0), float(left.y or 0.0), float(left.w or 0.0), float(left.h or 0.0))
            for right in items[index + 1 :]:
                if is_text_over_container_intended(left, right):
                    continue
                left_type = str(left.type or "").strip().lower()
                right_type = str(right.type or "").strip().lower()
                if left_type != "text_box" and right_type != "text_box":
                    continue
                right_rect = (float(right.x or 0.0), float(right.y or 0.0), float(right.w or 0.0), float(right.h or 0.0))
                inter = self.rect_intersection_area(left_rect, right_rect)
                if inter <= 0.0:
                    continue
                left_area = max(left_rect[2] * left_rect[3], 0.0001)
                right_area = max(right_rect[2] * right_rect[3], 0.0001)
                ratio = inter / min(left_area, right_area)
                if ratio >= SIBLING_OVERLAP_RATIO_THRESHOLD:
                    overlap += 1
                if (
                    (left_type == "text_box" and right_type == "text_box" and ratio >= TEXT_TEXT_OVERLAP_RATIO_THRESHOLD)
                    or (ratio >= TEXT_TEXT_OVERLAP_RATIO_THRESHOLD and inter >= SEVERE_OVERLAP_AREA_THRESHOLD)
                ):
                    severe += 1
        return overlap, severe

    @staticmethod
    def flatten_blocks(blocks: List[FreeformBlock]) -> List[FreeformBlock]:
        return flatten_blocks_util(list(blocks or []))

    @staticmethod
    def rect_intersection_area(
        left: tuple[float, float, float, float],
        right: tuple[float, float, float, float],
    ) -> float:
        return rect_intersection_area_util(left, right)
