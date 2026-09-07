from __future__ import annotations

import logging
import time
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass
class PlannerMeasurement:
    input_chars: int
    started_at: float = 0.0

    def __enter__(self) -> "PlannerMeasurement":
        self.started_at = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        logger.info(
            "browser planner completed",
            extra={
                "event": "browser.planner",
                "input_chars": self.input_chars,
                "duration_ms": int((time.monotonic() - self.started_at) * 1000),
                "ok": exc is None,
                "error": str(exc)[:240] if exc is not None else "",
            },
        )
