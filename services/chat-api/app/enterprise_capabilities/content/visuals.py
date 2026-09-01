from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Awaitable
from typing import Any, Callable

from app.enterprise_capabilities.content.publish_assembly import DeferredVisualFinalizer


@dataclass(frozen=True)
class FinalBodyVisualResult:
    markdown: str
    assets: list[dict[str, Any]] = field(default_factory=list)
    assembly: dict[str, Any] = field(default_factory=dict)


class FinalBodyVisualAssembler:
    """Reuse ASKAI's deferred visual pipeline for single-shot writer output."""

    def __init__(
        self,
        *,
        finalizer_factory: Callable[[], DeferredVisualFinalizer] = DeferredVisualFinalizer,
    ) -> None:
        self._finalizer_factory = finalizer_factory

    async def finalize(
        self,
        *,
        markdown: str,
        output_spec: dict[str, Any],
        user_query: str,
        language: str,
        user_id: str,
        progress_sink: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> FinalBodyVisualResult:
        body = str(markdown or "").strip()
        writer_path = str(output_spec.get("__writer_path") or "").strip().lower()
        if not body or writer_path != "single_shot":
            return FinalBodyVisualResult(markdown=body)

        finalizer = self._finalizer_factory()
        if not finalizer.has_visual_work(final_markdown=body, output_spec=output_spec):
            return FinalBodyVisualResult(markdown=body)
        if progress_sink is not None:
            await progress_sink({
                "type": "activity",
                "content": {
                    "kind": "visual",
                    "message": (
                        "正文已完成，正在规划并生成配图"
                        if str(language or "").lower().startswith("zh")
                        else "The draft is complete; planning and generating visuals"
                    ),
                },
            })
        assembly = await finalizer.finalize(
            final_markdown=body,
            output_spec=output_spec,
            user_query=str(user_query or ""),
            language=str(language or "zh"),
            user_id=str(user_id or "anonymous"),
        )
        assets = [
            item.model_dump(mode="json")
            for item in list(assembly.generated_assets or [])
            if str(item.status or "").strip() == "generated" and str(item.image_url or "").strip()
        ]
        return FinalBodyVisualResult(
            markdown=str(assembly.final_markdown or body).strip(),
            assets=assets,
            assembly=assembly.model_dump(mode="json"),
        )


__all__ = ["FinalBodyVisualAssembler", "FinalBodyVisualResult"]
