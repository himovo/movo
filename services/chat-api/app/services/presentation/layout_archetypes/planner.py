from __future__ import annotations

import logging
import re
from collections import Counter

from app.services.presentation.contracts import DeckBrief, PageBrief, StoryDeckPlan, StoryPageSpec

from .catalog import ARCHETYPE_CATALOG, archetype_by_id
from .contracts import LayoutArchetypeSpec


logger = logging.getLogger(__name__)

# Data layouts must be grounded by explicit data language or an actual number.
# Generic outcome verbs such as “提升/降低” are qualitative and must not force
# the composer to invent KPI values merely to satisfy a dashboard archetype.
_DATA_TOKENS = ("指标", "数据", "kpi", "roi", "metric", "data", "%")
_COMPARISON_TOKENS = ("对比", "差异", "优劣", "之前", "之后", "现状", "目标", "compare", "versus", "before", "after", " vs ")
_SEQUENCE_TOKENS = ("步骤", "阶段", "流程", "路线", "时间", "演进", "里程碑", "journey", "process", "roadmap", "timeline", "maturity")
_IMAGE_TOKENS = ("图片", "视觉", "截图", "案例", "场景", "客户故事", "image", "visual", "screenshot", "case", "scenario")

_SPECIAL_LAYOUTS = {
    "cover": "full_bleed_visual",
    "agenda": "sidebar_toc",
    "section_divider": "hero_statement",
    "thank_you": "accent_callout",
}


class LayoutAssignmentPlanner:
    """Deterministically assigns MOVO layout archetypes before page composition."""

    def assign(self, deck_brief: DeckBrief, story_plan: StoryDeckPlan) -> DeckBrief:
        resolved = deck_brief.model_copy(deep=True)
        stories = {str(page.page_id or "").strip(): page for page in list(story_plan.pages or [])}
        id_usage: Counter[str] = Counter()
        family_usage: Counter[str] = Counter()
        previous_id = ""
        previous_family = ""

        for page in list(resolved.page_briefs or []):
            story = stories.get(str(page.page_id or "").strip())
            chosen, rationale = self._choose(
                page,
                story,
                id_usage=id_usage,
                family_usage=family_usage,
                previous_id=previous_id,
                previous_family=previous_family,
            )
            page.layout_archetype_id = chosen.archetype_id
            page.layout_family = chosen.family
            page.layout_rationale = rationale
            page.layout_constraints = chosen.prompt_payload()
            id_usage[chosen.archetype_id] += 1
            family_usage[chosen.family] += 1
            previous_id = chosen.archetype_id
            previous_family = chosen.family
            logger.info(
                "presentation_layout_assignment page_id=%s archetype=%s family=%s rationale=%s",
                str(page.page_id or "").strip(),
                chosen.archetype_id,
                chosen.family,
                rationale,
            )

        resolved.layout_distribution = dict(sorted(id_usage.items()))
        logger.info(
            "presentation_layout_distribution deck_id=%s distribution=%s families=%s",
            str(resolved.deck_id or "").strip(),
            dict(sorted(id_usage.items())),
            dict(sorted(family_usage.items())),
        )
        return resolved

    def _choose(
        self,
        page: PageBrief,
        story: StoryPageSpec | None,
        *,
        id_usage: Counter[str],
        family_usage: Counter[str],
        previous_id: str,
        previous_family: str,
    ) -> tuple[LayoutArchetypeSpec, str]:
        page_type = str((story.page_type if story else page.page_type) or "content").strip().lower()
        forced_id = _SPECIAL_LAYOUTS.get(page_type)
        if forced_id:
            selected = archetype_by_id(forced_id)
            return selected, f"special_page_type:{page_type}"

        page_intent = str((story.page_intent if story else page.validation_profile) or "").strip().lower()
        text = self._semantic_text(page, story)
        item_count = max(len(list(page.must_include or [])), len(list(page.must_visualize or [])), 1)
        signals = {
            "data": self._contains(text, _DATA_TOKENS) or bool(re.search(r"\d", text)),
            "comparison": self._contains(text, _COMPARISON_TOKENS),
            "sequence": self._contains(text, _SEQUENCE_TOKENS),
            "image": self._contains(text, _IMAGE_TOKENS),
        }
        compatible = [
            spec for spec in ARCHETYPE_CATALOG
            if self._compatible(spec, page_type=page_type, signals=signals)
        ]
        if not compatible:
            compatible = [archetype_by_id("dominant_panel")]

        # A third use is permitted only when semantics leave no alternative.
        below_cap = [spec for spec in compatible if id_usage[spec.archetype_id] < 2]
        if below_cap:
            compatible = below_cap
        non_adjacent = [spec for spec in compatible if spec.archetype_id != previous_id]
        if non_adjacent:
            compatible = non_adjacent

        scored = [
            (
                self._score(
                    spec,
                    page_intent=page_intent,
                    text=text,
                    item_count=item_count,
                    id_usage=id_usage,
                    family_usage=family_usage,
                    previous_family=previous_family,
                ),
                -index,
                spec,
            )
            for index, spec in enumerate(compatible)
        ]
        score, _, selected = max(scored, key=lambda item: (item[0], item[1]))
        matched_keywords = [keyword for keyword in selected.keywords if keyword.lower() in text][:3]
        rationale = (
            f"intent={page_intent or 'unspecified'};score={score};"
            f"signals={','.join(key for key, enabled in signals.items() if enabled) or 'none'};"
            f"keywords={','.join(matched_keywords) or 'none'};prior_family={previous_family or 'none'}"
        )
        return selected, rationale

    @staticmethod
    def _semantic_text(page: PageBrief, story: StoryPageSpec | None) -> str:
        values = [
            page.page_goal,
            page.key_takeaway,
            page.visual_intent,
            page.composition_intent,
            page.dominant_move,
            " ".join(list(page.must_include or [])),
            " ".join(list(page.must_visualize or [])),
        ]
        if story is not None:
            # page_intent is scored separately. Mixing labels such as
            # ``show_metrics`` into semantic copy fabricates a data signal even
            # when the page contains no grounded metric or number.
            values.extend([story.communication_goal, story.key_message, story.visual_intent])
        return " ".join(str(value or "").strip().lower() for value in values if str(value or "").strip())

    @staticmethod
    def _contains(text: str, tokens: tuple[str, ...]) -> bool:
        return any(token in text for token in tokens)

    @staticmethod
    def _compatible(spec: LayoutArchetypeSpec, *, page_type: str, signals: dict[str, bool]) -> bool:
        if page_type not in spec.page_types:
            return False
        if spec.requires_data and not signals["data"]:
            return False
        if spec.requires_comparison and not signals["comparison"]:
            return False
        if spec.requires_sequence and not signals["sequence"]:
            return False
        if spec.requires_image and not signals["image"]:
            return False
        return True

    @staticmethod
    def _score(
        spec: LayoutArchetypeSpec,
        *,
        page_intent: str,
        text: str,
        item_count: int,
        id_usage: Counter[str],
        family_usage: Counter[str],
        previous_family: str,
    ) -> int:
        score = 0
        if spec.archetype_id in text:
            score += 500
        if page_intent in spec.page_intents:
            score += 42
        score += min(48, sum(12 for keyword in spec.keywords if keyword.lower() in text))
        if spec.min_content_items <= item_count <= spec.max_content_items:
            score += 8
        if id_usage[spec.archetype_id] == 0:
            score += 18
        score -= id_usage[spec.archetype_id] * 28
        score -= family_usage[spec.family] * 5
        if spec.family == previous_family:
            score -= 24
        return score


__all__ = ["LayoutAssignmentPlanner"]
