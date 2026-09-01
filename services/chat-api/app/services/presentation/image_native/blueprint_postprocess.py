from __future__ import annotations

from typing import Any, Dict

from app.services.presentation.contracts import FreeformBlock, FreeformPageBlueprint


_FONT_KEYS = {"font_size"}
_PX_STYLE_KEYS = {
    "border_radius",
    "border_width",
    "line_weight",
    "padding",
}


def postprocess_image_native_page(
    page: FreeformPageBlueprint,
    *,
    source_slide_image_url: str,
    image_asset_map: Dict[str, str],
    allow_source_slide_background: bool = True,
) -> FreeformPageBlueprint:
    out = page.model_copy(deep=True)
    _walk_blocks(
        list(out.blocks or []),
        source_slide_image_url=str(source_slide_image_url or "").strip(),
        image_asset_map=dict(image_asset_map or {}),
        allow_source_slide_background=allow_source_slide_background,
    )
    if allow_source_slide_background:
        _ensure_real_visual_background(out, source_slide_image_url=str(source_slide_image_url or "").strip())
        _downgrade_duplicate_source_slide_images(out, source_slide_image_url=str(source_slide_image_url or "").strip())
    else:
        _downgrade_source_slide_images(out, source_slide_image_url=str(source_slide_image_url or "").strip())
    return out


def _walk_blocks(
    blocks: list[FreeformBlock],
    *,
    source_slide_image_url: str,
    image_asset_map: Dict[str, str],
    allow_source_slide_background: bool,
) -> None:
    for block in blocks:
        _normalize_style_units(block)
        _hydrate_image_block(
            block,
            source_slide_image_url=source_slide_image_url,
            image_asset_map=image_asset_map,
            allow_source_slide_background=allow_source_slide_background,
        )
        if block.children:
            _walk_blocks(
                list(block.children or []),
                source_slide_image_url=source_slide_image_url,
                image_asset_map=image_asset_map,
                allow_source_slide_background=allow_source_slide_background,
            )


def _normalize_style_units(block: FreeformBlock) -> None:
    style = dict(block.style or {})
    for key in list(style.keys()):
        raw = style.get(key)
        if key in _FONT_KEYS:
            parsed = _coerce_float(raw)
            if parsed is not None and 0 < parsed <= 1:
                style[key] = int(round(parsed * 1000))
            elif parsed is not None and 1 < parsed < 6:
                style[key] = int(round(parsed * 10))
        elif key in _PX_STYLE_KEYS:
            parsed = _coerce_float(raw)
            if parsed is not None and 0 < parsed <= 1:
                style[key] = round(parsed * 1000, 2)
        elif key in {"border_color", "border"} and isinstance(raw, str):
            # The VLM often emits border-color as a raw color under a key that
            # renderer expects to be CSS border shorthand or color. Keep color.
            style[key] = raw
    block.style = style


def _hydrate_image_block(
    block: FreeformBlock,
    *,
    source_slide_image_url: str,
    image_asset_map: Dict[str, str],
    allow_source_slide_background: bool,
) -> None:
    if str(block.type or "").strip().lower() != "image":
        return
    content = str(block.content or "").strip()
    role = str(block.role or "").strip().lower()
    if content and source_slide_image_url and content == source_slide_image_url and role == "illustration" and not _covers_large_area(block):
        _downgrade_to_decorative_rect(block)
        return
    if _is_real_url(content):
        return
    block_id = str(block.id or "").strip()
    mapped = image_asset_map.get(block_id)
    if _is_real_url(mapped):
        block.content = mapped
        return
    # If a generated asset was produced but the composer changed ids, use a
    # conservative semantic match before falling back to the full slide.
    for key, url in image_asset_map.items():
        if not _is_real_url(url):
            continue
        if key and (key in block_id or block_id in key):
            block.content = url
            return
    if allow_source_slide_background and source_slide_image_url and (
        role in {"background", "visual_background", "hero_visual"}
        or block_id.lower().startswith(("bg", "background", "hero", "main_panel"))
        or _covers_large_area(block)
    ):
        block.content = source_slide_image_url
        return
    # Small decorative image hints without an actual asset should not render as
    # dashed image placeholders. Downgrade them to editable decorative shapes.
    _downgrade_to_decorative_rect(block)


def _ensure_real_visual_background(page: FreeformPageBlueprint, *, source_slide_image_url: str) -> None:
    if not source_slide_image_url:
        return
    has_real_large_image = False
    for block in _iter_blocks(list(page.blocks or [])):
        if str(block.type or "").strip().lower() == "image" and _is_real_url(block.content or "") and _covers_large_area(block):
            has_real_large_image = True
            break
    if has_real_large_image:
        return
    page.blocks.insert(
        0,
        FreeformBlock(
            id=f"{page.page_id}_source_visual_bg",
            type="image",
            role="visual_background",
            x=0,
            y=0,
            w=1,
            h=1,
            z_index=0,
            content=source_slide_image_url,
            style={"fit": "cover"},
        ),
    )


def _iter_blocks(blocks: list[FreeformBlock]):
    for block in blocks:
        yield block
        if block.children:
            yield from _iter_blocks(list(block.children or []))


def _covers_large_area(block: FreeformBlock) -> bool:
    try:
        return float(block.w or 0) * float(block.h or 0) >= 0.35
    except Exception:
        return False


def _downgrade_duplicate_source_slide_images(page: FreeformPageBlueprint, *, source_slide_image_url: str) -> None:
    if not source_slide_image_url:
        return
    kept_source_visual = False
    for block in _iter_blocks(list(page.blocks or [])):
        if str(block.type or "").strip().lower() != "image":
            continue
        if str(block.content or "").strip() != source_slide_image_url:
            continue
        role = str(block.role or "").strip().lower()
        should_keep = not kept_source_visual and (
            role in {"background", "visual_background", "hero_visual"}
            or str(block.id or "").lower().startswith(("bg", "background", "hero"))
            or _covers_large_area(block)
        )
        if should_keep:
            kept_source_visual = True
            continue
        _downgrade_to_decorative_rect(block)


def _downgrade_source_slide_images(page: FreeformPageBlueprint, *, source_slide_image_url: str) -> None:
    if not source_slide_image_url:
        return
    for block in _iter_blocks(list(page.blocks or [])):
        if str(block.type or "").strip().lower() == "image" and str(block.content or "").strip() == source_slide_image_url:
            _downgrade_to_decorative_rect(block)


def _downgrade_to_decorative_rect(block: FreeformBlock) -> None:
    block.type = "rectangle"
    block.content = ""
    block.style = {
        "background": str(block.style.get("background") or "rgba(0,0,0,0.04)"),
        "border_radius": block.style.get("border_radius", 12),
        "opacity": block.style.get("opacity", 0.35),
        **dict(block.style or {}),
    }


def _is_real_url(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return (
        text.startswith("http://")
        or text.startswith("https://")
        or text.startswith("/")
        or text.startswith("data:image/")
    )


def _coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower().replace("px", "")
    try:
        return float(text)
    except Exception:
        return None
