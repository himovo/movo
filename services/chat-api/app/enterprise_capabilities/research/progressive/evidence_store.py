"""Bounded evidence storage independent from research completion semantics."""

from __future__ import annotations

from collections.abc import Iterable

from .models import EvidenceItem


class ResearchEvidenceStore:
    """Keep a bounded, deduplicated working set without deciding sufficiency."""

    def __init__(self, *, output_limit: int) -> None:
        self.output_limit = max(1, min(40, int(output_limit or 16)))
        self.working_limit = max(40, min(120, self.output_limit * 3))
        self.items: list[EvidenceItem] = []
        self._keys: set[str] = set()

    def extend(self, values: Iterable[EvidenceItem]) -> int:
        added = 0
        for item in values:
            key = self._key(item)
            if not key or key in self._keys:
                continue
            if len(self.items) >= self.working_limit:
                self._replace_lower_confidence(item, key)
                continue
            self._keys.add(key)
            self.items.append(item)
            added += 1
        return added

    def output(self) -> list[EvidenceItem]:
        if len(self.items) <= self.output_limit:
            return list(self.items)
        selected = sorted(
            range(len(self.items)),
            key=lambda index: (float(self.items[index].confidence or 0.0), index),
            reverse=True,
        )[: self.output_limit]
        return [self.items[index] for index in sorted(selected)]

    def _replace_lower_confidence(self, candidate: EvidenceItem, key: str) -> None:
        candidate_score = float(candidate.confidence or 0.0)
        lowest_index = min(
            range(len(self.items)),
            key=lambda index: float(self.items[index].confidence or 0.0),
        )
        current = self.items[lowest_index]
        if candidate_score <= float(current.confidence or 0.0):
            return
        self._keys.discard(self._key(current))
        self._keys.add(key)
        self.items[lowest_index] = candidate

    @staticmethod
    def _key(item: EvidenceItem) -> str:
        return str(item.url or item.title or item.content[:100]).strip().lower()


__all__ = ["ResearchEvidenceStore"]
