"""Final admission contract for ASKAI-governed content production."""

from __future__ import annotations

from typing import Any


def build_content_acceptance(
    *,
    markdown: str,
    image_count: int,
    required_visual_min: int,
    quality_verdict: str,
    quality_status: str,
) -> dict[str, Any]:
    """Project existing pipeline outcomes; this function owns no quality rules."""
    reasons: list[str] = []
    if not str(markdown or "").strip():
        reasons.append("content_pipeline_returned_no_content")
    if image_count < required_visual_min:
        reasons.append("required_visuals_missing")
    accepted = not reasons
    return {
        "status": "accepted" if accepted else "rejected",
        "retry_allowed": not accepted,
        "reasons": reasons,
        "quality_verdict": str(quality_verdict or "not_evaluated"),
        "quality_status": str(quality_status or "not_evaluated"),
        "character_count": len(str(markdown or "")),
        "image_count": int(image_count),
        "required_visual_min": int(required_visual_min),
    }


__all__ = ["build_content_acceptance"]
