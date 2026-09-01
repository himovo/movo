from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.services.presentation.contracts import DeckBrief, StoryDeckPlan
from app.services.presentation.llm_utils import invoke_structured
from app.services.presentation.layout_archetypes.catalog import ARCHETYPE_CATALOG, archetype_by_id

from .composition_grammar import fallback_deck_visual_plan, fallback_page_direction
from .contracts import DeckVisualPlan, PageVisualDirection
from .prompts import build_deck_visual_direction_prompt

logger = logging.getLogger(__name__)


class DeckVisualDirector:
    """Plans deck rhythm once, before holistic page composition begins."""

    def _payload(self, *, deck_brief: DeckBrief, story_plan: StoryDeckPlan) -> Dict[str, Any]:
        pages: List[Dict[str, Any]] = []
        for page in list(deck_brief.page_briefs or []):
            pages.append({
                "page_id": str(page.page_id or "").strip(),
                "page_index": int(page.page_index or 0),
                "page_type": str(page.page_type or "content").strip(),
                "page_goal": str(page.page_goal or "").strip(),
                "key_takeaway": str(page.key_takeaway or "").strip(),
                "visual_intent": str(page.visual_intent or "").strip(),
                "composition_intent": str(page.composition_intent or "").strip(),
                "must_visualize": list(page.must_visualize or []),
                "assigned_archetype": str(page.layout_archetype_id or "").strip(),
                "layout_family": str(page.layout_family or "").strip(),
            })
        return {
            "deck": {
                "deck_id": str(deck_brief.deck_id or "presentation").strip(),
                "goal": str(deck_brief.deck_goal or story_plan.deck_goal or "").strip(),
                "audience": str(deck_brief.target_audience or story_plan.target_audience or "").strip(),
                "context": str(deck_brief.presentation_context or "").strip(),
                "language": str(deck_brief.language or "zh-CN").strip(),
                "narrative_arc": list(deck_brief.narrative_arc or []),
                "visual_direction": list(deck_brief.visual_direction or []),
                "design_tokens": deck_brief.design_tokens.model_dump(),
            },
            "pages": pages,
            "allowable_archetypes": [
                {"archetype_id": item.archetype_id, "family": item.family, "brief": item.prompt_brief}
                for item in ARCHETYPE_CATALOG
            ],
        }

    def _complete(self, *, candidate: DeckVisualPlan, deck_brief: DeckBrief) -> DeckVisualPlan:
        fallback = fallback_deck_visual_plan(deck_brief)
        candidate_by_id = {
            str(item.page_id or "").strip(): item
            for item in list(candidate.page_directions or [])
            if str(item.page_id or "").strip()
        }
        completed: List[PageVisualDirection] = []
        for page in list(deck_brief.page_briefs or []):
            page_id = str(page.page_id or "").strip()
            direction = candidate_by_id.get(page_id) or fallback_page_direction(page)
            direction.page_id = page_id
            if not direction.region_plan:
                direction.region_plan = fallback_page_direction(page).region_plan
            fallback_direction = fallback_page_direction(page)
            if not str(direction.recommended_archetype or "").strip():
                direction.recommended_archetype = fallback_direction.recommended_archetype
            try:
                archetype_by_id(direction.recommended_archetype)
            except ValueError:
                direction.recommended_archetype = fallback_direction.recommended_archetype
            if not direction.required_visual_elements:
                direction.required_visual_elements = fallback_direction.required_visual_elements
            direction.minimum_visual_blocks = max(1, int(direction.minimum_visual_blocks or 1))
            completed.append(direction)
        candidate.deck_id = str(deck_brief.deck_id or "presentation").strip() or "presentation"
        candidate.page_directions = completed
        if not candidate.design_language:
            candidate.design_language = list(fallback.design_language)
        if not candidate.rhythm_rules:
            candidate.rhythm_rules = list(fallback.rhythm_rules)
        return candidate

    def apply_layout_recommendations(self, *, deck_brief: DeckBrief, visual_plan: DeckVisualPlan) -> DeckBrief:
        """Apply the deck-level visual decision; deterministic assignment remains fallback."""
        out = deck_brief.model_copy(deep=True)
        distribution: Dict[str, int] = {}
        for page in list(out.page_briefs or []):
            direction = visual_plan.for_page(str(page.page_id or "").strip())
            recommended = str(getattr(direction, "recommended_archetype", "") or "").strip()
            try:
                spec = archetype_by_id(recommended)
            except ValueError:
                spec = archetype_by_id(str(page.layout_archetype_id or "dominant_panel").strip())
            page.layout_archetype_id = spec.archetype_id
            page.layout_family = spec.family
            page.layout_rationale = "Selected by the deck visual director; deterministic assignment is the fallback."
            page.layout_constraints = spec.prompt_payload()
            distribution[spec.archetype_id] = distribution.get(spec.archetype_id, 0) + 1
        out.layout_distribution = dict(sorted(distribution.items()))
        return out

    async def plan(self, *, deck_brief: DeckBrief, story_plan: StoryDeckPlan) -> DeckVisualPlan:
        try:
            candidate = await invoke_structured(
                model_cls=DeckVisualPlan,
                system_prompt=build_deck_visual_direction_prompt(),
                payload=self._payload(deck_brief=deck_brief, story_plan=story_plan),
                stage="presentation_deck_visual_direction",
                intent="generation",
            )
            return self._complete(candidate=candidate, deck_brief=deck_brief)
        except Exception:
            logger.warning(
                "presentation_deck_visual_direction_fallback deck_id=%s",
                str(deck_brief.deck_id or "").strip(),
                exc_info=True,
            )
            return fallback_deck_visual_plan(deck_brief)


__all__ = ["DeckVisualDirector"]
