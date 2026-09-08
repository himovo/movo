from __future__ import annotations

from typing import Any

from app.services.presentation.contracts import FreeformBlock, FreeformPageBlueprint


class ImagePageBuilder:
    """Represent one generated slide as one full-canvas image block."""

    def build(
        self,
        *,
        page_plan: dict[str, Any],
        source_slide_image_url: str,
    ) -> FreeformPageBlueprint:
        page_id = str(page_plan.get("page_id") or "page_01").strip() or "page_01"
        return FreeformPageBlueprint(
            page_id=page_id,
            page_title=str(page_plan.get("key_takeaway") or "").strip(),
            layout_type="image_native_full_slide",
            design_intent=str(page_plan.get("visual_intent") or "").strip(),
            blocks=[
                FreeformBlock(
                    id=f"{page_id}_visual",
                    type="image",
                    role="full_slide_visual",
                    x=0,
                    y=0,
                    w=1,
                    h=1,
                    z_index=0,
                    content=str(source_slide_image_url or "").strip(),
                    style={"fit": "cover"},
                )
            ],
        )


def is_image_only_page(page: FreeformPageBlueprint) -> bool:
    blocks = list(page.blocks or [])
    return (
        page.layout_type == "image_native_full_slide"
        and len(blocks) == 1
        and str(blocks[0].type or "").strip().lower() == "image"
        and bool(str(blocks[0].content or "").strip())
    )


__all__ = ["ImagePageBuilder", "is_image_only_page"]
