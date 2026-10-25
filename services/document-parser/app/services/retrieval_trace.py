"""Metadata-only retrieval diagnostics; never log document text or user queries."""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


def trace_stage(stage: str, items: list[dict[str, Any]]) -> None:
    logger.info(
        "knowledge retrieval stage=%s count=%s chunks=%s",
        stage,
        len(items),
        [(str(item.get("documentId") or ""), str(item.get("chunkId") or "")) for item in items],
    )
