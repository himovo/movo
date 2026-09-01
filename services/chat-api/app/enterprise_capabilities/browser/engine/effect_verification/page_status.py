"""Extract newly visible operation status text from two page observations."""
from __future__ import annotations

from typing import Iterable, List

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation

from .contracts import EffectEvidence
from .page_text_delta import compact_insertions
from .status_semantics import INLINE_STATUS, classify_status_text


def collect_new_page_status(before: Observation, after: Observation) -> List[EffectEvidence]:
    """Return concise status lines that appeared after the operation.

    Page-level text is used only as a before/after delta. This avoids treating
    persistent navigation labels such as "Sent" as proof of a new operation.
    """
    old = {_normalise(line) for line in _status_surfaces(before) if _normalise(line)}
    evidence: List[EffectEvidence] = []
    seen = set()
    candidates = [
        *((line, "page_status_delta") for line in _status_surfaces(after)),
        *((line, "page_message_delta") for line in compact_insertions(before.page_text, after.page_text)),
    ]
    for line, kind in candidates:
        text = _normalise(line)
        if not text or text in old or text in seen:
            continue
        seen.add(text)
        polarity = classify_status_text(text)
        if polarity == "neutral" and kind != "page_message_delta":
            continue
        evidence.append(EffectEvidence(
            evidence_id=f"page_status:{len(evidence)}:{abs(hash(text)) % 10_000_000}",
            kind=kind,
            detail=text[:160],
            polarity=polarity,
            weight=(
                0.92 if polarity in {"positive", "negative"}
                else 0.65 if polarity == "pending"
                else 0.45
            ),
        ))
    return evidence[:8]


def _status_surfaces(observation: Observation) -> Iterable[str]:
    for raw in str(observation.page_text or "").splitlines():
        line = _normalise(raw)
        if 1 <= len(line) <= 100:
            yield line
        elif len(line) > 100:
            # Many SPAs flatten the entire accessibility tree into one line.
            # Keep only compact operation-status phrases instead of discarding
            # the line or treating the whole page as a success message.
            for match in INLINE_STATUS.finditer(line):
                snippet = _normalise(match.group(0))
                if snippet:
                    yield snippet
    for item in observation.elements:
        if not isinstance(item, dict) or str(item.get("role") or "").lower() not in {"alert", "status"}:
            continue
        yield " ".join(str(item.get(key) or "") for key in ("name", "text"))


def _normalise(value: str) -> str:
    return " ".join(str(value or "").split()).strip()
