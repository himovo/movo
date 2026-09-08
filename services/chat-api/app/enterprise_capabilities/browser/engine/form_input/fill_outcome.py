"""One interpretation of the sidecar fill receipt for all form consumers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class FillOutcome:
    status: Literal["confirmed", "ambiguous", "failed"]
    reason: str


def resolve_fill_outcome(*, result: Any, ok: bool, error: str | None = None) -> FillOutcome:
    if not ok:
        message = str(error or "fill failed")
        uncertain = "target_not_found" in message.lower() and "after input" in message.lower()
        return FillOutcome("ambiguous" if uncertain else "failed", message)
    receipt = result.get("fill_receipt") if isinstance(result, dict) else None
    if receipt is None:
        # Legacy sidecars only acknowledge a fill after their local value check.
        return FillOutcome("confirmed", "legacy browser agent acknowledged the fill")
    if not isinstance(receipt, dict):
        return FillOutcome("ambiguous", "invalid fill receipt")
    status = str(receipt.get("status") or "")
    if status not in {"confirmed", "ambiguous", "failed"}:
        return FillOutcome("ambiguous", "fill receipt has no recognized verification status")
    return FillOutcome(status, str(receipt.get("reason") or f"fill {status}"))
