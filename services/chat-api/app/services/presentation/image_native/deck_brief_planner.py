from __future__ import annotations

import logging
from pathlib import Path
import re

from app.services.presentation.brief_compiler import BriefCompiler
from app.services.presentation.contracts import (
    ConstraintBundle,
    DeckBrief,
    DesignTokens,
    PageBrief,
    StoryDeckPlan,
    StoryPageSpec,
)
from app.services.presentation.llm_utils import invoke_structured
from app.services.presentation.theme_factory_catalog import (
    apply_theme_spec_to_design_tokens,
    get_theme_spec_by_slug,
    infer_theme_spec,
    theme_catalog_prompt_text,
)

logger = logging.getLogger(__name__)


class _DeckBriefEnvelope(DeckBrief):
    pass


class DeckBriefPlanner:
    """Build the deck-level brief shared by all image-native pages."""

    def __init__(self) -> None:
        self._brief_compiler = BriefCompiler()

    async def build(
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
            "Build a coherent deck-level plan that preserves user intent and page-to-page continuity.\n"
            "Rules:\n"
            "- Preserve the exact page order and page_id values from the story plan brief.\n"
            "- Respect the user's outline, requested sections, generation ideas, and active skill constraints.\n"
            "- Capture user intent in user_outline, user_generation_guidance, source_outline_section, and source_user_intent.\n"
            "- page_briefs are lightweight page directives, not coordinates or rigid templates.\n"
            "- design_tokens define stable visual constants for the whole deck.\n"
            "- Every page must define goal, key_takeaway, composition_intent, visual_center, dominant_move, must_include, must_avoid, must_visualize, and validation_profile.\n"
            "- Keep the deck coherent while varying neighboring page composition.\n"
            "- Choose one theme_factory_name from the provided catalog and fill its rationale, colors, and typography.\n"
            "- Prefer a strong accent color matched to the content instead of defaulting to gray-only themes.\n"
            "- Output exactly one PageBrief for every story page.\n"
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
            logger.warning(
                "presentation_deck_brief_fallback deck_id=%s",
                str(story_plan.deck_id or "").strip(),
                exc_info=True,
            )
            brief = self._fallback(story_plan=story_plan, constraint_bundle=constraint_bundle)

        by_id = {
            str(item.page_id or "").strip(): item
            for item in list(brief.page_briefs or [])
            if str(item.page_id or "").strip()
        }
        brief.deck_id = str(brief.deck_id or story_plan.deck_id or "presentation").strip() or "presentation"
        brief.deck_goal = str(brief.deck_goal or story_plan.deck_goal or "").strip()
        brief.target_audience = str(brief.target_audience or story_plan.target_audience or "").strip()
        brief.presentation_context = str(brief.presentation_context or story_plan.presentation_context or "").strip()
        brief.language = str(brief.language or story_plan.language or "zh-CN").strip() or "zh-CN"
        brief.page_briefs = [
            by_id.get(str(page.page_id or "").strip())
            or self._default_page_brief(
                page,
                user_outline=constraint_bundle.user_outline,
                generation_guidance=constraint_bundle.user_generation_guidance,
            )
            for page in list(story_plan.pages or [])
        ]
        brief.user_outline = brief.user_outline or constraint_bundle.user_outline
        brief.user_generation_guidance = brief.user_generation_guidance or constraint_bundle.user_generation_guidance
        brief.narrative_arc = brief.narrative_arc or list(story_plan.narrative_outline or [])
        brief.continuity_rules = brief.continuity_rules or [
            "Keep terminology and visual tone consistent across the deck.",
            "Avoid reusing the same composition on adjacent pages.",
            "Honor the user outline and requested flow.",
        ]
        brief.visual_direction = brief.visual_direction or [
            "clean executive presentation",
            "strong page hierarchy",
            "integrated text and graphics",
        ]
        if not isinstance(brief.design_tokens, DesignTokens):
            brief.design_tokens = DesignTokens()
        return brief

    def resolve_theme(self, brief: DeckBrief, *, constraint_bundle: ConstraintBundle) -> DeckBrief:
        resolved = brief.model_copy(deep=True)
        selected = get_theme_spec_by_slug(str(resolved.theme_factory_name or "").strip())
        if selected is None:
            selected = infer_theme_spec(
                deck_goal=str(resolved.deck_goal or "").strip(),
                target_audience=str(resolved.target_audience or "").strip(),
                user_outline=str(constraint_bundle.user_outline or "").strip(),
            )
        resolved.design_tokens = apply_theme_spec_to_design_tokens(
            resolved.design_tokens if isinstance(resolved.design_tokens, DesignTokens) else DesignTokens(),
            selected,
        )
        if selected:
            resolved.theme_factory_name = str(selected.get("slug") or selected.get("name") or "").strip()
            resolved.theme_factory_rationale = resolved.theme_factory_rationale or str(
                selected.get("best_for") or "Selected by topic and audience fit."
            ).strip()
            resolved.theme_factory_colors = dict(selected.get("colors") or {})
            resolved.theme_factory_typography = dict(selected.get("typography") or {})
        return resolved

    @staticmethod
    def theme_reference_markdown(theme_factory_name: str) -> str:
        slug = str(theme_factory_name or "").strip().lower().replace("_", "-").replace(" ", "-")
        if not slug or not re.fullmatch(r"[a-z0-9-]+", slug):
            return ""
        path = Path(__file__).resolve().parents[1] / "theme_factory" / "themes" / f"{slug}.md"
        try:
            return path.read_text(encoding="utf-8").strip()[:8000] if path.exists() else ""
        except Exception:
            return ""

    def _fallback(self, *, story_plan: StoryDeckPlan, constraint_bundle: ConstraintBundle) -> _DeckBriefEnvelope:
        return _DeckBriefEnvelope(
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
                "Vary composition while keeping the same presentation tone.",
                "Honor the user outline and story order exactly.",
            ],
            visual_direction=["business presentation", "clear hierarchy", "strong focal points"],
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

    def _default_page_brief(
        self,
        page: StoryPageSpec,
        *,
        user_outline: str,
        generation_guidance: str,
    ) -> PageBrief:
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
            must_include=[str(page.key_message or "").strip(), str(page.visual_intent or "").strip()],
            must_avoid=["generic report-like text dump", "repeating the same layout as nearby pages"],
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
        lines = [line.strip() for line in re.split(r"[\r\n]+", text) if line.strip()]
        if not lines:
            return text[:400]
        index = max(1, int(page_index or 1)) - 1
        return (lines[index] if index < len(lines) else lines[-1])[:400]


__all__ = ["DeckBriefPlanner"]
