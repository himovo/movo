from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from app.services.presentation.contracts import (
    DesignTokens,
    FreeformBlock,
    FreeformDeckBlueprint,
    FreeformPageBlueprint,
)
from app.services.presentation.icon_library import (
    load_inline_svg_map,
    resolve_icon_from_texts,
)
from app.services.presentation.layout_protocol import (
    MIN_LINE_LENGTH,
    normalize_line_route,
)
from app.services.presentation.content_reflow import ContentDrivenReflowEngine
from app.services.presentation.geometry_constraints_engine import GeometryConstraintsEngine
from app.services.presentation.overlap_resolver_engine import OverlapResolverEngine
from app.services.presentation.style_normalizer_engine import StyleNormalizerEngine
from app.services.presentation.quality_metrics_engine import QualityMetricsEngine
from app.services.presentation.layout_utils import (
    children_bbox as calc_children_bbox,
    flatten_blocks as flatten_blocks_util,
    is_text_over_container_intended as text_over_container_intended_util,
    rect_intersection_area as rect_intersection_area_util,
    render_order_key as render_order_key_util,
)

logger = logging.getLogger(__name__)


def _clamp01(value: Any, default: float) -> float:
    try:
        result = float(value)
    except Exception:
        result = default
    return max(0.0, min(1.0, result))


