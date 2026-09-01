"""Finalize generated content before an existing Browser Agent Loop consumes it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .contracts import PublishAssemblySpec
from .deferred_finalizer import DeferredVisualFinalizer


@dataclass(frozen=True)
class BrowserHandoffAssemblyResult:
    markdown: str
    visual_assets: List[Dict[str, Any]]
    assembly: Dict[str, Any]


async def finalize_browser_handoff_assembly(
    *,
    markdown: str,
    output_spec: Dict[str, Any],
    user_query: str,
    language: str,
    user_id: str,
    finalizer: DeferredVisualFinalizer | None = None,
) -> BrowserHandoffAssemblyResult:
    """Reuse the normal final-body visual pipeline at the browser boundary."""
    body = str(markdown or "").strip()
    if not body:
        return BrowserHandoffAssemblyResult(markdown="", visual_assets=[], assembly={})

    visual_finalizer = finalizer or DeferredVisualFinalizer()
    if not visual_finalizer.has_visual_work(
        final_markdown=body,
        output_spec=output_spec,
    ):
        return BrowserHandoffAssemblyResult(markdown=body, visual_assets=[], assembly={})

    assembly = await visual_finalizer.finalize(
        final_markdown=body,
        output_spec=output_spec,
        user_query=str(user_query or ""),
        language=str(language or "zh"),
        user_id=str(user_id or "anonymous"),
    )
    final_markdown = str(assembly.final_markdown or body).strip()
    visual_assets = [
        asset.model_dump()
        for asset in list(assembly.generated_assets or [])
        if str(asset.status or "").strip() == "generated"
        and str(asset.image_url or "").strip()
    ]
    return BrowserHandoffAssemblyResult(
        markdown=final_markdown,
        visual_assets=visual_assets,
        assembly=assembly.model_dump(),
    )


__all__ = [
    "BrowserHandoffAssemblyResult",
    "finalize_browser_handoff_assembly",
]
