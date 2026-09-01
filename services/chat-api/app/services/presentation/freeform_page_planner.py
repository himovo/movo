from __future__ import annotations

import inspect
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional, Set

from app.core.config import get_settings
from pydantic import BaseModel, Field
from app.services.presentation.contracts import StoryDeckPlan, StoryPageSpec
from app.services.presentation.llm_utils import invoke_structured
from app.services.presentation.brief_compiler import BriefCompiler
from app.services.presentation.contracts import (
    ComposerPageBlueprint,
    ConstraintBundle,
    DeckBrief,
    FreeformDeckBlueprint,
    DesignTokens,
    FreeformBlock,
    FreeformPageBlueprint,
    PageBrief,
    PageGenerationContext,
    PageRepairReport,
)
from app.services.presentation.renderable_normalizer import RenderableAstNormalizer
from app.services.presentation.layout_protocol import (
    CHILD_OUTSIDE_CONTAINER_RATIO_LIMIT,
    HARD_QUALITY_ISSUES,
    MIN_LINE_LENGTH,
    OVERLAP_HARD_COUNT_THRESHOLD,
    SIBLING_OVERLAP_RATIO_THRESHOLD,
    text_geometry_requirements,
)
from app.services.presentation.layout_utils import (
    id_stem as id_stem_util,
    is_text_over_container_intended as text_over_container_intended_util,
    rect_intersection_area as rect_intersection_area_util,
)
from app.services.presentation.theme_factory_catalog import (
    apply_theme_spec_to_design_tokens,
    build_freeform_theme_from_design_tokens,
    get_theme_spec_by_slug,
    infer_theme_spec,
    theme_catalog_prompt_text,
)
from app.services.presentation.layout_archetypes import LayoutAssignmentPlanner, archetype_by_id
from app.services.presentation.layout_archetypes.conformance import (
    layout_conformance_issues,
)
from app.services.presentation.generative_design import DeckVisualDirector, DeckVisualPlan
from app.services.presentation.generative_design.composition_grammar import fallback_deck_visual_plan
from app.services.presentation.generative_design.page_payload import build_page_composition_payload
from app.services.presentation.generative_design.prompts import build_page_composition_prompt

logger = logging.getLogger(__name__)


def _log_page_compose_grounding_dump(*, page_id: str, bundle: ConstraintBundle) -> None:
    """Dump a compact preview of the grounding evidence carried into each
    per-page compose LLM call. Emits WARNING so it is visible under the
    default backend log filter.
    """
    observations = list(getattr(bundle, "tool_observations", None) or [])
    if not observations:
        logger.debug(
            "presentation_page_compose_grounding_dump page_id=%s observation_count=0",
            page_id or "(unknown)",
        )
        return
    previews: List[str] = []
    for obs in observations:
        if not isinstance(obs, dict):
            continue
        ev = str(obs.get("evidence_id") or "")
        tool = str(obs.get("tool") or "")
        src = str(obs.get("source_label") or "")
        summary = str(obs.get("summary") or "").replace("\n", " ")
        summary_preview = summary[:160] + ("…" if len(summary) > 160 else "")
        previews.append(
            f"[{ev}] tool={tool or '-'} source={src or '-'} summary={summary_preview!r}"
        )
    logger.debug(
        "presentation_page_compose_grounding_dump page_id=%s observation_count=%s\n  %s",
        page_id or "(unknown)",
        len(previews),
        "\n  ".join(previews),
    )


class _DeckBriefEnvelope(DeckBrief):
    pass


class _MovLayoutBlock(BaseModel):
    """Small authoring schema; runtime-only block fields stay out of the LLM call."""

    id: str = Field(min_length=1)
    type: Literal["text_box", "rectangle", "circle", "line", "image", "group", "icon", "chart"]
    role: str = ""
    container_id: str = ""
    coordinate_space: Literal["page", "parent"] = "page"
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    x2: float | None = Field(default=None, ge=0.0, le=1.0)
    y2: float | None = Field(default=None, ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)
    content: str = ""
    style: Dict[str, Any] = Field(default_factory=dict)
    children: List["_MovLayoutBlock"] = Field(default_factory=list)
    icon: str = ""
    image_prompt: str = ""
    auto_fit: bool = False
    chart_type: Literal["", "line", "bar", "pie"] = ""
    chart_data: Dict[str, Any] = Field(default_factory=dict)
    z_index: int = Field(default=0, ge=0, le=20)


class _MovLayoutPageResponse(BaseModel):
    """Compact page authoring response converted to runtime IR after generation."""

    page_id: str = ""
    page_title: str = ""
    page_subtitle: str = ""
    layout_type: str = ""
    design_intent: str = ""
    style: Dict[str, Any] = Field(default_factory=dict)
    blocks: List[_MovLayoutBlock] = Field(min_length=2)


