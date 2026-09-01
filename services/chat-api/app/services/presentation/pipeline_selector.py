from __future__ import annotations

from typing import Any, Dict

from app.services.presentation.image_native.pipeline import ImageNativePresentationPipeline
from app.services.presentation.pipeline import PresentationPipeline


def presentation_generation_mode(output_spec: Dict[str, Any] | None = None) -> str:
    spec = output_spec if isinstance(output_spec, dict) else {}
    mode = str(spec.get("presentation_generation_mode") or "").strip().lower()
    if mode not in {"llm", "image_rebuild"}:
        raise ValueError("presentation_generation_mode must be llm or image_rebuild")
    return mode


def build_presentation_pipeline(output_spec: Dict[str, Any] | None = None) -> Any:
    if presentation_generation_mode(output_spec) == "llm":
        return PresentationPipeline()
    return ImageNativePresentationPipeline()
