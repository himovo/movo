"""Trusted artifact inputs exposed to the governed script sandbox."""

from __future__ import annotations

from typing import Any

from app.enterprise_capabilities.artifacts.references import require_owned_artifacts
from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext


def governed_script_files(
    arguments: dict[str, Any], context: CapabilityExecutionContext
) -> list[dict[str, Any]]:
    """Merge explicit files with the current turn's trusted attachments.

    Every script invocation uses a fresh sandbox. Supplying the active turn's
    attachments here makes retries deterministic without retaining a previous
    sandbox or trusting model-provided storage URLs.
    """
    candidates: list[Any] = list(arguments.get("files") or [])
    for key in ("documents", "images"):
        candidates.extend(list(context.turn_context.get(key) or []))
    governed = require_owned_artifacts(candidates, user_id=context.user_id)
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in governed:
        marker = str(item.get("object_path") or "")
        if marker and marker not in seen:
            seen.add(marker)
            unique.append(item)
    return unique


__all__ = ["governed_script_files"]
