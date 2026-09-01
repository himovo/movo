from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StagnationBudget:
    """Bounds repeated recovery cycles that remain on the same page URL."""

    max_notices: int = 3
    _url: str = ""
    _notices: int = 0

    def record_notice(self, url: str) -> bool:
        normalized = str(url or "").strip()
        if normalized != self._url:
            self._url = normalized
            self._notices = 0
        self._notices += 1
        return self._notices >= max(1, int(self.max_notices))

    @property
    def notices(self) -> int:
        return self._notices


__all__ = ["StagnationBudget"]
