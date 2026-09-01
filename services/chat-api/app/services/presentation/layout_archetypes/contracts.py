from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class LayoutArchetypeSpec:
    archetype_id: str
    family: str
    page_types: FrozenSet[str]
    page_intents: FrozenSet[str]
    keywords: tuple[str, ...]
    prompt_brief: str
    must_do: tuple[str, ...]
    must_avoid: tuple[str, ...]
    min_content_items: int = 0
    max_content_items: int = 99
    requires_data: bool = False
    requires_comparison: bool = False
    requires_sequence: bool = False
    requires_image: bool = False

    def prompt_payload(self) -> dict[str, object]:
        return {
            "archetype_id": self.archetype_id,
            "family": self.family,
            "design_brief": self.prompt_brief,
            "must_do": list(self.must_do),
            "must_avoid": list(self.must_avoid),
            "freedom": [
                "Choose exact coordinates, proportions, typography, colors, icons, and decoration.",
                "Keep the assigned structural archetype while composing an original page.",
            ],
        }


__all__ = ["LayoutArchetypeSpec"]
