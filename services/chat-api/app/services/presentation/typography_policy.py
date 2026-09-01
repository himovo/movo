from __future__ import annotations

from typing import Any, Dict


class PresentationTypographyPolicy:
    """Projection-readable typography floors for LLM-authored slides.

    Values are CSS pixels on the 1600×900 authoring canvas.  The policy keeps
    explicit hierarchy while preventing a page from silently becoming a 12px
    wireframe.  It does not change copy or geometry.
    """

    _HERO_ROLES = frozenset({"hero_title", "main_title", "cover_title"})
    _HEADLINE_ROLES = frozenset({"title", "headline", "headline_claim", "takeaway"})
    _SECTION_ROLES = frozenset({
        "subtitle", "subtakeaway", "section_title", "subheading",
        "platform_label", "action_packet_title", "summary_title", "phase_label",
    })
    _METRIC_ROLES = frozenset({
        "metric", "metric_value", "outcome_value", "callout_text", "verdict",
    })
    _LABEL_ROLES = frozenset({
        "label", "section_label", "eyebrow", "tag", "meta", "chip_label",
        "value_chip_label", "phase_label", "axis_label",
    })
    _ANNOTATION_HINTS = ("caption", "footnote", "source", "annotation", "eyebrow")

    def apply(self, *, role: str, style: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(style or {})
        normalized_role = str(role or "").strip().lower()
        minimum = self.minimum_size(normalized_role)
        current = self._number(out.get("font_size"))
        if current is None or current < minimum:
            out["font_size"] = minimum
        out.setdefault("line_height", 1.16 if minimum >= 32 else 1.28)
        return out

    def minimum_size(self, role: str) -> int:
        if role in self._HERO_ROLES:
            return 58
        if role in self._HEADLINE_ROLES:
            return 48
        if role in self._SECTION_ROLES:
            return 32
        if role in self._METRIC_ROLES:
            return 36
        if role in self._LABEL_ROLES:
            return 22
        if any(token in role for token in self._ANNOTATION_HINTS):
            return 18
        return 22

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


__all__ = ["PresentationTypographyPolicy"]