class FreeformPagePlanner:
    def __init__(self) -> None:
        self._brief_compiler = BriefCompiler()
        self._layout_planner = LayoutAssignmentPlanner()
        self._visual_director = DeckVisualDirector()

    def _serialize_messages(self, messages: List[Any]) -> List[Dict[str, Any]]:
        serialized: List[Dict[str, Any]] = []
        for item in list(messages or []):
            if isinstance(item, dict):
                serialized.append(
                    {
                        "role": str(item.get("role") or "").strip(),
                        "content": item.get("content"),
                    }
                )
                continue
            role = str(getattr(item, "role", "") or "").strip()
            content = getattr(item, "content", "")
            if hasattr(content, "model_dump"):
                try:
                    content = content.model_dump()
                except Exception:
                    content = str(content)
            elif isinstance(content, list):
                content = [
                    entry.model_dump() if hasattr(entry, "model_dump") else entry
                    for entry in content
                ]
            serialized.append(
                {
                    "role": role,
                    "content": content,
                }
            )
        return serialized

    def _extract_message_text(self, messages: List[Any]) -> str:
        parts: List[str] = []
        for item in list(messages or []):
            role = ""
            content: Any = ""
            if isinstance(item, dict):
                role = str(item.get("role") or "").strip()
                content = item.get("content")
            else:
                role = str(getattr(item, "role", "") or "").strip()
                content = getattr(item, "content", "")
            if role != "user":
                continue
            if isinstance(content, str) and content.strip():
                parts.append(content.strip())
            elif isinstance(content, list):
                for entry in content:
                    if not isinstance(entry, dict):
                        continue
                    text = str(entry.get("text") or "").strip()
                    if text:
                        parts.append(text)
        return "\n\n".join(parts[-6:]).strip()

    def _extract_user_outline(self, *, messages: List[Any], output_spec: Dict[str, Any]) -> str:
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        schema = content_task_spec.get("schema") if isinstance(content_task_spec.get("schema"), dict) else {}
        section_specs = [
            item for item in list(schema.get("section_specs") or [])
            if isinstance(item, dict) and str(item.get("title") or "").strip()
        ]
        if section_specs:
            lines = []
            for idx, item in enumerate(section_specs, start=1):
                line = f"{idx}. {str(item.get('title') or '').strip()}"
                purpose = str(item.get("purpose") or "").strip()
                topics = [str(x).strip() for x in list(item.get("must_cover_topics") or []) if str(x).strip()]
                if purpose:
                    line += f" | purpose={purpose}"
                if topics:
                    line += f" | topics={', '.join(topics[:6])}"
                lines.append(line)
            return "\n".join(lines).strip()

        explicit_outline = str(
            output_spec.get("outline")
            or output_spec.get("deck_outline")
            or output_spec.get("user_outline")
            or ""
        ).strip()
        if explicit_outline:
            return explicit_outline
        return self._extract_message_text(messages)

    def _extract_generation_guidance(self, *, messages: List[Any], output_spec: Dict[str, Any]) -> str:
        compose_policy = output_spec.get("compose_policy") if isinstance(output_spec.get("compose_policy"), dict) else {}
        guidance_chunks: List[str] = []
        for key in ("user_request", "deck_goal", "presentation_context", "target_audience"):
            value = str(output_spec.get(key) or "").strip()
            if value:
                guidance_chunks.append(f"{key}: {value}")
        writing_instructions = [str(x).strip() for x in list(compose_policy.get("writing_instructions") or []) if str(x).strip()]
        required_sections = [str(x).strip() for x in list(compose_policy.get("required_sections") or []) if str(x).strip()]
        if writing_instructions:
            guidance_chunks.append(f"writing_instructions: {' | '.join(writing_instructions[:12])}")
        if required_sections:
            guidance_chunks.append(f"required_sections: {' | '.join(required_sections[:12])}")
        raw_user_text = self._extract_message_text(messages)
        if raw_user_text:
            guidance_chunks.append(f"user_messages: {raw_user_text}")
        return "\n".join(guidance_chunks).strip()

    def _story_payload(self, *, story_plan: StoryDeckPlan) -> Dict[str, Any]:
        return {
            "deck_id": story_plan.deck_id,
            "deck_goal": story_plan.deck_goal,
            "target_audience": story_plan.target_audience,
            "presentation_context": story_plan.presentation_context,
            "language": story_plan.language,
            "narrative_outline": list(story_plan.narrative_outline or []),
            "pages": [
                {
                    "page_id": page.page_id,
                    "page_index": page.page_index,
                    "page_type": page.page_type,
                    "page_intent": page.page_intent,
                    "communication_goal": page.communication_goal,
                    "key_message": page.key_message,
                    "visual_intent": page.visual_intent,
                    "narrative_role": page.narrative_role,
                    "density_level": page.density_level,
                }
                for page in list(story_plan.pages or [])
            ],
        }

    def _default_page_brief(self, page: StoryPageSpec, *, user_outline: str, generation_guidance: str) -> PageBrief:
        outline_section = self._outline_section_for_page(
            user_outline=user_outline,
            page_index=int(page.page_index or 0),
        )
        return PageBrief(
            page_id=str(page.page_id or "").strip(),
            page_index=int(page.page_index or 0),
            page_type=str(page.page_type or "content").strip() or "content",
            page_goal=str(page.communication_goal or "").strip(),
            key_takeaway=str(page.key_message or "").strip(),
            visual_intent=str(page.visual_intent or "").strip(),
            composition_intent=str(page.visual_intent or page.page_intent or "").strip(),
            narrative_role=str(page.narrative_role or "").strip(),
            source_outline_section=outline_section,
            source_user_intent=generation_guidance[:400],
            must_include=[
                str(page.key_message or "").strip(),
                str(page.visual_intent or "").strip(),
            ],
            must_avoid=[
                "generic report-like text dump",
                "repeating the same layout as nearby pages",
            ],
            visual_center=str(page.visual_intent or page.key_message or "").strip(),
            dominant_move=str(page.visual_intent or page.page_intent or "").strip(),
            must_visualize=[str(page.visual_intent or "").strip()],
            validation_profile=str(page.page_intent or "presentation_page").strip() or "presentation_page",
        )

    @staticmethod
    def _outline_section_for_page(*, user_outline: str, page_index: int) -> str:
        text = str(user_outline or "").strip()
        if not text:
            return ""
        lines = [
            line.strip()
            for line in re.split(r"[\r\n]+", text)
            if str(line or "").strip()
        ]
        if not lines:
            return text[:400]
        idx = max(1, int(page_index or 1)) - 1
        if idx < len(lines):
            return lines[idx][:400]
        return lines[-1][:400]

    async def _build_deck_brief(
        self,
        *,
        story_plan: StoryDeckPlan,
        constraint_bundle: ConstraintBundle,
        user_message_context: str,
    ) -> DeckBrief:
        payload = {
            "story_plan_brief": self._brief_compiler.compile_story_plan_brief(story_plan),
            "constraint_brief": self._brief_compiler.compile_constraint_brief(constraint_bundle),
            "user_message_context": user_message_context,
        }
        system_prompt = (
            "You are the deck strategist for Presentation Pipeline.\n"
            "Return JSON only matching DeckBrief.\n"
            "Your job is to build a coherent deck-level plan that preserves user intent and keeps page-to-page continuity strong.\n"
            "Rules:\n"
            "- Preserve the exact page order and page_id values from the story plan brief.\n"
            "- Respect the user's outline, requested sections, generation ideas, and any active skill constraints whenever they are present.\n"
            "- Do not summarize away the user's intent. Capture it in user_outline, user_generation_guidance, source_outline_section, and source_user_intent.\n"
            "- page_briefs are light-weight page directives, not component plans. Do not choose coordinates or rigid templates here.\n"
            "- design_tokens must define stable visual constants for the whole deck so page-level generation does not drift in style.\n"
            "- Each page_brief must state what the page is trying to achieve, what it must include, what it should avoid, and how it connects to nearby pages.\n"
            "- Each page_brief should describe visual_center, dominant_move, must_visualize, and a validation_profile suitable for that page's intent.\n"
            "- Each page_brief MUST fill key_takeaway (the single most important message the audience should remember from this page) "
            "and composition_intent (how the page should be visually structured, e.g. 'left-right comparison', 'horizontal timeline', 'layered architecture stack', 'card grid with 4 cards').\n"
            "- Keep the whole deck coherent: define continuity_rules and visual_direction that can be reused by every page composer call.\n"
            "- Avoid repetitive composition across neighboring pages by expressing rhythm and contrast at the brief level.\n"
            "- Choose one theme_factory_name from the provided catalog. Fill theme_factory_name, theme_factory_rationale, "
            "theme_factory_colors, and theme_factory_typography.\n"
            "- Theme selection guidance: PREFER themes with strong accent colors that create visual energy — "
            "tech-innovation (electric blue), sunset-boulevard (burnt orange + coral), golden-hour (mustard + terracotta), "
            "ocean-depths (teal + seafoam), midnight-galaxy (purple + lavender) are all excellent choices. "
            "AVOID defaulting to modern-minimalist or arctic-frost for every deck — gray-only decks feel like rough drafts. "
            "A deck with one bold accent color always looks more polished and intentional than an all-gray deck. "
            "Match the theme to the content mood: tech topics → tech-innovation; strategy/leadership → midnight-galaxy or golden-hour; "
            "nature/sustainability → botanical-garden or forest-canopy; consumer/retail → sunset-boulevard or desert-rose.\n"
            "- Output exactly one PageBrief for every page in the story plan brief.\n"
            "Theme factory catalog:\n"
            f"{theme_catalog_prompt_text()}\n"
        )
        try:
            brief = await invoke_structured(
                model_cls=_DeckBriefEnvelope,
                system_prompt=system_prompt,
                payload=payload,
                stage="presentation_deck_brief",
                intent="generation",
            )
        except Exception:
            logger.warning("presentation_deck_brief_fallback deck_id=%s", str(story_plan.deck_id or "").strip(), exc_info=True)
            brief = _DeckBriefEnvelope(
                deck_id=str(story_plan.deck_id or "presentation").strip() or "presentation",
                deck_goal=str(story_plan.deck_goal or "").strip(),
                target_audience=str(story_plan.target_audience or "").strip(),
                presentation_context=str(story_plan.presentation_context or "").strip(),
                language=str(story_plan.language or "zh-CN").strip() or "zh-CN",
                narrative_arc=list(story_plan.narrative_outline or []),
                user_outline=constraint_bundle.user_outline,
                user_generation_guidance=constraint_bundle.user_generation_guidance,
                continuity_rules=[
                    "Preserve terminology and argument continuity across pages.",
                    "Vary composition while keeping the same business presentation tone.",
                    "Honor the user outline and story order exactly.",
                ],
                visual_direction=[
                    "business presentation",
                    "clear hierarchy",
                    "strong focal points",
                ],
                design_tokens=DesignTokens(),
                page_briefs=[
                    self._default_page_brief(
                        page,
                        user_outline=constraint_bundle.user_outline,
                        generation_guidance=constraint_bundle.user_generation_guidance,
                    )
                    for page in list(story_plan.pages or [])
                ],
            )

        by_id = {str(item.page_id or "").strip(): item for item in list(brief.page_briefs or []) if str(item.page_id or "").strip()}
        normalized_briefs: List[PageBrief] = []
        for page in list(story_plan.pages or []):
            page_id = str(page.page_id or "").strip()
            normalized_briefs.append(
                by_id.get(page_id)
                or self._default_page_brief(
                    page,
                    user_outline=constraint_bundle.user_outline,
                    generation_guidance=constraint_bundle.user_generation_guidance,
                )
            )
        brief.deck_id = str(brief.deck_id or story_plan.deck_id or "presentation").strip() or "presentation"
        brief.deck_goal = str(brief.deck_goal or story_plan.deck_goal or "").strip()
        brief.target_audience = str(brief.target_audience or story_plan.target_audience or "").strip()
        brief.presentation_context = str(brief.presentation_context or story_plan.presentation_context or "").strip()
        brief.language = str(brief.language or story_plan.language or "zh-CN").strip() or "zh-CN"
        brief.page_briefs = normalized_briefs
        if not brief.user_outline:
            brief.user_outline = constraint_bundle.user_outline
        if not brief.user_generation_guidance:
            brief.user_generation_guidance = constraint_bundle.user_generation_guidance
        if not brief.narrative_arc:
            brief.narrative_arc = list(story_plan.narrative_outline or [])
        if not brief.continuity_rules:
            brief.continuity_rules = [
                "Keep terminology and visual tone consistent across the deck.",
                "Avoid reusing the same composition on adjacent pages.",
                "Honor the user outline and requested flow.",
            ]
        if not brief.visual_direction:
            brief.visual_direction = [
                "clean executive presentation",
                "strong page hierarchy",
                "integrated text and graphics",
            ]
        if not isinstance(brief.design_tokens, DesignTokens):
            brief.design_tokens = DesignTokens()
        return brief

    def _resolve_deck_theme(self, brief: DeckBrief, *, constraint_bundle: ConstraintBundle) -> DeckBrief:
        resolved = brief.model_copy(deep=True)
        selected_spec = get_theme_spec_by_slug(str(resolved.theme_factory_name or "").strip())
        if selected_spec is None:
            selected_spec = infer_theme_spec(
                deck_goal=str(resolved.deck_goal or "").strip(),
                target_audience=str(resolved.target_audience or "").strip(),
                user_outline=str(constraint_bundle.user_outline or "").strip(),
            )
        resolved.design_tokens = apply_theme_spec_to_design_tokens(
            resolved.design_tokens if isinstance(resolved.design_tokens, DesignTokens) else DesignTokens(),
            selected_spec,
        )
        if selected_spec:
            resolved.theme_factory_name = str(selected_spec.get("slug") or selected_spec.get("name") or "").strip()
            if not str(resolved.theme_factory_rationale or "").strip():
                resolved.theme_factory_rationale = str(
                    selected_spec.get("best_for") or "Selected by topic and audience fit."
                ).strip()
            colors = selected_spec.get("colors") if isinstance(selected_spec.get("colors"), dict) else {}
            typography = selected_spec.get("typography") if isinstance(selected_spec.get("typography"), dict) else {}
            resolved.theme_factory_colors = dict(colors)
            resolved.theme_factory_typography = dict(typography)
        return resolved

    def _theme_reference_markdown(self, theme_factory_name: str) -> str:
        slug = str(theme_factory_name or "").strip().lower()
        if not slug:
            return ""
        slug = slug.replace("_", "-").replace(" ", "-")
        if not re.fullmatch(r"[a-z0-9-]+", slug):
            return ""
        theme_path = (
            Path(__file__).resolve().parent
            / "theme_factory"
            / "themes"
            / f"{slug}.md"
        )
        try:
            if not theme_path.exists():
                return ""
            text = theme_path.read_text(encoding="utf-8").strip()
            return text[:8000]
        except Exception:
            return ""

    def _block_area(self, block: FreeformBlock) -> float:
        try:
            return max(0.0, float(block.w or 0.0)) * max(0.0, float(block.h or 0.0))
        except Exception:
            return 0.0

    def _font_size_of(self, block: FreeformBlock) -> float | None:
        try:
            raw = dict(block.style or {}).get("font_size")
            if raw in (None, ""):
                return None
            return float(raw)
        except Exception:
            return None

    def _effective_block_count(self, blocks: List[FreeformBlock]) -> int:
        count = 0
        for block in list(blocks or []):
            block_type = str(block.type or "").strip().lower()
            if block_type == "group":
                count += self._effective_block_count(list(block.children or []))
                continue
            if block_type == "text_box" and not str(block.content or "").strip():
                continue
            count += 1
        return count

    def _page_occupancy(self, blocks: List[FreeformBlock]) -> float:
        regions = self._visual_regions(blocks)
        if not regions:
            return 0.0
        cols = 48
        rows = 27
        occupied = 0
        for row in range(rows):
            cy = (row + 0.5) / rows
            for col in range(cols):
                cx = (col + 0.5) / cols
                if any(x <= cx <= x + w and y <= cy <= y + h for x, y, w, h in regions):
                    occupied += 1
        return occupied / float(cols * rows)

    def _degenerate_line_count(self, blocks: List[FreeformBlock]) -> int:
        count = 0
        for block in list(blocks or []):
            if str(block.type or "").strip().lower() == "line":
                x2 = block.x2 if block.x2 is not None else float(block.x or 0.0) + float(block.w or 0.0)
                y2 = block.y2 if block.y2 is not None else float(block.y or 0.0) + float(block.h or 0.0)
                if abs(float(x2 or 0.0) - float(block.x or 0.0)) < 0.005 and abs(float(y2 or 0.0) - float(block.y or 0.0)) < 0.005:
                    count += 1
            if str(block.type or "").strip().lower() == "group":
                count += self._degenerate_line_count(list(block.children or []))
        return count

    def _circle_count(self, blocks: List[FreeformBlock]) -> int:
        """Count large circles (w>0.06). Small circles used as timeline nodes are OK."""
        count = 0
        for block in list(blocks or []):
            if str(block.type or "").strip().lower() == "circle" and float(block.w or 0) > 0.06:
                count += 1
            if str(block.type or "").strip().lower() == "group":
                count += self._circle_count(list(block.children or []))
        return count

    def _line_count(self, blocks: List[FreeformBlock]) -> int:
        count = 0
        for block in list(blocks or []):
            block_type = str(block.type or "").strip().lower()
            if block_type == "line":
                count += 1
            if block_type == "group":
                count += self._line_count(list(block.children or []))
        return count

    def _primary_anchor_present(self, blocks: List[FreeformBlock]) -> bool:
        for block in list(blocks or []):
            block_type = str(block.type or "").strip().lower()
            if block_type == "group":
                if self._styled_container(block) and (
                    self._block_area(block) >= 0.10 or float(block.w or 0.0) >= 0.38 or float(block.h or 0.0) >= 0.22
                ):
                    return True
                if self._primary_anchor_present(list(block.children or [])):
                    return True
                continue
            if block_type == "text_box":
                if str(block.content or "").strip() and float(block.w or 0.0) >= 0.42 and float(block.h or 0.0) >= 0.08:
                    return True
                continue
            if self._block_area(block) >= 0.10 or float(block.w or 0.0) >= 0.38 or float(block.h or 0.0) >= 0.22:
                return True
        return False

    def _large_region_count(self, blocks: List[FreeformBlock]) -> int:
        count = 0
        for block in list(blocks or []):
            block_type = str(block.type or "").strip().lower()
            if block_type == "group":
                if self._styled_container(block) and (
                    self._block_area(block) >= 0.08 or float(block.w or 0.0) >= 0.32 or float(block.h or 0.0) >= 0.18
                ):
                    count += 1
                count += self._large_region_count(list(block.children or []))
                continue
            if self._block_area(block) >= 0.08 or float(block.w or 0.0) >= 0.32 or float(block.h or 0.0) >= 0.18:
                count += 1
        return count

    def _small_region_count(self, blocks: List[FreeformBlock]) -> int:
        count = 0
        for block in list(blocks or []):
            block_type = str(block.type or "").strip().lower()
            if block_type == "group":
                count += self._small_region_count(list(block.children or []))
                continue
            if block_type == "line":
                continue
            area = self._block_area(block)
            if 0.0 < area < 0.045:
                count += 1
        return count

    def _text_geometry_issues(self, blocks: List[FreeformBlock]) -> List[str]:
        issues: List[str] = []
        for block in list(blocks or []):
            block_type = str(block.type or "").strip().lower()
            if block_type == "group":
                issues.extend(self._text_geometry_issues(list(block.children or [])))
                continue
            if block_type != "text_box":
                continue
            content = str(block.content or "").strip()
            if not content:
                continue
            style = dict(block.style or {})
            try:
                font_size = float(style.get("font_size")) if style.get("font_size") not in (None, "") else None
            except Exception:
                font_size = None
            min_w, min_h = text_geometry_requirements(content, font_size=font_size)
            if float(block.w or 0.0) < min_w:
                issues.append("text_box_too_narrow")
            if float(block.h or 0.0) < min_h:
                issues.append("text_box_too_short")
        return issues

    def _non_text_zero_geometry_count(self, blocks: List[FreeformBlock]) -> int:
        count = 0
        for block in list(blocks or []):
            block_type = str(block.type or "").strip().lower()
            if block_type == "group":
                count += self._non_text_zero_geometry_count(list(block.children or []))
                continue
            if block_type in {"rectangle", "circle", "image", "chart"} and (
                float(block.w or 0.0) <= 0.0 or float(block.h or 0.0) <= 0.0
            ):
                count += 1
        return count

    def _sparse_diagram_pattern(self, blocks: List[FreeformBlock]) -> bool:
        return self._line_count(blocks) >= 2 and self._large_region_count(blocks) == 0 and self._page_occupancy(blocks) < 0.22

    def _fragmented_framework_pattern(self, blocks: List[FreeformBlock]) -> bool:
        return self._large_region_count(blocks) == 0 and self._small_region_count(blocks) >= 4 and self._page_occupancy(blocks) < 0.24

    def _page_layout_budget(self, page_brief: PageBrief) -> Dict[str, Any]:
        return {
            "max_primary_regions": 2,
            "max_supporting_regions": 6,
            "max_text_boxes": 10,
            "max_body_lines_per_region": 4,
            "min_body_width": 0.24,
            "min_body_height": 0.10,
            "headline_width": 0.70,
            "prefer_full_width_for_long_text": True,
        }

    def _layout_budget_brief(self, page_brief: PageBrief) -> str:
        budget = self._page_layout_budget(page_brief)
        return (
            "Layout budget: "
            f"max_primary_regions={budget['max_primary_regions']}; "
            f"max_supporting_regions={budget['max_supporting_regions']}; "
            f"max_text_boxes={budget['max_text_boxes']}; "
            f"max_body_lines_per_region={budget['max_body_lines_per_region']}; "
            f"min_body_width={budget['min_body_width']:.2f}; "
            f"min_body_height={budget['min_body_height']:.2f}; "
            f"headline_width>={budget['headline_width']:.2f}; "
            f"prefer_full_width_for_long_text={str(bool(budget['prefer_full_width_for_long_text'])).lower()}."
        )

    def _page_strategy_guidance(self, page_brief: PageBrief) -> str:
        assigned_id = str(page_brief.layout_archetype_id or "").strip()
        if not assigned_id:
            raise ValueError(f"page {page_brief.page_id} has no MOVO layout assignment")
        spec = archetype_by_id(assigned_id)
        profile = str(getattr(page_brief, "validation_profile", "") or "").strip().lower()
        intent = str(getattr(page_brief, "composition_intent", "") or getattr(page_brief, "visual_intent", "") or "").strip()
        guidance: List[str] = [
            f"MOVO assigned layout archetype '{spec.archetype_id}' in family '{spec.family}'.",
            spec.prompt_brief,
            "Required structure: " + " | ".join(spec.must_do),
            "Avoid: " + (" | ".join(spec.must_avoid) if spec.must_avoid else "No additional archetype-specific restrictions."),
            "The deck visual director selected this archetype. Treat it as the structural grammar while freely composing coordinates, proportions, typography, colors, icons, and decoration.",
            f"Write layout_type exactly as '{spec.archetype_id}'.",
            self._layout_budget_brief(page_brief),
            "First make the page geometrically solid: readable text containers, a clear primary anchor, and occupied space. Only then add decorative refinement.",
            "Do not let important copy live in edge strips, narrow micro-columns, or isolated labels. If space becomes tight, merge blocks and simplify the composition.",
        ]
        if profile in {"introduce_topic", "ask_for_decision", "close_gratitude"}:
            guidance.append(
                "This page needs one large dominant panel, slab, or headline region. Do not scatter the message across multiple equal-weight islands."
            )
        if profile in {"show_architecture", "show_roadmap", "process_diagram"} or any(
            token in intent for token in ("架构", "路线", "流程", "阶段", "roadmap", "architecture", "process", "timeline")
        ):
            guidance.append(
                "If you use layers, steps, or connectors, place them inside substantial containers or bands. Lines and nodes alone cannot be the main occupied area."
            )
        if profile in {"frame_problem", "show_metrics", "introduce_topic"} or any(
            token in intent for token in ("矩阵", "框架", "总结", "治理", "决策", "matrix", "framework", "summary", "governance")
        ):
            guidance.append(
                "For abstract frameworks, consolidate the logic into one or two strong regions. Avoid many small detached boxes that leave the page feeling like a sketch."
            )
        return " ".join(guidance)

    def _collect_block_ids(self, blocks: List[FreeformBlock]) -> Set[str]:
        ids: Set[str] = set()
        for block in list(blocks or []):
            block_id = str(block.id or "").strip()
            if block_id:
                ids.add(block_id)
            if block.children:
                ids.update(self._collect_block_ids(list(block.children or [])))
        return ids

    def _layout_signature(self, page: FreeformPageBlueprint) -> str:
        block_types = [str(block.type or "").strip().lower() for block in list(page.blocks or [])[:8]]
        large_blocks = sum(1 for block in list(page.blocks or []) if self._block_area(block) >= 0.12)
        group_count = sum(1 for block in list(page.blocks or []) if str(block.type or "").strip().lower() == "group")
        line_count = sum(1 for block in list(page.blocks or []) if str(block.type or "").strip().lower() == "line")
        design = str(page.design_intent or "").strip()
        return (
            f"layout_type={str(page.layout_type or '').strip()}|design_intent={design}|blocks={','.join(block_types)}"
            f"|groups={group_count}|lines={line_count}|large={large_blocks}"
        )

    def _prior_page_summaries(self, pages: List[FreeformPageBlueprint], briefs: Dict[str, PageBrief]) -> List[Dict[str, Any]]:
        summaries: List[Dict[str, Any]] = []
        for page in pages[-3:]:
            brief = briefs.get(str(page.page_id or "").strip())
            summaries.append(
                {
                    "page_id": page.page_id,
                    "key_takeaway": getattr(brief, "key_takeaway", ""),
                    "composition_intent": getattr(brief, "composition_intent", ""),
                    "layout_signature": self._layout_signature(page),
                }
            )
        return summaries

    def _page_system_prompt(self, *, repair_mode: bool) -> str:
        # The former prompt mandated a reusable card component recipe for every
        # region. Keep generation centered on one holistic editorial composition.
        return build_page_composition_prompt(repair_mode=repair_mode)

    async def _compose_page(
        self,
        *,
        deck_brief: DeckBrief,
        constraint_bundle: ConstraintBundle,
        page_brief: PageBrief,
        previous_page: PageBrief | None,
        next_page: PageBrief | None,
        prior_pages: List[FreeformPageBlueprint],
        repair_issues: List[str] | None = None,
        existing_page: FreeformPageBlueprint | None = None,
        repair_brief_text: str | None = None,
        visual_defects: List[Dict[str, Any]] | None = None,
        screenshot_b64: str | None = None,
        screenshot_mime: str = "image/jpeg",
        lock_blocks: bool = True,
        layout_attempt: int = 0,
        deck_visual_plan: DeckVisualPlan | None = None,
    ) -> FreeformPageBlueprint:
        brief_by_id = {str(item.page_id or "").strip(): item for item in list(deck_brief.page_briefs or [])}
        generation_context = PageGenerationContext(
            deck_brief=deck_brief,
            current_page=page_brief,
            previous_page=previous_page,
            next_page=next_page,
            prior_page_summaries=self._prior_page_summaries(prior_pages, brief_by_id),
        )
        logger.info(
            "presentation_page_rule_strategy page_id=%s mode=movo_assigned archetype=%s",
            str(page_brief.page_id or "").strip(),
            str(page_brief.layout_archetype_id or "").strip(),
        )
        visual_plan = deck_visual_plan or fallback_deck_visual_plan(deck_brief)
        payload = build_page_composition_payload(
            deck_brief=deck_brief,
            page_brief=page_brief,
            constraint_bundle=constraint_bundle,
            visual_plan=visual_plan,
            recent_pages=generation_context.prior_page_summaries,
        )
        theme_reference = self._theme_reference_markdown(deck_brief.theme_factory_name)
        if theme_reference:
            payload["deck_context"]["theme_reference"] = theme_reference[:4000]
        payload["page_strategy_brief"] = self._page_strategy_guidance(page_brief)
        if repair_issues:
            payload["repair_brief"] = repair_brief_text or (
                "This page had problems in the last attempt. "
                f"Fix these issues while keeping creativity: {', '.join(list(repair_issues))}"
            )
        if existing_page is not None:
            # Provide full page structure for targeted repair so the model can edit
            # concrete block geometry/content instead of guessing from a summary.
            payload["existing_page_blocks"] = [
                block.model_dump()
                for block in list(existing_page.blocks or [])
            ]
            payload["existing_page_meta"] = {
                "page_id": str(existing_page.page_id or "").strip(),
                "layout_type": str(existing_page.layout_type or "").strip(),
                "page_title": str(existing_page.page_title or "").strip(),
                "page_subtitle": str(existing_page.page_subtitle or "").strip(),
                "design_intent": str(existing_page.design_intent or "").strip(),
            }
            payload["existing_page_summary"] = (
                f"Existing page summary: id={existing_page.page_id}; layout={existing_page.layout_type}; "
                f"block_count={len(list(existing_page.blocks or []))}; design_intent={existing_page.design_intent}."
            )
            logger.warning(
                "presentation_repair_payload page_id=%s blocks_count=%s sample_block_ids=%s",
                str(existing_page.page_id or "").strip() or str(page_brief.page_id or "").strip(),
                len(list(existing_page.blocks or [])),
                [
                    str(b.id or "").strip()
                    for b in list(existing_page.blocks or [])[:8]
                    if str(b.id or "").strip()
                ],
            )

        # Visual-defect-driven targeted repair: pass the structured defects from
        # multimodal QC plus the rendered screenshot so the repair LLM has the
        # same spatial grounding the QC LLM had. The set of "editable" block ids
        # is derived from the defects themselves; everything else is locked.
        invoke_images: list[dict] | None = None
        if visual_defects:
            normalized_defects: List[Dict[str, Any]] = []
            editable_ids: List[str] = []
            seen_ids: Set[str] = set()
            for raw_defect in list(visual_defects or []):
                if not isinstance(raw_defect, dict):
                    continue
                ids = [str(x).strip() for x in list(raw_defect.get("block_ids") or []) if str(x).strip()]
                kind = str(raw_defect.get("kind") or "other").strip() or "other"
                severity = str(raw_defect.get("severity") or "medium").strip() or "medium"
                note = str(raw_defect.get("note") or "").strip()
                if not ids and not note:
                    continue
                normalized_defects.append({
                    "block_ids": ids,
                    "kind": kind,
                    "severity": severity,
                    "note": note,
                })
                for bid in ids:
                    if bid not in seen_ids:
                        seen_ids.add(bid)
                        editable_ids.append(bid)
            if normalized_defects:
                payload["visual_defects"] = normalized_defects
                if lock_blocks:
                    payload["editable_block_ids"] = editable_ids
                else:
                    payload["rewrite_mode"] = True
                    payload["rewrite_instruction"] = (
                        "REWRITE MODE — the previous page version listed in `existing_page_blocks` "
                        "FAILED visual QC and is shown to you only as a REJECTED REFERENCE. "
                        "Do NOT preserve its block ids, layout, or coordinates. "
                        "Generate a NEW design from the page brief that AVOIDS the listed defects, "
                        "while keeping the page's narrative intent and key takeaway intact. "
                        "Keep MOVO's assigned layout archetype while changing the concrete geometry "
                        "and block arrangement enough to eliminate the rejected defects."
                    )
                payload["coordinate_system_note"] = (
                    "Block coordinates (x,y,w,h) are normalized to [0,1] relative to the page. "
                    "The attached screenshot is a render of the same page in the same coordinate frame. "
                    "Use the image to localize defects spatially; use the JSON to edit them precisely."
                )
                logger.warning(
                    "presentation_repair_visual_defects page_id=%s defect_count=%s editable_block_ids=%s",
                    str(existing_page.page_id or "").strip() if existing_page else str(page_brief.page_id or "").strip(),
                    len(normalized_defects),
                    editable_ids[:16],
                )
        if screenshot_b64:
            invoke_images = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{screenshot_mime};base64,{screenshot_b64}",
                    },
                }
            ]
            logger.warning(
                "presentation_repair_screenshot_attached page_id=%s mime=%s bytes_b64=%s",
                str(existing_page.page_id or "").strip() if existing_page else str(page_brief.page_id or "").strip(),
                screenshot_mime,
                len(screenshot_b64),
            )

        system_prompt = self._page_system_prompt(repair_mode=bool(repair_issues))
        logger.info(
            "presentation_page_compose_prompt page_id=%s repair_mode=%s strategy=unified_prompt prompt_logging=summary_only payload_keys=%s has_image=%s",
            str(page_brief.page_id or "").strip(),
            bool(repair_issues),
            sorted(list(payload.keys())),
            bool(invoke_images),
        )
        _log_page_compose_grounding_dump(
            page_id=str(page_brief.page_id or "").strip(),
            bundle=constraint_bundle,
        )

        authored_page = await invoke_structured(
            model_cls=_MovLayoutPageResponse,
            system_prompt=system_prompt,
            payload=payload,
            stage="presentation_page_compose",
            intent="generation",
            images=invoke_images,
        )
        page = ComposerPageBlueprint.model_validate(authored_page.model_dump())
        page.page_id = str(page.page_id or page_brief.page_id).strip() or str(page_brief.page_id).strip()
        if not page.page_title:
            page.page_title = str(page_brief.key_takeaway or page_brief.page_goal or "").strip()
        if not page.page_subtitle:
            page.page_subtitle = str(page_brief.page_goal or "").strip()
        if not page.design_intent:
            page.design_intent = str(page_brief.visual_intent or page_brief.composition_intent or "").strip()
        expected_layout = str(page_brief.layout_archetype_id or "").strip()
        # layout_type is MOVO-owned metadata. The model designs within the
        # assigned structure but cannot override the deck-level decision.
        page.layout_type = expected_layout
        issues = layout_conformance_issues(page, expected_archetype_id=expected_layout)
        if issues:
            logger.warning(
                "presentation_layout_conformance_failed page_id=%s expected=%s actual=%s attempt=%s issues=%s blocks=%s",
                str(page_brief.page_id or "").strip(),
                expected_layout,
                str(page.layout_type or "").strip(),
                layout_attempt,
                issues,
                [
                    {
                        "id": str(block.id or "").strip(),
                        "type": str(block.type or "").strip(),
                        "x": float(block.x or 0.0),
                        "y": float(block.y or 0.0),
                        "w": float(block.w or 0.0),
                        "h": float(block.h or 0.0),
                        "children": len(list(block.children or [])),
                        "has_content": bool(str(block.content or "").strip()),
                    }
                    for block in list(page.blocks or [])[:12]
                ],
            )
            # Conformance is diagnostic only. Retrying a whole page because a
            # coarse archetype heuristic disagrees causes duplicate generation
            # and often replaces a stronger original composition with a generic
            # fallback. Schema and renderer safety checks still protect output.
        return page

    async def build(
        self,
        *,
        story_plan: StoryDeckPlan,
        request_context: Dict[str, Any] | None = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]] = None,
    ) -> FreeformDeckBlueprint:
        messages = list((request_context or {}).get("messages") or [])
        output_spec = dict((request_context or {}).get("output_spec") or {})
        logger.info(
            "presentation_deck_build_start deck_id=%s page_count=%s audience=%s",
            str(story_plan.deck_id or "").strip(),
            len(list(story_plan.pages or [])),
            str(story_plan.target_audience or "").strip(),
        )
        user_outline = self._extract_user_outline(messages=messages, output_spec=output_spec)
        generation_guidance = self._extract_generation_guidance(messages=messages, output_spec=output_spec)
        user_message_context = self._extract_message_text(messages)
        constraint_bundle = self._brief_compiler.build_constraint_bundle(
            output_spec=output_spec,
            user_outline=user_outline,
            user_generation_guidance=generation_guidance,
            user_message_context=user_message_context,
        )
        deck_brief = await self._build_deck_brief(
            story_plan=story_plan,
            constraint_bundle=constraint_bundle,
            user_message_context=user_message_context,
        )
        deck_brief = self._resolve_deck_theme(deck_brief, constraint_bundle=constraint_bundle)
        deck_brief = self._layout_planner.assign(deck_brief, story_plan)
        logger.info(
            "presentation_deck_brief_ready deck_id=%s page_count=%s",
            str(deck_brief.deck_id or "").strip(),
            len(list(deck_brief.page_briefs or [])),
        )
        await self._emit_progress(
            progress_callback,
            {
                "stage": "deck_planning",
                "status": "running",
                "kind": "analyze",
                "message": "正在规划PPT结构",
            },
        )
        await self._emit_progress(
            progress_callback,
            {
                "stage": "visual_direction",
                "status": "running",
                "kind": "analyze",
                "message": "正在规划PPT视觉语言",
            },
        )
        deck_visual_plan = await self._visual_director.plan(
            deck_brief=deck_brief,
            story_plan=story_plan,
        )
        deck_brief = self._visual_director.apply_layout_recommendations(
            deck_brief=deck_brief,
            visual_plan=deck_visual_plan,
        )

        built_pages: List[FreeformPageBlueprint] = []
        repair_reports: List[PageRepairReport] = []
        page_briefs_list = list(deck_brief.page_briefs or [])
        for idx, page_brief in enumerate(page_briefs_list):
            page_label = self._progress_page_label(page_brief, idx + 1)
            page_description = self._progress_page_description(page_brief, page_label)
            progress_message = f"正在生成第{idx + 1}页：{page_label}"
            if page_description:
                progress_message = f"{progress_message}\n{page_description}"
            await self._emit_progress(
                progress_callback,
                {
                    "stage": "page_generation",
                    "status": "running",
                    "kind": "write",
                    "page_index": idx + 1,
                    "page_total": len(page_briefs_list),
                    "page_id": str(page_brief.page_id or "").strip(),
                    "page_label": page_label,
                    "page_description": page_description,
                    "message": progress_message,
                },
            )
            previous_brief = page_briefs_list[idx - 1] if idx > 0 else None
            next_brief = page_briefs_list[idx + 1] if idx + 1 < len(page_briefs_list) else None
            page = await self._compose_page(
                deck_brief=deck_brief,
                constraint_bundle=constraint_bundle,
                page_brief=page_brief,
                previous_page=previous_brief,
                next_page=next_brief,
                prior_pages=built_pages,
                deck_visual_plan=deck_visual_plan,
            )
            report = PageRepairReport(
                page_id=page.page_id,
                issues=[],
                accepted=True,
                attempt_count=1,
                issue_score_before=0,
                issue_score_after=0,
            )
            built_pages.append(page)
            repair_reports.append(report)
            logger.info(
                "presentation_page_ready page_id=%s layout_type=%s block_count=%s",
                str(page.page_id or "").strip(),
                str(page.layout_type or "").strip(),
                len(list(page.blocks or [])),
            )

        # Deck-level coherence review and per-page repair loops have been
        # removed: the LLM's first-shot pages are trusted as-is.
        blueprint = FreeformDeckBlueprint(
            deck_id=str(deck_brief.deck_id or story_plan.deck_id or "presentation").strip() or "presentation",
            deck_goal=str(deck_brief.deck_goal or story_plan.deck_goal or "").strip(),
            target_audience=str(deck_brief.target_audience or story_plan.target_audience or "").strip(),
            theme=build_freeform_theme_from_design_tokens(deck_brief.design_tokens),
            pages=built_pages,
        )
        actual_layout_distribution: Dict[str, int] = {}
        for built_page in built_pages:
            layout_id = str(built_page.layout_type or "").strip()
            actual_layout_distribution[layout_id] = actual_layout_distribution.get(layout_id, 0) + 1
        logger.info(
            "presentation_layout_distribution_actual deck_id=%s distribution=%s",
            str(blueprint.deck_id or "").strip(),
            dict(sorted(actual_layout_distribution.items())),
        )
        blueprint.runtime = {
            "source": "presentation_deck_visual_direction_page_compose",
            "story_outline": json.dumps(self._story_payload(story_plan=story_plan), ensure_ascii=False),
            "deck_brief": deck_brief.model_dump(),
            "deck_visual_plan": deck_visual_plan.model_dump(),
            "planned_layout_distribution": dict(deck_brief.layout_distribution or {}),
            "layout_distribution": dict(sorted(actual_layout_distribution.items())),
            "constraint_bundle": constraint_bundle.model_dump(),
            "repair_reports": [report.model_dump() for report in repair_reports],
        }
        # ── Sequential page_id renumbering ────────────────────────────────
        # LLM often produces non-sequential IDs (p01, p04, p08...) which
        # confuses downstream consumers. Renumber to page_01..page_N.
        blueprint = self._renumber_pages(blueprint)

        logger.info(
            "presentation_deck_build_done deck_id=%s page_count=%s",
            str(blueprint.deck_id or "").strip(),
            len(list(blueprint.pages or [])),
        )
        return blueprint

    def _renumber_pages(self, blueprint: FreeformDeckBlueprint) -> FreeformDeckBlueprint:
        """Renumber page_ids to sequential page_01, page_02, ... page_N."""
        out = blueprint.model_copy(deep=True)
        pages = list(out.pages or [])
        id_map: Dict[str, str] = {}
        for idx, page in enumerate(pages):
            old_id = str(page.page_id or "").strip()
            new_id = f"page_{idx + 1:02d}"
            id_map[old_id] = new_id
            page.page_id = new_id

        # Update repair_reports and deck_review references in runtime
        runtime = dict(out.runtime or {})
        for report in list(runtime.get("repair_reports") or []):
            if isinstance(report, dict) and report.get("page_id") in id_map:
                report["page_id"] = id_map[report["page_id"]]
        deck_brief = runtime.get("deck_brief")
        if isinstance(deck_brief, dict):
            for brief in list(deck_brief.get("page_briefs") or []):
                if isinstance(brief, dict) and brief.get("page_id") in id_map:
                    brief["page_id"] = id_map[brief["page_id"]]
        visual_plan = runtime.get("deck_visual_plan")
        if isinstance(visual_plan, dict):
            for direction in list(visual_plan.get("page_directions") or []):
                if isinstance(direction, dict) and direction.get("page_id") in id_map:
                    direction["page_id"] = id_map[direction["page_id"]]
        review = runtime.get("deck_review")
        if isinstance(review, dict):
            for note in list(review.get("notes") or []):
                if isinstance(note, dict) and note.get("page_id") in id_map:
                    note["page_id"] = id_map[note["page_id"]]
        out.runtime = runtime
        out.pages = pages
        return out

    async def rebuild_failed_pages(
        self,
        *,
        blueprint: FreeformDeckBlueprint,
        failed_page_ids: List[str],
    ) -> FreeformDeckBlueprint:
        """Re-compose only the failed pages, keeping all other pages intact.

        Called by the pipeline when the quality gate fails — avoids discarding
        the entire deck and re-generating from scratch.
        """
        runtime = dict(blueprint.runtime or {})
        deck_brief_data = runtime.get("deck_brief")
        constraint_data = runtime.get("constraint_bundle")
        if not isinstance(deck_brief_data, dict) or not isinstance(constraint_data, dict):
            logger.warning("rebuild_failed_pages: missing runtime context, cannot rebuild")
            return blueprint

        try:
            deck_brief = DeckBrief.model_validate(deck_brief_data)
            constraint_bundle = ConstraintBundle.model_validate(constraint_data)
            visual_plan_data = runtime.get("deck_visual_plan")
            deck_visual_plan = (
                DeckVisualPlan.model_validate(visual_plan_data)
                if isinstance(visual_plan_data, dict)
                else fallback_deck_visual_plan(deck_brief)
            )
        except Exception:
            logger.warning("rebuild_failed_pages: invalid runtime context", exc_info=True)
            return blueprint

        brief_by_id = {str(pb.page_id or "").strip(): pb for pb in list(deck_brief.page_briefs or [])}
        page_index_by_id = {str(p.page_id or "").strip(): i for i, p in enumerate(list(blueprint.pages or []))}
        pages = list(blueprint.pages or [])
        all_briefs = list(deck_brief.page_briefs or [])

        for page_id in failed_page_ids:
            idx = page_index_by_id.get(page_id)
            if idx is None:
                logger.warning("presentation_rebuild_page_skip page_id=%s reason=page_not_found", page_id)
                continue
            page_brief = brief_by_id.get(page_id)
            if page_brief is None and 0 <= idx < len(all_briefs):
                page_brief = all_briefs[idx]
            if page_brief is None:
                logger.warning("presentation_rebuild_page_skip page_id=%s reason=brief_not_found", page_id)
                continue
            logger.info("presentation_rebuild_page page_id=%s", page_id)
            prior_pages = [p for i, p in enumerate(pages) if i != idx]
            previous_brief = all_briefs[idx - 1] if idx > 0 else None
            next_brief = all_briefs[idx + 1] if idx + 1 < len(all_briefs) else None
            try:
                new_page = await self._compose_page(
                    deck_brief=deck_brief,
                    constraint_bundle=constraint_bundle,
                    page_brief=page_brief,
                    previous_page=previous_brief,
                    next_page=next_brief,
                    prior_pages=prior_pages,
                    deck_visual_plan=deck_visual_plan,
                )
                pages[idx] = new_page
                logger.info("presentation_rebuild_page_done page_id=%s", page_id)
            except Exception:
                logger.warning(
                    "presentation_rebuild_page_failed page_id=%s (keeping original)",
                    page_id, exc_info=True,
                )

        rebuilt = blueprint.model_copy(deep=True)
        rebuilt.pages = pages
        return rebuilt
    async def _emit_progress(
        self,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]],
        payload: Dict[str, Any],
    ) -> None:
        if progress_callback is None:
            return
        result = progress_callback(dict(payload or {}))
        if inspect.isawaitable(result):
            await result

    @staticmethod
    def _progress_page_label(page_brief: PageBrief, index: int) -> str:
        def _normalize_label(raw: str) -> str:
            text = str(raw or "").strip()
            if not text:
                return ""
            # Strip outline metadata artifacts, e.g.:
            # "1. 第1页：什么是大模型？ | purpose=..."
            text = re.sub(r"\s*\|\s*purpose\s*=.*$", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*\|\s*topics\s*=.*$", "", text, flags=re.IGNORECASE)
            text = re.sub(r"^\s*\d+\s*[\.、]\s*", "", text)
            text = re.sub(r"^\s*第\s*\d+\s*页\s*[:：\-—]\s*", "", text)
            text = re.sub(r"^\s*page\s*\d+\s*[:：\-—]\s*", "", text, flags=re.IGNORECASE)
            return text.strip()

        page_type = str(page_brief.page_type or "").strip().lower()
        outline = _normalize_label(str(page_brief.source_outline_section or ""))
        key_takeaway = _normalize_label(str(page_brief.key_takeaway or ""))
        visual_center = _normalize_label(str(page_brief.visual_center or ""))
        if page_type == "cover":
            return "封面"
        if page_type == "thank_you":
            return "结束页"
        for candidate in (key_takeaway, outline, visual_center):
            if candidate:
                return candidate.rstrip("：:，,。.;；")
        return f"第{index}页"

    @staticmethod
    def _progress_page_description(page_brief: PageBrief, page_label: str) -> str:
        description = str(page_brief.page_goal or "").strip()
        if not description or description == str(page_label or "").strip():
            return ""
        return description