class RenderableAstNormalizer:
    _DEFAULT_CONTAINER_PAD = 0.012
    _MAX_ABSOLUTE_DEPTH = 4

    def __init__(self) -> None:
        self._reflow_engine = ContentDrivenReflowEngine()
        self._geometry_engine = GeometryConstraintsEngine()
        self._overlap_engine = OverlapResolverEngine()
        self._style_engine = StyleNormalizerEngine()
        self._quality_engine = QualityMetricsEngine()

    def infer_child_coordinate_space(self, blueprint: FreeformDeckBlueprint) -> FreeformDeckBlueprint:
        """Heuristic fix for the LLM's most common geometry mistake.

        The LLM is told (via prompt) that group children should declare
        ``coordinate_space=parent`` so their (x, y, w, h) is interpreted
        relative to the parent group. In practice it forgets the field but
        still emits parent-relative numbers like ``(0.08, 0.18, 0.18, 0.40)``,
        which the default ``coordinate_space=page`` would render as
        page-absolute coordinates — i.e., a giant icon at the top-left of
        the slide instead of a small icon inside its parent card.

        For each ``type=group`` block on the page, this pass evaluates the
        children twice: once interpreted as page-absolute, once as
        parent-relative. It uses the same scoring function the engineering-
        geometry pipeline already trusted (containment fit + minimal
        overlap + readable text dims). If the parent-relative reading is
        materially better AND the page reading is genuinely bad, every
        child of that group is **flipped to ``coordinate_space=parent``**.

        Why we flip the metadata flag instead of rewriting coordinates:
        ``html_renderer._render_shape`` already knows how to translate
        parent-relative children. Flipping the flag is a one-bit change
        per child; the actual x/y numbers are untouched. If we ever need
        to roll back, removing the flip yields byte-identical output.

        Safety guards:
          - Only walks ``type=group`` blocks. Top-level cards never get
            touched (top level is page-space by definition). Non-group
            container types (rectangle, image) are left alone too.
          - Skips groups whose children already declare ``parent``
            consistently — they were correct as authored.
          - Never modifies a child whose ``coordinate_space`` is already
            ``parent`` (it's already correct).
          - Never modifies a child if the parent's group rect is bogus
            (zero area or fills the entire page — those are root-level
            decorations, not real containers).
          - Logs each flipped group with the score margin so the change
            is auditable from backend.log alone.

        Idempotent: running the pass twice has the same effect as running
        it once, because flipped children are already ``parent`` on the
        second pass and skip the heuristic.
        """
        prepared = blueprint.model_copy(deep=True)
        flipped_log: List[Dict[str, Any]] = []
        for page in list(prepared.pages or []):
            page_id = str(page.page_id or "").strip()
            for top_block in list(page.blocks or []):
                self._walk_groups_for_coordinate_inference(
                    top_block, page_id=page_id, flipped_log=flipped_log,
                )
        if flipped_log:
            logger.warning(
                "presentation_child_coord_space_inferred deck_id=%s flips=%s details=%s",
                str(prepared.deck_id or "").strip(),
                len(flipped_log),
                flipped_log[:20],
            )
        else:
            logger.warning(
                "presentation_child_coord_space_inferred deck_id=%s flips=0 (clean)",
                str(prepared.deck_id or "").strip(),
            )
        return prepared

    def _walk_groups_for_coordinate_inference(
        self,
        block: FreeformBlock,
        *,
        page_id: str,
        flipped_log: List[Dict[str, Any]],
    ) -> None:
        """Recurse into a block tree, applying the inference rule to each group."""
        block_type = str(block.type or "").strip().lower()
        if block_type == "group" and list(block.children or []):
            self._maybe_flip_group_children_to_parent(
                block, page_id=page_id, flipped_log=flipped_log,
            )
        for child in list(block.children or []):
            self._walk_groups_for_coordinate_inference(
                child, page_id=page_id, flipped_log=flipped_log,
            )

    def _maybe_flip_group_children_to_parent(
        self,
        group: FreeformBlock,
        *,
        page_id: str,
        flipped_log: List[Dict[str, Any]],
    ) -> None:
        gx = float(group.x or 0.0)
        gy = float(group.y or 0.0)
        gw = float(group.w or 0.0)
        gh = float(group.h or 0.0)
        # Bogus group rect — skip rather than risk a bad heuristic call.
        if gw <= 0.001 or gh <= 0.001:
            return
        # Full-page or near-full-page "groups" are decorative containers
        # whose children are typically intended as page-absolute. Skip.
        if gw >= 0.95 and gh >= 0.95 and gx <= 0.05 and gy <= 0.05:
            return
        children = list(group.children or [])
        if not children:
            return
        # Children that are already explicitly parent-relative tell us the
        # group is already correct as authored — don't second-guess.
        page_children = [
            c for c in children
            if str(c.coordinate_space or "").strip().lower() != "parent"
        ]
        if not page_children:
            return
        # Run the existing scoring on the WHOLE child set in both modes;
        # the score function knows how to mix parent and page children.
        group_rect = (gx, gy, gw, gh)
        page_score = self._score_group_children_layout(
            children=children, group_rect=group_rect, reinterpret_page_children=False,
        )
        parent_score = self._score_group_children_layout(
            children=children, group_rect=group_rect, reinterpret_page_children=True,
        )
        # Require a clear win (the existing engineering pipeline used the
        # same +0.12 margin in _choose_group_subtree_coordinate_mode).
        if parent_score < page_score + 0.12:
            return
        # Additional safety: page-mode score has to be genuinely bad. If the
        # current page-mode interpretation is already decent (>= 0.65), the
        # group is probably fine and we should not touch it.
        if page_score >= 0.78:
            return
        for child in page_children:
            child.coordinate_space = "parent"
        flipped_log.append({
            "page_id": page_id,
            "group_id": str(group.id or "").strip(),
            "child_count": len(page_children),
            "page_score": round(page_score, 3),
            "parent_score": round(parent_score, 3),
        })

    def prepare_for_render(self, blueprint: FreeformDeckBlueprint) -> FreeformDeckBlueprint:
        """Minimal, coordinate-neutral metadata prep for raw-render mode.

        Runs ONLY two non-destructive passes:
        - ``_infer_roles`` fills missing ``role`` fields on blocks so the
          downstream verifier's background whitelist and the renderer's
          role-sensitive styling can actually see what's a background, a
          card, a connector, etc.
        - ``_infer_container_links`` fills missing ``container_id`` on
          unlinked text_box blocks so ``is_text_over_container_intended``
          correctly treats text-in-card as intentional layering instead of
          flagging it as a defect.

        This method intentionally does NOT run reflow, overlap resolution,
        geometry constraints, cleanup, or any other stage from
        ``normalize_page``. It is safe to call on raw LLM output because it
        only writes fields that were empty; it never changes x/y/w/h/content/
        style, never adds or removes a block, never re-sorts children.
        """
        prepared = blueprint.model_copy(deep=True)
        pages: List[FreeformPageBlueprint] = []
        for page in list(prepared.pages or []):
            page_out = page.model_copy(deep=True)
            blocks = list(page_out.blocks or [])
            blocks = self._infer_roles(blocks)
            blocks = self._infer_container_links(blocks)
            page_out.blocks = blocks
            pages.append(page_out)
        prepared.pages = pages
        return prepared

    def normalize_deck(
        self,
        blueprint: FreeformDeckBlueprint,
        *,
        preserve_geometry_page_ids: set[str] | None = None,
    ) -> FreeformDeckBlueprint:
        deck = blueprint.model_copy(deep=True)
        protected = {str(pid).strip() for pid in (preserve_geometry_page_ids or set()) if str(pid).strip()}
        pages: List[FreeformPageBlueprint] = []
        for page in list(deck.pages or []):
            page_id = str(page.page_id or "").strip()
            preserve = page_id in protected if protected else False
            pages.append(self.normalize_page(page, deck, preserve_geometry=preserve))
        deck.pages = pages
        return deck

    def normalize_page(
        self,
        page: FreeformPageBlueprint,
        deck: FreeformDeckBlueprint,
        *,
        preserve_geometry: bool = False,
    ) -> FreeformPageBlueprint:
        tokens = DesignTokens()
        runtime = dict(deck.runtime or {})
        brief_payload = runtime.get("deck_brief") if isinstance(runtime.get("deck_brief"), dict) else {}
        if isinstance(brief_payload.get("design_tokens"), dict):
            try:
                tokens = DesignTokens.model_validate(brief_payload.get("design_tokens"))
            except Exception:
                tokens = DesignTokens()

        normalized = page.model_copy(deep=True)
        normalized.style = self._normalize_style(dict(page.style or {}), shape_type="page", tokens=tokens)
        blocks: List[FreeformBlock] = []
        for block in list(page.blocks or []):
            block_out = self.normalize_block(block, tokens=tokens)
            if block_out is not None:
                blocks.append(block_out)
        blocks = self._infer_roles(blocks)
        blocks = self._infer_container_links(blocks)
        blocks = self._resolve_text_geometry(blocks, tokens=tokens)
        blocks = self._resolve_page_skeleton(page, blocks)
        blocks = self._absolutize_group_children(blocks)
        blocks = self._resolve_group_geometry(blocks)
        blocks = self._align_text_to_containers(blocks)
        blocks = self._resolve_linked_container_geometry(blocks)
        blocks = self._absolutize_group_children(blocks)
        if preserve_geometry:
            # Repaired pages: keep LLM coordinates intact. Skip reflow and overlap
            # resolution because they would undo the targeted geometry fix the
            # repair LLM just produced. A single boundary-clamp pass keeps the
            # output legal without redistributing block positions.
            logger.info(
                "presentation_normalize stage=preserve_geometry page_id=%s block_count=%s skipped=reflow,overlap_resolver",
                str(page.page_id or "").strip(),
                len(blocks),
            )
            blocks = self._apply_geometry_constraints(blocks)
        else:
            blocks = self._reflow_engine.reflow_page(blocks, page_rect=(0.0, 0.0, 1.0, 1.0))
            blocks = self._apply_geometry_constraints(blocks)
            blocks = self._resolve_top_level_overlaps(blocks)
            # One more deterministic reflow+constraint pass after overlap nudging
            # to avoid engines undoing each other on crowded pages.
            blocks = self._reflow_engine.reflow_page(blocks, page_rect=(0.0, 0.0, 1.0, 1.0))
            blocks = self._apply_geometry_constraints(blocks)
        blocks = self._final_constrain_children(blocks)
        blocks = self._cleanup_invalid_blocks(blocks)
        blocks = self._cleanup_orphan_decorations(blocks)
        blocks = self._sort_blocks_for_rendering(blocks)
        normalized.blocks = blocks
        return normalized

    def normalize_block(self, block: FreeformBlock, *, tokens: DesignTokens) -> FreeformBlock | None:
        shape_type = str(block.type or "text_box").strip().lower() or "text_box"
        normalized = block.model_copy(deep=True)
        normalized.type = shape_type
        normalized.role = str(block.role or "").strip().lower()
        normalized.container_id = str(block.container_id or "").strip()
        normalized.coordinate_space = "parent" if str(block.coordinate_space or "").strip().lower() == "parent" else "page"
        normalized.x = _clamp01(block.x, 0.0)
        normalized.y = _clamp01(block.y, 0.0)
        normalized.w = max(0.0, _clamp01(block.w, 0.0))
        normalized.h = max(0.0, _clamp01(block.h, 0.0))
        normalized.x2 = _clamp01(block.x2, normalized.x + normalized.w) if block.x2 is not None else None
        normalized.y2 = _clamp01(block.y2, normalized.y + normalized.h) if block.y2 is not None else None
        normalized.max_w = _clamp01(block.max_w, normalized.w) if block.max_w is not None else None
        normalized.max_h = _clamp01(block.max_h, normalized.h) if block.max_h is not None else None
        normalized.min_w = _clamp01(block.min_w, normalized.w) if block.min_w is not None else None
        normalized.min_h = _clamp01(block.min_h, normalized.h) if block.min_h is not None else None
        if normalized.min_w is not None and normalized.max_w is not None and normalized.min_w > normalized.max_w:
            normalized.min_w, normalized.max_w = normalized.max_w, normalized.min_w
        if normalized.min_h is not None and normalized.max_h is not None and normalized.min_h > normalized.max_h:
            normalized.min_h, normalized.max_h = normalized.max_h, normalized.min_h
        normalized.padding = _clamp01(block.padding, self._DEFAULT_CONTAINER_PAD) if block.padding is not None else None
        normalized.style = self._normalize_style(dict(block.style or {}), shape_type=shape_type, tokens=tokens)

        children: List[FreeformBlock] = []
        for child in list(block.children or []):
            child_out = self.normalize_block(child, tokens=tokens)
            if child_out is not None:
                children.append(child_out)
        normalized.children = children

        if shape_type == "group":
            if not normalized.children and not self._has_visual_style(normalized.style):
                return None
            return normalized

        if shape_type == "line":
            return self._normalize_line_block(normalized, tokens=tokens)

        if shape_type == "text_box":
            normalized.style = self._normalize_text_style(
                normalized.style, tokens=tokens, text=normalized.content, role=normalized.role
            )
            normalized.style = self._resolve_text_contrast(normalized.style)
            if not str(normalized.content or "").strip() and not normalized.children:
                return None
            return normalized

        if shape_type == "icon":
            return self._normalize_icon_block(normalized, tokens=tokens)

        if shape_type in {"rectangle", "circle", "image"}:
            if shape_type == "image" and not str(normalized.content or "").strip():
                return None
            return normalized
        if shape_type == "chart":
            return normalized

        logger.warning("presentation_unknown_block_type type=%s id=%s", shape_type, str(block.id or "").strip())
        normalized.type = "text_box"
        normalized.style = self._normalize_text_style(
            normalized.style, tokens=tokens, text=normalized.content, role=normalized.role
        )
        normalized.style = self._resolve_text_contrast(normalized.style)
        return normalized if str(normalized.content or "").strip() or normalized.children else None

    def _infer_roles(self, blocks: List[FreeformBlock]) -> List[FreeformBlock]:
        inferred: List[FreeformBlock] = []
        for block in list(blocks or []):
            out = block.model_copy(deep=True)
            if out.children:
                out.children = self._infer_roles(list(out.children or []))
            if not str(out.role or "").strip():
                out.role = self._infer_role_from_block(out)
            inferred.append(out)
        return inferred

    def _infer_role_from_block(self, block: FreeformBlock) -> str:
        block_type = str(block.type or "").strip().lower()
        block_id = str(block.id or "").strip().lower()
        text = str(block.content or "").strip()
        if block_type == "line":
            if "axis" in block_id:
                return "axis"
            if "divider" in block_id:
                return "divider"
            return "connector"
        if block_type == "group":
            return "group"
        if block_type in {"rectangle", "circle", "image", "chart"}:
            for token, role in (
                ("bg", "background"),
                ("background", "background"),
                ("panel", "panel"),
                ("container", "container"),
                ("card", "card"),
                ("band", "band"),
                ("stage", "card"),
                ("row", "card"),
                ("q", "card"),
                ("box", "card"),
            ):
                if token in block_id:
                    return role
            return "shape"
        if block_type == "text_box":
            if "title" in block_id or "headline" in block_id:
                return "title"
            if "subtitle" in block_id or "tagline" in block_id:
                return "subtitle"
            if any(token in block_id for token in ("header", "label", "caption")):
                return "label"
            if len(text) <= 18 and "\n" not in text:
                return "label"
            return "body"
        return ""

    _CONTAINER_TYPES = frozenset({"rectangle", "circle", "image", "chart", "group"})

    def _infer_container_links(self, blocks: List[FreeformBlock]) -> List[FreeformBlock]:
        """Infer container_id for unlinked text_box blocks at every tree level.

        Three strategies tried in order for each unlinked text_box:
        1. ID-stem match (suffix/prefix stripping)
        2. Geometric overlap ≥60% of text area
        3. Proximity: nearest shape sibling at similar x-range (for text
           placed below its intended container)

        Runs per-level so group children match against sibling shapes,
        not against unrelated blocks in other groups.
        """
        # Global stem map (flat across all levels for stem matching)
        all_blocks = self._flatten_blocks(blocks)
        containers_by_stem: Dict[str, List[str]] = {}
        for block in all_blocks:
            if str(block.type or "").strip().lower() not in self._CONTAINER_TYPES:
                continue
            stem = self._shape_stem(str(block.id or ""))
            if stem:
                containers_by_stem.setdefault(stem, []).append(str(block.id or ""))

        return self._infer_links_at_level(blocks, containers_by_stem)

    def _infer_links_at_level(
        self,
        siblings: List[FreeformBlock],
        containers_by_stem: Dict[str, List[str]],
    ) -> List[FreeformBlock]:
        """Infer container_id among a list of sibling blocks (one tree level)."""
        # Local container candidates for geometric + proximity matching at this level
        local_containers = [
            b for b in siblings
            if str(b.type or "").strip().lower() in self._CONTAINER_TYPES
            and float(b.w or 0) > 0 and float(b.h or 0) > 0
        ]

        # When there are multiple containers at this level, geometric inference
        # is risky — a section title can overlap the first card by accident.
        # Only use geometric inference when there's exactly 1 container sibling.
        multi_container = len(local_containers) > 1

        def _best_container(text_block: FreeformBlock) -> str | None:
            tx, ty = float(text_block.x or 0), float(text_block.y or 0)
            tw, th = float(text_block.w or 0), float(text_block.h or 0)
            text_area = max(tw * th, 0.0001)
            text_cx = tx + tw / 2

            best_geo_id: str | None = None
            best_geo_area = float("inf")
            best_prox_id: str | None = None
            best_prox_dist = float("inf")

            for cand in local_containers:
                cid = str(cand.id or "").strip()
                if not cid or cid == str(text_block.id or "").strip():
                    continue
                cx, cy = float(cand.x or 0), float(cand.y or 0)
                cw, ch = float(cand.w or 0), float(cand.h or 0)
                cand_area = cw * ch
                cand_cx = cx + cw / 2

                # ── Strategy 2: geometric overlap ≥60% ──────────────
                # Skip when multiple containers exist — too easy to mis-bind
                # a section title to the first card it overlaps.
                if not multi_container:
                    inter_w = min(tx + tw, cx + cw) - max(tx, cx)
                    inter_h = min(ty + th, cy + ch) - max(ty, cy)
                    if inter_w > 0 and inter_h > 0:
                        covered = (inter_w * inter_h) / text_area
                        if covered >= 0.60 and cand_area < best_geo_area:
                            best_geo_id = cid
                            best_geo_area = cand_area

                # ── Strategy 3: proximity (same x-range, nearest y) ─
                # Check horizontal overlap: text and container share ≥50% x range
                x_overlap = min(tx + tw, cx + cw) - max(tx, cx)
                x_overlap_ratio = x_overlap / max(min(tw, cw), 0.001)
                if x_overlap_ratio >= 0.50 or abs(text_cx - cand_cx) < max(tw, cw) * 0.4:
                    # y-distance between text and container
                    if ty >= cy + ch:
                        y_dist = ty - (cy + ch)  # text below container
                    elif cy >= ty + th:
                        y_dist = cy - (ty + th)  # text above container
                    else:
                        y_dist = 0.0  # overlapping
                    if y_dist < best_prox_dist and y_dist < 0.06:
                        best_prox_dist = y_dist
                        best_prox_id = cid

            if best_geo_id:
                return best_geo_id
            return best_prox_id

        result: List[FreeformBlock] = []
        for block in list(siblings or []):
            out = block.model_copy(deep=True)
            # Recurse into group children first (process each level independently)
            if out.children:
                out.children = self._infer_links_at_level(
                    list(out.children or []), containers_by_stem
                )
            if str(out.type or "").strip().lower() == "text_box" and not str(out.container_id or "").strip():
                # Strategy 1: stem match (global)
                stem = self._shape_stem(str(out.id or ""))
                stem_matches = list(containers_by_stem.get(stem) or [])
                if stem and len(stem_matches) == 1 and stem_matches[0] != str(out.id or ""):
                    out.container_id = stem_matches[0]
                else:
                    # Strategy 2+3: geometric / proximity (local siblings)
                    matched = _best_container(out)
                    if matched:
                        out.container_id = matched
            result.append(out)
        return result

    def _shape_stem(self, block_id: str) -> str:
        """Extract a semantic stem from a block ID for container matching.

        Handles both suffix patterns (card_title → card) and
        prefix patterns (text_application → application).
        """
        stem = str(block_id or "").strip().lower()
        if not stem:
            return ""
        # Strip suffix: card_title → card, panel_desc → panel
        stem = re.sub(r"_(title|subtitle|text|body|label|header|content|main|headline|detail|desc|description|info|summary|caption|note)$", "", stem)
        # Strip prefix: text_overview → overview, band_model → model
        stem = re.sub(r"^(text|body|label|title|subtitle|header|content|band|bar|bg|icon|arrow|line|desc|description|txt|lbl|info|rect|shape|box|panel|card|block|heading|headline|detail|note|caption)_", "", stem)
        return stem

    def _normalize_line_block(self, block: FreeformBlock, *, tokens: DesignTokens) -> FreeformBlock | None:
        x1 = _clamp01(block.x, 0.0)
        y1 = _clamp01(block.y, 0.0)
        x2 = block.x2
        y2 = block.y2
        if x2 is None:
            x2 = self._as_number(block.style.get("end_x"))
        if x2 is None:
            x2 = self._as_number(block.style.get("to_x"))
        if y2 is None:
            y2 = self._as_number(block.style.get("end_y"))
        if y2 is None:
            y2 = self._as_number(block.style.get("to_y"))
        # Line endpoint is semantic and must be explicit (or style-endpoint based), never inferred from width/height.
        if x2 is None or y2 is None:
            return None
        x2 = _clamp01(x2, x1)
        y2 = _clamp01(y2, y1)
        route = normalize_line_route(str(block.style.get("route") or block.style.get("router") or block.style.get("path") or "auto"))
        if route == "h":
            y2 = y1
        elif route == "v":
            x2 = x1
        else:
            route = "auto"
            if abs(x2 - x1) >= abs(y2 - y1):
                y2 = y1
            else:
                x2 = x1
        if abs(x2 - x1) < MIN_LINE_LENGTH and abs(y2 - y1) < MIN_LINE_LENGTH:
            # Drop point-like pseudo lines; they create visible artifacts and carry no connector semantics.
            return None
        block.x = min(x1, x2)
        block.y = min(y1, y2)
        block.w = max(abs(x2 - x1), 0.001)
        block.h = max(abs(y2 - y1), 0.001)
        block.x2 = x2
        block.y2 = y2
        block.style["route"] = route
        if "line_weight" not in block.style:
            block.style["line_weight"] = max(2, int(tokens.line_weight or 2))
        if "color" not in block.style and "border_color" in block.style:
            block.style["color"] = block.style.get("border_color")
        elif "color" not in block.style:
            block.style["color"] = tokens.primary_color
        return block

    def _normalize_icon_block(self, block: FreeformBlock, *, tokens: DesignTokens) -> FreeformBlock | None:
        """Resolve icon name → inline SVG and set sensible defaults."""
        raw_name = str(block.icon or block.content or "").strip()
        if not raw_name:
            return None
        resolved = resolve_icon_from_texts(raw_name, block.role, block.content, fallback="bulb")
        svg_map = load_inline_svg_map()
        svg_content = str(svg_map.get(resolved) or "").strip()
        block.icon = resolved
        block.icon_svg = svg_content
        # Sensible default size for icons if LLM didn't specify
        if block.w <= 0.0:
            block.w = 0.035
        if block.h <= 0.0:
            block.h = 0.05
        # Default icon color: use style.color or accent color from tokens
        if "color" not in block.style:
            block.style["color"] = tokens.primary_color
        if not block.role:
            block.role = "icon"
        return block

    def _normalize_text_style(self, style: Dict[str, Any], *, tokens: DesignTokens, text: str, role: str = "") -> Dict[str, Any]:  # noqa: ARG002 (text reserved for future use)
        out = dict(style or {})
        if "font_family" not in out:
            out["font_family"] = tokens.font_family

        role_lower = str(role or "").strip().lower()
        text_size = self._as_number(out.get("font_size"))

        # Role-based defaults and readability floors.
        # Hierarchy: title > subtitle > body/label — ensures visual hierarchy.
        if role_lower in {"title", "heading"}:
            default_size = max(int(tokens.title_font_size or 48), 36)
            floor_size = 30
        elif role_lower == "subtitle":
            default_size = max(int(tokens.subtitle_font_size or 28), 28)
            floor_size = 24
        elif role_lower == "label":
            default_size = max(int(tokens.body_font_size or 22), 22)
            floor_size = 18
        else:
            # body or unknown — default to body size
            default_size = max(int(tokens.body_font_size or 22), 22)
            floor_size = 20

        if text_size is None:
            out["font_size"] = default_size
        else:
            # Respect LLM's creative choice, only enforce readability floor
            out["font_size"] = max(int(text_size), floor_size)

        if "line_height" not in out:
            out["line_height"] = 1.35
        if "color" not in out:
            is_title_role = role_lower in {"title", "heading", "subtitle"}
            out["color"] = tokens.title_color if is_title_role else tokens.body_color
        return out

    # ── Contrast helpers (WCAG 2.0) ────────────────────────────────────────────

    @staticmethod
    def _parse_hex_color(color: str) -> tuple[int, int, int] | None:
        c = str(color or "").strip().lstrip("#")
        if len(c) == 3:
            c = c[0] * 2 + c[1] * 2 + c[2] * 2
        if len(c) == 6:
            try:
                return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
            except ValueError:
                return None
        return None

    @staticmethod
    def _relative_luminance(r: int, g: int, b: int) -> float:
        def lin(v: int) -> float:
            s = v / 255.0
            return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

    def _colors_too_similar(self, color_a: str, color_b: str) -> bool:
        """Return True when WCAG contrast ratio < 3:1 (fails AA-large)."""
        if color_a == color_b:
            return True
        rgb_a = self._parse_hex_color(color_a)
        rgb_b = self._parse_hex_color(color_b)
        if rgb_a is None or rgb_b is None:
            return False
        lum_a = self._relative_luminance(*rgb_a)
        lum_b = self._relative_luminance(*rgb_b)
        lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
        return (lighter + 0.05) / (darker + 0.05) < 3.0

    def _resolve_text_contrast(self, style: Dict[str, Any]) -> Dict[str, Any]:
        """If text color and background are too similar, make background transparent."""
        out = dict(style)
        text_color = str(out.get("color") or "").strip().lower()
        bg_color = str(out.get("background") or "").strip().lower()
        if bg_color and bg_color not in {"", "transparent", "none"}:
            if self._colors_too_similar(text_color, bg_color):
                out["background"] = "transparent"
        return out

    def _resolve_text_geometry(self, blocks: List[FreeformBlock], *, tokens: DesignTokens) -> List[FreeformBlock]:
        resolved: List[FreeformBlock] = []
        for block in list(blocks or []):
            resolved.append(self._resolve_block_geometry(block, tokens=tokens))
        return resolved

    def _resolve_block_geometry(self, block: FreeformBlock, *, tokens: DesignTokens) -> FreeformBlock:
        out = block.model_copy(deep=True)
        if str(out.type or "").strip().lower() == "group":
            out.children = [self._resolve_block_geometry(child, tokens=tokens) for child in list(out.children or [])]
            return out
        if str(out.type or "").strip().lower() != "text_box":
            return out

        text = str(out.content or "").strip()
        if not text:
            return out

        font_size = self._as_number(out.style.get("font_size")) or max(int(tokens.body_font_size or 22), 24)
        width_cap = out.max_w if out.max_w is not None else (out.w if out.w > 0 else None)
        if width_cap is None or width_cap <= 0.0:
            width_cap = 0.36 if len(text.replace("\n", "").replace("<br/>", "")) >= 28 else 0.28
        width_chars = self._estimated_line_capacity(width_cap, font_size)
        line_count = self._estimated_line_count(text, max(width_chars, 1))

        target_w = max(out.w, out.min_w or 0.0)
        target_h = max(out.h, out.min_h or 0.0)
        text_len = len(text.replace("\n", "").replace("<br/>", ""))

        # Distinguish LLM-provided geometry from "LLM gave 0 → we infer"
        fallback_w = target_w <= 0.0
        fallback_h = target_h <= 0.0
        out.geometry_source = (
            "inferred" if (fallback_w and fallback_h)
            else "inferred_w" if fallback_w
            else "inferred_h" if fallback_h
            else "llm"
        )

        if fallback_w:
            target_w = min(width_cap, 0.30 if text_len <= 18 else 0.36)
            if width_chars < 6:
                target_w = max(target_w, 0.22)
            if width_chars < 10 and text_len >= 12:
                target_w = max(target_w, 0.28)
            if width_chars < 14 and text_len >= 28:
                target_w = max(target_w, 0.34)
            if font_size >= 44:
                target_w = max(target_w, 0.30)
            if out.max_w is not None:
                target_w = min(target_w, max(out.max_w, out.min_w or 0.0, 0.12))

        if fallback_h:
            if line_count >= 7:
                target_h = max(target_h, 0.16)
            if line_count >= 10:
                target_h = max(target_h, 0.22)
            if "<br/>" in text or "\n" in text:
                target_h = max(target_h, 0.12)
            target_h = max(target_h, self._estimated_min_height(line_count, font_size))
            if out.max_h is not None:
                target_h = min(target_h, max(out.max_h, out.min_h or 0.0, 0.06))

        if fallback_w or fallback_h:
            target_w = min(target_w, 0.88)
            target_h = min(target_h, 0.50)
            if out.x + target_w > 0.96:
                out.x = max(0.02, 0.96 - target_w)
            if out.y + target_h > 0.96:
                out.y = max(0.02, 0.96 - target_h)

        # ── Protective clamp for LLM-provided values:
        # Respect creative intent; only enforce an absolute readability floor.
        # This is deliberately softer than the heuristic minimums above.
        role = str(getattr(out, "role", "") or "").strip().lower()
        is_title = role in {"title", "heading"} or font_size >= 36
        if not fallback_w and target_w > 0:
            # Hard floor: prevent truly unreadable narrow strips
            if text_len >= 40:
                hard_floor_w = 0.16
            elif text_len >= 20:
                hard_floor_w = 0.12
            else:
                hard_floor_w = 0.08
            if is_title:
                hard_floor_w = max(hard_floor_w, 0.20)
            target_w = max(target_w, hard_floor_w)

        if not fallback_h and target_h > 0:
            # Hard floor: at least one line must be readable
            single_line_min = self._estimated_min_height(1, font_size) * 0.8
            target_h = max(target_h, single_line_min)

        # Re-apply explicit min/max constraints after readability floors.
        if out.max_w is not None:
            target_w = min(target_w, float(out.max_w))
        if out.min_w is not None:
            target_w = max(target_w, float(out.min_w))
        if out.max_h is not None:
            target_h = min(target_h, float(out.max_h))
        if out.min_h is not None:
            target_h = max(target_h, float(out.min_h))
        if out.max_w is not None and out.min_w is not None and out.min_w > out.max_w:
            target_w = float(out.max_w)
        if out.max_h is not None and out.min_h is not None and out.min_h > out.max_h:
            target_h = float(out.max_h)

        # Ensure the block doesn't overflow the page
        target_w = min(target_w, 0.96)
        target_h = min(target_h, 0.96)
        if out.x + target_w > 0.98:
            out.x = max(0.02, 0.98 - target_w)
        if out.y + target_h > 0.98:
            out.y = max(0.02, 0.98 - target_h)

        out.w = max(out.w, target_w)
        out.h = max(out.h, target_h)
        return out

    def _resolve_page_skeleton(self, page: FreeformPageBlueprint, blocks: List[FreeformBlock]) -> List[FreeformBlock]:
        resolved: List[FreeformBlock] = []
        page_id = str(page.page_id or "").strip().lower()
        title_cursor = 0.08
        has_cover = "cover" in page_id
        has_thank = "thank" in page_id
        for block in list(blocks or []):
            out = block.model_copy(deep=True)
            role = str(out.role or "").strip().lower()
            block_type = str(out.type or "").strip().lower()
            if block_type == "text_box" and (out.w <= 0.0 or out.h <= 0.0):
                if role == "title":
                    out.x = 0.08 if has_cover else 0.06
                    out.y = title_cursor
                    out.w = 0.72 if has_cover else 0.88
                    out.h = 0.12 if has_cover else 0.10
                    title_cursor = out.y + out.h + 0.02
                elif role == "subtitle":
                    out.x = 0.08 if has_cover else 0.06
                    out.y = max(title_cursor, 0.18 if has_cover else 0.14)
                    out.w = 0.70 if has_cover else 0.88
                    out.h = 0.08
                    title_cursor = out.y + out.h + 0.02
                elif has_thank and "qa" in str(out.id or "").lower():
                    out.x = 0.24
                    out.y = 0.72
                    out.w = 0.52
                    out.h = 0.10
                elif has_cover:
                    out.w = max(out.w, 0.28)
                    out.h = max(out.h, 0.10)
            if block_type in {"rectangle", "circle", "image", "chart"} and out.w <= 0.0 and out.h <= 0.0:
                if role == "background":
                    out.x = 0.0
                    out.y = 0.0
                    out.w = 1.0
                    out.h = 1.0
                elif has_cover and role in {"panel", "container", "card"}:
                    if "left" in str(out.id or "").lower():
                        out.x, out.y, out.w, out.h = 0.0, 0.0, 0.46, 1.0
                    elif "right" in str(out.id or "").lower():
                        out.x, out.y, out.w, out.h = 0.54, 0.0, 0.46, 1.0
                    else:
                        out.x, out.y, out.w, out.h = 0.08, 0.60, 0.36, 0.22
                elif has_thank and role in {"panel", "container", "card"}:
                    out.x = 0.18 if "anchor" in str(out.id or "").lower() else 0.25
                    out.y = 0.22 if "anchor" in str(out.id or "").lower() else 0.72
                    out.w = 0.50 if "anchor" in str(out.id or "").lower() else 0.40
                    out.h = 0.26 if "anchor" in str(out.id or "").lower() else 0.10
            resolved.append(out)
        return resolved

    def _resolve_group_geometry(self, blocks: List[FreeformBlock]) -> List[FreeformBlock]:
        resolved: List[FreeformBlock] = []
        for block in list(blocks or []):
            resolved.append(self._resolve_group_block(block))
        return resolved

    def _absolutize_group_children(
        self,
        blocks: List[FreeformBlock],
        parent_rect: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
        force_page_children_as_parent: bool = False,
        depth: int = 0,
    ) -> List[FreeformBlock]:
        return [
            self._absolutize_block(
                block,
                parent_rect=parent_rect,
                force_page_children_as_parent=force_page_children_as_parent,
                depth=depth,
            )
            for block in list(blocks or [])
        ]

    def _absolutize_block(
        self,
        block: FreeformBlock,
        *,
        parent_rect: tuple[float, float, float, float],
        force_page_children_as_parent: bool = False,
        depth: int = 0,
    ) -> FreeformBlock:
        out = block.model_copy(deep=True)
        coordinate_space = str(out.coordinate_space or "").strip().lower()
        if depth >= self._MAX_ABSOLUTE_DEPTH and coordinate_space == "parent":
            logger.warning(
                "presentation_group_depth_clamped block_id=%s depth=%s",
                str(out.id or "").strip(),
                depth,
            )
            coordinate_space = "page"
            out.coordinate_space = "page"
        reinterpret = bool(force_page_children_as_parent and coordinate_space == "page")
        if coordinate_space == "parent" or reinterpret or self._should_reinterpret_page_child_as_parent(out, parent_rect=parent_rect):
            out = self._map_parent_space_to_page(out, parent_rect=parent_rect)
        out.coordinate_space = "page"
        if out.children:
            child_parent = (out.x, out.y, out.w, out.h)
            child_force_parent = self._choose_group_subtree_coordinate_mode(
                children=list(out.children or []),
                group_rect=child_parent,
            )
            out.children = [
                self._absolutize_block(
                    child,
                    parent_rect=child_parent,
                    force_page_children_as_parent=child_force_parent,
                    depth=depth + 1,
                )
                for child in list(out.children or [])
            ]
        return out

    def _map_parent_space_to_page(
        self,
        block: FreeformBlock,
        *,
        parent_rect: tuple[float, float, float, float],
    ) -> FreeformBlock:
        out = block.model_copy(deep=True)
        parent_x, parent_y, parent_w, parent_h = parent_rect
        safe_parent_w = max(parent_w, 0.001)
        safe_parent_h = max(parent_h, 0.001)
        out.x = parent_x + safe_parent_w * _clamp01(out.x, 0.0)
        out.y = parent_y + safe_parent_h * _clamp01(out.y, 0.0)
        out.w = safe_parent_w * _clamp01(out.w, 0.0)
        out.h = safe_parent_h * _clamp01(out.h, 0.0)
        if out.x2 is not None:
            out.x2 = parent_x + safe_parent_w * _clamp01(out.x2, 0.0)
        if out.y2 is not None:
            out.y2 = parent_y + safe_parent_h * _clamp01(out.y2, 0.0)
        return out

    def _should_reinterpret_page_child_as_parent(
        self,
        block: FreeformBlock,
        *,
        parent_rect: tuple[float, float, float, float],
    ) -> bool:
        if str(block.coordinate_space or "").strip().lower() != "page":
            return False
        parent_x, parent_y, parent_w, parent_h = parent_rect
        # Root-level blocks are already page-space by definition.
        if parent_w >= 0.999 and parent_h >= 0.999 and parent_x <= 0.001 and parent_y <= 0.001:
            return False
        if parent_w <= 0.0 or parent_h <= 0.0:
            return False

        page_rect = self._candidate_rect(block, parent_rect=parent_rect, assume_parent=False)
        rel_rect = self._candidate_rect(block, parent_rect=parent_rect, assume_parent=True)
        page_fit = self._containment_ratio(page_rect, parent_rect)
        rel_fit = self._containment_ratio(rel_rect, parent_rect)

        # Reinterpret only when the parent-relative interpretation is clearly better.
        if rel_fit < 0.82:
            return False
        if rel_fit <= page_fit + 0.25:
            return False
        return page_fit <= 0.60

    def _choose_group_subtree_coordinate_mode(
        self,
        *,
        children: List[FreeformBlock],
        group_rect: tuple[float, float, float, float],
    ) -> bool:
        if not children:
            return False
        has_page_children = any(str(child.coordinate_space or "").strip().lower() == "page" for child in list(children or []))
        if not has_page_children:
            return False
        page_score = self._score_group_children_layout(children=children, group_rect=group_rect, reinterpret_page_children=False)
        parent_score = self._score_group_children_layout(children=children, group_rect=group_rect, reinterpret_page_children=True)
        # Use parent interpretation only if it is materially better.
        return parent_score >= page_score + 0.12

    def _score_group_children_layout(
        self,
        *,
        children: List[FreeformBlock],
        group_rect: tuple[float, float, float, float],
        reinterpret_page_children: bool,
    ) -> float:
        candidate_rects: List[tuple[FreeformBlock, tuple[float, float, float, float]]] = []
        overflow = 0.0
        readability_penalty = 0.0
        for child in list(children or []):
            rect = self._candidate_rect(
                child,
                parent_rect=group_rect,
                assume_parent=bool(
                    str(child.coordinate_space or "").strip().lower() == "parent"
                    or (reinterpret_page_children and str(child.coordinate_space or "").strip().lower() == "page")
                ),
            )
            candidate_rects.append((child, rect))
            overflow += 1.0 - self._containment_ratio(rect, group_rect)
            readability_penalty += self._text_readability_penalty(child, rect)
        count = max(len(candidate_rects), 1)
        overflow_rate = overflow / count
        readability_rate = readability_penalty / count
        overlap_rate = self._overlap_rate([item[1] for item in candidate_rects])
        # Larger score is better.
        return 1.0 - (overflow_rate * 0.50 + overlap_rate * 0.30 + readability_rate * 0.20)

    def _text_readability_penalty(self, block: FreeformBlock, rect: tuple[float, float, float, float]) -> float:
        if str(block.type or "").strip().lower() != "text_box":
            return 0.0
        _, _, w, h = rect
        text = str(block.content or "").strip()
        if not text:
            return 0.0
        min_w = 0.18 if len(text) > 24 else 0.12
        min_h = 0.07
        penalty = 0.0
        if w < min_w:
            penalty += min(1.0, (min_w - w) / max(min_w, 0.001))
        if h < min_h:
            penalty += min(1.0, (min_h - h) / max(min_h, 0.001))
        return min(1.0, penalty)

    def _overlap_rate(self, rects: List[tuple[float, float, float, float]]) -> float:
        if len(rects) < 2:
            return 0.0
        pair_count = 0
        overlap_score = 0.0
        for index, left in enumerate(rects):
            for right in rects[index + 1 :]:
                pair_count += 1
                overlap = self._rect_intersection_area(left, right)
                if overlap <= 0.0:
                    continue
                left_area = max(left[2] * left[3], 0.0001)
                right_area = max(right[2] * right[3], 0.0001)
                overlap_score += min(1.0, overlap / min(left_area, right_area))
        if pair_count <= 0:
            return 0.0
        return max(0.0, min(1.0, overlap_score / pair_count))

    def _candidate_rect(
        self,
        block: FreeformBlock,
        *,
        parent_rect: tuple[float, float, float, float],
        assume_parent: bool,
    ) -> tuple[float, float, float, float]:
        parent_x, parent_y, parent_w, parent_h = parent_rect
        if assume_parent:
            x = parent_x + max(parent_w, 0.001) * _clamp01(block.x, 0.0)
            y = parent_y + max(parent_h, 0.001) * _clamp01(block.y, 0.0)
            w = max(parent_w, 0.001) * _clamp01(block.w, 0.0)
            h = max(parent_h, 0.001) * _clamp01(block.h, 0.0)
        else:
            x = float(block.x or 0.0)
            y = float(block.y or 0.0)
            w = float(block.w or 0.0)
            h = float(block.h or 0.0)
        return (x, y, max(w, 0.0), max(h, 0.0))

    def _containment_ratio(
        self,
        rect: tuple[float, float, float, float],
        container: tuple[float, float, float, float],
    ) -> float:
        rx, ry, rw, rh = rect
        cx, cy, cw, ch = container
        if rw <= 0.0 or rh <= 0.0:
            return 0.0
        inter_w = min(rx + rw, cx + cw) - max(rx, cx)
        inter_h = min(ry + rh, cy + ch) - max(ry, cy)
        if inter_w <= 0.0 or inter_h <= 0.0:
            return 0.0
        inter_area = inter_w * inter_h
        area = rw * rh
        if area <= 0.0:
            return 0.0
        return max(0.0, min(1.0, inter_area / area))

    def _resolve_group_block(self, block: FreeformBlock) -> FreeformBlock:
        out = block.model_copy(deep=True)
        if str(out.type or "").strip().lower() != "group":
            if out.children:
                out.children = [self._resolve_group_block(child) for child in list(out.children or [])]
            return out
        out.children = [self._resolve_group_block(child) for child in list(out.children or [])]
        if not out.children:
            return out
        if out.auto_fit or out.w <= 0.0 or out.h <= 0.0:
            x1, y1, x2, y2 = self._children_bbox(out.children)
            pad = out.padding if out.padding is not None else self._DEFAULT_CONTAINER_PAD
            x1 = max(0.0, x1 - pad)
            y1 = max(0.0, y1 - pad)
            x2 = min(1.0, x2 + pad)
            y2 = min(1.0, y2 + pad)
            out.x = x1
            out.y = y1
            out.w = max(x2 - x1, out.min_w or 0.12)
            out.h = max(y2 - y1, out.min_h or 0.10)
        return out

    def _resolve_linked_container_geometry(
        self,
        blocks: List[FreeformBlock],
        *,
        parent_bounds: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    ) -> List[FreeformBlock]:
        all_blocks = self._flatten_blocks(blocks)
        linked: Dict[str, List[FreeformBlock]] = {}
        for block in all_blocks:
            container_id = str(block.container_id or "").strip()
            if not container_id:
                continue
            linked.setdefault(container_id, []).append(block)

        pb_x, pb_y, pb_w, pb_h = parent_bounds

        def visit(block: FreeformBlock) -> FreeformBlock:
            out = block.model_copy(deep=True)
            block_type = str(out.type or "").strip().lower()
            # Recurse into groups, passing group bounds as parent_bounds
            if out.children:
                child_bounds = (out.x, out.y, out.w, out.h) if block_type == "group" else parent_bounds
                out.children = self._resolve_linked_container_geometry(
                    list(out.children or []), parent_bounds=child_bounds
                )
            block_id = str(out.id or "").strip()
            if block_id and block_id in linked and block_type in {"rectangle", "circle", "image", "chart"}:
                x1, y1, x2, y2 = self._children_bbox(linked[block_id])
                pad = out.padding if out.padding is not None else self._DEFAULT_CONTAINER_PAD
                needed_x = max(pb_x, x1 - pad)
                needed_y = max(pb_y, y1 - pad)
                needed_r = min(pb_x + pb_w, x2 + pad)
                needed_b = min(pb_y + pb_h, y2 + pad)
                if out.w <= 0.0 or out.h <= 0.0 or bool(out.auto_fit):
                    out.x = needed_x
                    out.y = needed_y
                    out.w = max(needed_r - needed_x, out.min_w or 0.12)
                    out.h = max(needed_b - needed_y, out.min_h or 0.10)
                else:
                    cur_r = out.x + out.w
                    cur_b = out.y + out.h
                    out.x = min(out.x, needed_x)
                    out.y = min(out.y, needed_y)
                    # Clamp expansion to parent group bounds
                    out.w = min(max(max(cur_r, needed_r) - out.x, out.min_w or 0.12), pb_x + pb_w - out.x)
                    out.h = min(max(max(cur_b, needed_b) - out.y, out.min_h or 0.10), pb_y + pb_h - out.y)
            return out

        return [visit(block) for block in list(blocks or [])]

    def _align_text_to_containers(self, blocks: List[FreeformBlock]) -> List[FreeformBlock]:
        """Reposition text blocks so they sit inside their linked containers.

        When the LLM places a text block at the wrong y/x (e.g. below its band
        instead of inside it), this pass moves the text into the container
        bounds with a small padding offset.  Runs after container geometry is
        finalized so we know the true container bounds.
        """
        all_blocks = self._flatten_blocks(blocks)
        container_map: Dict[str, FreeformBlock] = {}
        for block in all_blocks:
            bid = str(block.id or "").strip()
            if bid and str(block.type or "").strip().lower() in {"rectangle", "circle", "image", "chart", "group"}:
                container_map[bid] = block
        occupied_by_container: Dict[str, List[tuple[float, float, float, float]]] = {}

        def realign(block: FreeformBlock) -> FreeformBlock:
            out = block.model_copy(deep=True)
            if out.children:
                out.children = [realign(child) for child in list(out.children or [])]
            if str(out.type or "").strip().lower() != "text_box":
                return out
            cid = str(out.container_id or "").strip()
            if not cid or cid not in container_map:
                return out
            container = container_map[cid]
            cx, cy = float(container.x or 0), float(container.y or 0)
            cw, ch = float(container.w or 0), float(container.h or 0)
            tx, ty = float(out.x or 0), float(out.y or 0)
            tw, th = float(out.w or 0), float(out.h or 0)
            cpad_raw = getattr(container, "padding", None)
            tpad_raw = getattr(out, "padding", None)
            pad = float(tpad_raw) if tpad_raw is not None else (float(cpad_raw) if cpad_raw is not None else self._DEFAULT_CONTAINER_PAD)
            pad = max(0.002, min(pad, 0.08))
            # Check if text is outside the container bounds
            inside_x = tx >= cx - pad and tx + tw <= cx + cw + pad
            inside_y = ty >= cy - pad and ty + th <= cy + ch + pad
            if not (inside_x and inside_y):
                if not inside_x:
                    out.x = cx + pad
                    out.w = min(tw, cw - 2 * pad) if cw > 2 * pad else max(cw * 0.9, 0.05)
                if not inside_y:
                    out.y = cy + pad
                    out.h = min(th, ch - 2 * pad) if ch > 2 * pad else max(ch * 0.9, 0.05)
                logger.debug(
                    "normalizer_text_realigned block_id=%s container_id=%s "
                    "old=(%.3f,%.3f) new=(%.3f,%.3f)",
                    str(out.id or ""), cid, tx, ty, float(out.x), float(out.y),
                )

            # Avoid same-container text stacking after boundary realign.
            out.x = max(float(out.x or 0.0), cx + pad)
            out.w = min(max(float(out.w or 0.001), 0.001), max(cw - 2 * pad, 0.001))
            out.h = min(max(float(out.h or 0.001), 0.001), max(ch - 2 * pad, 0.001))
            out.y = max(float(out.y or 0.0), cy + pad)
            taken = occupied_by_container.setdefault(cid, [])
            cursor_y = float(out.y or 0.0)
            step = max(float(out.h or 0.001) + 0.004, 0.01)
            for _ in range(24):
                candidate = (float(out.x or 0.0), cursor_y, float(out.w or 0.001), float(out.h or 0.001))
                if all(self._rect_intersection_area(candidate, used) <= 0.0 for used in taken):
                    break
                cursor_y += step
            max_y = cy + ch - pad - float(out.h or 0.001)
            out.y = min(cursor_y, max_y)
            taken.append((float(out.x or 0.0), float(out.y or 0.0), float(out.w or 0.001), float(out.h or 0.001)))
            return out

        return [realign(block) for block in list(blocks or [])]

    def _apply_geometry_constraints(
        self,
        blocks: List[FreeformBlock],
        *,
        parent_rect: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    ) -> List[FreeformBlock]:
        return self._geometry_engine.apply_geometry_constraints(
            list(blocks or []),
            parent_rect=parent_rect,
            is_text_over_container_intended=self._is_text_over_container_intended,
            shift_children=self._shift_children,
            dedupe_siblings=self._dedupe_near_identical_siblings,
        )

    def _fix_block_geometry(
        self,
        block: FreeformBlock,
        *,
        parent_rect: tuple[float, float, float, float],
    ) -> FreeformBlock | None:
        out_blocks = self._geometry_engine.apply_geometry_constraints(
            [block.model_copy(deep=True)],
            parent_rect=parent_rect,
            is_text_over_container_intended=self._is_text_over_container_intended,
            shift_children=self._shift_children,
            dedupe_siblings=self._dedupe_near_identical_siblings,
        )
        return out_blocks[0] if out_blocks else None

    def _fix_line_geometry(
        self,
        block: FreeformBlock,
        *,
        parent_rect: tuple[float, float, float, float],
    ) -> FreeformBlock | None:
        return self._geometry_engine.fix_line_geometry(block, parent_rect=parent_rect)

    def _enforce_text_readability_bounds(
        self,
        block: FreeformBlock,
        *,
        parent_rect: tuple[float, float, float, float],
    ) -> FreeformBlock:
        return self._geometry_engine.enforce_text_readability_bounds(block, parent_rect=parent_rect)

    def _dedupe_near_identical_siblings(self, children: List[FreeformBlock]) -> List[FreeformBlock]:
        if len(children) <= 1:
            return children
        deduped: List[FreeformBlock] = []
        for child in list(children or []):
            block_type = str(child.type or "").strip().lower()
            role = str(child.role or "").strip().lower()
            rect = (
                float(child.x or 0.0),
                float(child.y or 0.0),
                float(child.w or 0.0),
                float(child.h or 0.0),
            )
            content = str(child.content or "").strip()
            style = dict(child.style or {})
            duplicate = False
            for kept in deduped:
                kept_type = str(kept.type or "").strip().lower()
                kept_role = str(kept.role or "").strip().lower()
                if kept_type != block_type or kept_role != role:
                    continue
                kept_rect = (
                    float(kept.x or 0.0),
                    float(kept.y or 0.0),
                    float(kept.w or 0.0),
                    float(kept.h or 0.0),
                )
                inter = self._rect_intersection_area(rect, kept_rect)
                area_a = max(rect[2] * rect[3], 0.0001)
                area_b = max(kept_rect[2] * kept_rect[3], 0.0001)
                iou = inter / max(area_a + area_b - inter, 0.0001)
                if iou < 0.92:
                    continue
                if block_type == "text_box":
                    if content and content != str(kept.content or "").strip():
                        continue
                else:
                    # For non-text shapes, require similar visual identity before deduping.
                    style_keys = ("background", "border_color", "border_width", "border_radius")
                    same_style = all(str(style.get(k) or "") == str(dict(kept.style or {}).get(k) or "") for k in style_keys)
                    if not same_style:
                        continue
                duplicate = True
                break
            if not duplicate:
                deduped.append(child)
        return deduped

    def _redistribute_all_groups(self, blocks: List[FreeformBlock]) -> List[FreeformBlock]:
        """Pre-pass: redistribute overflowing horizontal children in every group."""
        result: List[FreeformBlock] = []
        for block in list(blocks or []):
            out = block.model_copy(deep=True)
            if str(out.type or "").strip().lower() == "group" and out.children:
                group_rect = (float(out.x or 0), float(out.y or 0), float(out.w or 0), float(out.h or 0))
                out.children = self._redistribute_horizontal_overflow(
                    list(out.children or []), group_rect=group_rect
                )
                # Recurse into nested groups
                out.children = self._redistribute_all_groups(list(out.children or []))
            result.append(out)
        return result

    def _redistribute_horizontal_overflow(
        self,
        children: List[FreeformBlock],
        *,
        group_rect: tuple[float, float, float, float],
    ) -> List[FreeformBlock]:
        """When horizontally-arranged children overflow the group, redistribute evenly.

        Groups children by (type, y-band). If a row of same-type children
        overflows the group width, shrinks each and spaces them evenly.
        Text blocks that belong to a card (via container_id or proximity)
        are shifted to follow their card.
        """
        if len(children) < 3:
            return children
        gx, gy, gw, gh = group_rect
        if gw <= 0:
            return children

        adjusted = [child.model_copy(deep=True) for child in list(children or [])]
        y_tolerance = max(gh * 0.10, 0.04)

        # Group by (block_type, y-band) so rectangles and text are separated
        rows: Dict[tuple[str, int], List[int]] = {}
        for idx, child in enumerate(adjusted):
            child_type = str(child.type or "").strip().lower()
            if child_type in {"line", "icon"}:
                continue
            cy = float(child.y or 0)
            band_key = round((cy - gy) / max(y_tolerance, 0.001))
            rows.setdefault((child_type, band_key), []).append(idx)

        for (row_type, band_key), indices in rows.items():
            if len(indices) < 3:
                continue
            indices.sort(key=lambda i: float(adjusted[i].x or 0))
            rightmost = max(
                float(adjusted[i].x or 0) + max(float(adjusted[i].w or 0), 0.01)
                for i in indices
            )
            if rightmost <= gx + gw + 0.01:
                continue

            # Overflow → redistribute evenly within the group
            n = len(indices)
            gap = 0.01
            available = gw - (n - 1) * gap
            item_w = max(available / n, 0.04)
            pad = max((gw - n * item_w) / max(n - 1, 1), gap)

            # Record old→new x mapping for shifting linked text blocks
            x_shift_map: Dict[int, tuple[float, float]] = {}  # idx → (old_x, new_x)
            for rank, idx in enumerate(indices):
                block = adjusted[idx]
                old_x = float(block.x or 0)
                new_x = gx + rank * (item_w + pad)
                block.x = new_x
                block.w = item_w
                x_shift_map[idx] = (old_x, new_x)

            # Shift text/icon blocks that were near the moved blocks
            if row_type in {"rectangle", "circle", "group"}:
                for idx, child in enumerate(adjusted):
                    if idx in {i for i in indices}:
                        continue
                    child_type = str(child.type or "").strip().lower()
                    if child_type not in {"text_box", "icon"}:
                        continue
                    cx = float(child.x or 0)
                    # Find the nearest moved block by old_x proximity
                    best_shift = None
                    best_dist = float("inf")
                    for moved_idx, (old_x, new_x) in x_shift_map.items():
                        dist = abs(cx - old_x)
                        if dist < best_dist and dist < item_w + 0.05:
                            best_dist = dist
                            best_shift = new_x - old_x
                    if best_shift is not None:
                        child.x = cx + best_shift
                        child.w = min(float(child.w or 0), item_w - 0.02)

            logger.debug(
                "normalizer_horizontal_redistribute type=%s band=%s items=%s item_w=%.3f",
                row_type, band_key, n, item_w,
            )

        return adjusted

    def _constrain_children_within_group(
        self,
        children: List[FreeformBlock],
        *,
        group_rect: tuple[float, float, float, float],
    ) -> List[FreeformBlock]:
        out = self._geometry_engine.apply_geometry_constraints(
            list(children or []),
            parent_rect=group_rect,
            is_text_over_container_intended=self._is_text_over_container_intended,
            shift_children=self._shift_children,
            dedupe_siblings=self._dedupe_near_identical_siblings,
        )
        return list(out or [])

    def _resolve_group_sibling_overlaps(
        self,
        children: List[FreeformBlock],
        *,
        group_rect: tuple[float, float, float, float],
    ) -> List[FreeformBlock]:
        return self._geometry_engine.apply_geometry_constraints(
            list(children or []),
            parent_rect=group_rect,
            is_text_over_container_intended=self._is_text_over_container_intended,
            shift_children=self._shift_children,
            dedupe_siblings=self._dedupe_near_identical_siblings,
        )

    def _clamp_rect_to_container(
        self,
        *,
        x: float,
        y: float,
        w: float,
        h: float,
        container: tuple[float, float, float, float],
    ) -> tuple[float, float, float, float]:
        return self._geometry_engine.clamp_rect_to_container(
            x=x, y=y, w=w, h=h, container=container
        )

    def _clamp_point_to_container(
        self,
        point: tuple[float, float],
        container: tuple[float, float, float, float],
    ) -> tuple[float, float]:
        return self._geometry_engine.clamp_point_to_container(point, container)

    def _rect_intersection_area(
        self,
        left: tuple[float, float, float, float],
        right: tuple[float, float, float, float],
    ) -> float:
        return rect_intersection_area_util(left, right)

    def _is_background_block(self, block: FreeformBlock) -> bool:
        """Return True for blocks that intentionally sit behind others (backgrounds, surfaces)."""
        role = str(block.role or "").strip().lower()
        if role in {"background", "surface"}:
            return True
        bid = str(block.id or "").strip().lower()
        if any(token in bid for token in ("bg", "background", "surface")):
            return True
        # Full-page shapes are backgrounds by definition
        return float(block.w or 0) >= 0.90 and float(block.h or 0) >= 0.90

    def _resolve_top_level_overlaps(self, blocks: List[FreeformBlock]) -> List[FreeformBlock]:
        return self._overlap_engine.resolve_top_level_overlaps(
            list(blocks or []),
            is_text_over_container_intended=self._is_text_over_container_intended,
            is_background_block=self._is_background_block,
            shift_children=self._shift_children,
            rect_intersection_area=self._rect_intersection_area,
            clamp_rect_to_container=self._clamp_rect_to_container,
        )

    def _shift_children(self, block: FreeformBlock, dx: float, dy: float) -> None:
        """Shift all children by (dx, dy) — keeps them inside a moved group."""
        for child in list(block.children or []):
            child.x = float(child.x or 0) + dx
            child.y = float(child.y or 0) + dy
            if child.x2 is not None:
                child.x2 = float(child.x2) + dx
            if child.y2 is not None:
                child.y2 = float(child.y2) + dy
            if child.children:
                self._shift_children(child, dx, dy)

    def _final_constrain_children(self, blocks: List[FreeformBlock]) -> List[FreeformBlock]:
        return self._geometry_engine.final_constrain_children(list(blocks or []))

    def _cleanup_invalid_blocks(self, blocks: List[FreeformBlock]) -> List[FreeformBlock]:
        cleaned: List[FreeformBlock] = []
        for block in list(blocks or []):
            out = block.model_copy(deep=True)
            block_type = str(out.type or "").strip().lower()
            if block_type == "group":
                out.children = self._cleanup_invalid_blocks(list(out.children or []))
                if not out.children:
                    # Empty group = empty shell on screen. Remove regardless of
                    # visual style — a styled empty group is just a colored box
                    # that wastes space and looks like a broken placeholder.
                    continue
                cleaned.append(out)
                continue
            if block_type in {"rectangle", "circle", "image", "chart"} and out.w <= 0.0 and out.h <= 0.0:
                continue
            if block_type == "text_box" and not str(out.content or "").strip():
                continue
            cleaned.append(out)
        return cleaned

    def _cleanup_orphan_decorations(self, blocks: List[FreeformBlock]) -> List[FreeformBlock]:
        """Remove shape blocks that serve no structural purpose.

        A shape is orphan when:
        1. It is a rectangle or circle (not text_box, group, line, image, icon)
        2. It has no children
        3. It is not referenced as a container by any other block
        4. It is not a background/surface block
        5. Either: area < 0.8% (tiny decoration) OR no content purpose at all

        Removes both tiny decorative dots AND large empty containers that
        the LLM created but never filled with text.
        """
        # Collect all container_id references so we don't remove used containers
        referenced_ids: set[str] = set()
        for block in self._flatten_blocks(blocks):
            cid = str(block.container_id or "").strip()
            if cid:
                referenced_ids.add(cid)

        # Build a set of block IDs that have nearby text siblings (geometric overlap)
        # so we don't remove card/panel backgrounds that visually contain text.
        has_text_nearby: set[str] = set()
        all_flat = self._flatten_blocks(blocks)
        text_rects = [
            (float(b.x or 0), float(b.y or 0), float(b.w or 0), float(b.h or 0))
            for b in all_flat
            if str(b.type or "").strip().lower() == "text_box" and str(b.content or "").strip()
        ]
        for block in all_flat:
            bid = str(block.id or "").strip()
            if not bid or str(block.type or "").strip().lower() not in {"rectangle", "circle"}:
                continue
            bx, by, bw, bh = float(block.x or 0), float(block.y or 0), float(block.w or 0), float(block.h or 0)
            for tx, ty, tw, th in text_rects:
                inter_w = min(bx + bw, tx + tw) - max(bx, tx)
                inter_h = min(by + bh, ty + th) - max(by, ty)
                if inter_w > 0 and inter_h > 0:
                    has_text_nearby.add(bid)
                    break

        # Detect timeline-node-like small shapes: ≥3 small same-type blocks at similar y
        timeline_node_ids: set[str] = set()
        small_shapes = [
            b for b in self._flatten_blocks(blocks)
            if str(b.type or "").strip().lower() in {"circle", "rectangle"}
            and float(b.w or 0) <= 0.07 and float(b.h or 0) <= 0.07
            and float(b.w or 0) > 0 and float(b.h or 0) > 0
        ]
        if len(small_shapes) >= 3:
            # Check if they share a similar y (timeline row)
            ys = [float(b.y or 0) for b in small_shapes]
            avg_y = sum(ys) / len(ys)
            aligned = [b for b in small_shapes if abs(float(b.y or 0) - avg_y) < 0.05]
            if len(aligned) >= 3:
                timeline_node_ids = {str(b.id or "") for b in aligned}

        def is_orphan(block: FreeformBlock) -> bool:
            block_type = str(block.type or "").strip().lower()
            if block_type not in {"rectangle", "circle"}:
                return False
            if block.children:
                return False
            block_id = str(block.id or "").strip()
            if block_id in referenced_ids:
                return False
            if self._is_background_block(block):
                return False
            if block_id in has_text_nearby:
                return False  # Likely a card/panel behind text
            if block_id in timeline_node_ids:
                return False  # Likely a timeline step node
            # Unreferenced shape with no text nearby = either noise or empty shell
            return True

        cleaned: List[FreeformBlock] = []
        for block in list(blocks or []):
            out = block.model_copy(deep=True)
            if str(out.type or "").strip().lower() == "group" and out.children:
                out.children = self._cleanup_orphan_decorations(list(out.children or []))
            if is_orphan(out):
                logger.debug(
                    "normalizer_orphan_decoration_removed block_id=%s type=%s w=%.3f h=%.3f area=%.4f",
                    str(out.id or ""), str(out.type or ""),
                    float(out.w or 0), float(out.h or 0),
                    float(out.w or 0) * float(out.h or 0),
                )
                continue
            cleaned.append(out)
        return cleaned

    def _sort_blocks_for_rendering(self, blocks: List[FreeformBlock]) -> List[FreeformBlock]:
        ordered: List[FreeformBlock] = []
        for block in list(blocks or []):
            out = block.model_copy(deep=True)
            if out.children:
                out.children = self._sort_blocks_for_rendering(list(out.children or []))
            ordered.append(out)
        return sorted(ordered, key=self._render_order_key)

    def evaluate_deck_quality(self, deck: FreeformDeckBlueprint) -> Dict[str, Any]:
        return self._quality_engine.evaluate_deck_quality(
            deck,
            is_text_over_container_intended=self._is_text_over_container_intended,
        )

    def _page_quality_metrics(self, page: FreeformPageBlueprint) -> Dict[str, Any]:
        return self._quality_engine.page_quality_metrics(
            page,
            is_text_over_container_intended=self._is_text_over_container_intended,
        )

    def _needs_strict_text_readability(self, block: FreeformBlock) -> bool:
        return self._quality_engine.needs_strict_text_readability(block)

    def _is_severe_narrow_text(
        self,
        block: FreeformBlock,
        *,
        min_w: float,
        min_h: float,
        w: float,
        h: float,
    ) -> bool:
        return self._quality_engine.is_severe_narrow_text(
            block,
            min_w=min_w,
            min_h=min_h,
            w=w,
            h=h,
        )

    def _count_children_outside(self, blocks: List[FreeformBlock]) -> tuple[int, int]:
        return self._quality_engine.count_children_outside(list(blocks or []))

    def _count_overlapping_siblings(self, blocks: List[FreeformBlock]) -> tuple[int, int]:
        return self._quality_engine.count_overlapping_siblings(
            list(blocks or []),
            is_text_over_container_intended=self._is_text_over_container_intended,
        )

    def _count_layer_overlap(self, siblings: List[FreeformBlock]) -> tuple[int, int]:
        return self._quality_engine.count_layer_overlap(
            list(siblings or []),
            is_text_over_container_intended=self._is_text_over_container_intended,
        )

    def _is_text_over_container_intended(self, first: FreeformBlock, second: FreeformBlock) -> bool:
        return text_over_container_intended_util(first, second)

    def _render_order_key(self, block: FreeformBlock) -> tuple[int, float]:
        return render_order_key_util(block)

    def _flatten_blocks(self, blocks: List[FreeformBlock]) -> List[FreeformBlock]:
        return flatten_blocks_util(list(blocks or []))

    def _children_bbox(self, blocks: List[FreeformBlock]) -> tuple[float, float, float, float]:
        return calc_children_bbox(list(blocks or []))

    def _estimated_min_height(self, line_count: int, font_size: float) -> float:
        required_px = line_count * font_size * 1.35 + 24.0
        return max(0.06, min(required_px / 900.0, 0.50))

    def _estimated_line_capacity(self, width_ratio: float, font_size: float) -> int:
        if width_ratio <= 0.0:
            return 0
        # Approximate Chinese characters per line on a 1600px canvas with 0.9 content width factor.
        usable_px = 1600 * max(width_ratio, 0.01) * 0.88
        char_px = max(font_size * 1.05, 10.0)
        return max(1, int(usable_px / char_px))

    def _estimated_line_count(self, text: str, chars_per_line: int) -> int:
        segments = [segment for segment in text.replace("<br/>", "\n").split("\n")]
        total = 0
        for segment in segments:
            clean = segment.strip()
            if not clean:
                total += 1
                continue
            total += max(1, (len(clean) + chars_per_line - 1) // chars_per_line)
        return max(total, 1)

    def _normalize_style(self, style: Dict[str, Any], *, shape_type: str, tokens: DesignTokens) -> Dict[str, Any]:
        return self._style_engine.normalize_style(
            dict(style or {}),
            shape_type=shape_type,
            tokens=tokens,
        )

    def _has_visual_style(self, style: Dict[str, Any]) -> bool:
        return self._style_engine.has_visual_style(dict(style or {}))

    def _as_number(self, value: Any) -> float | None:
        return self._style_engine.as_number(value)
