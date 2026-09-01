from __future__ import annotations

import logging
import re
from typing import Any, Awaitable, Callable, Dict, List

from app.llm.configured_multimodal import ConfiguredMultimodalClient
from app.services.presentation.contracts import ComposerPageBlueprint, FreeformBlock, FreeformPageBlueprint
from app.services.presentation.image_native.prompt_builder import build_blueprint_compose_prompt

logger = logging.getLogger(__name__)

_LAYER_ROLE_HINTS = ("layer_node_container", "layer container", "input layer", "hidden layer", "output layer")
_TECHNICAL_DIAGRAM_HINTS = ("mlp", "cnn", "rnn", "transformer", "neural", "network", "perceptron", "topology", "schematic")


def _style_from_visual(style: Dict[str, Any] | None) -> Dict[str, Any]:
    raw = dict(style or {})
    out: Dict[str, Any] = {}
    fill = raw.get("fill") or raw.get("background") or raw.get("background_color")
    if fill:
        out["background"] = fill
    stroke = raw.get("stroke") or raw.get("border_color")
    if stroke:
        out["border_color"] = stroke
    radius = raw.get("radius") or raw.get("border_radius")
    if radius not in (None, ""):
        out["border_radius"] = radius
    shadow = raw.get("shadow") or raw.get("box_shadow")
    if shadow:
        out["box_shadow"] = shadow
    opacity = raw.get("opacity")
    if opacity not in (None, ""):
        out["opacity"] = opacity
    color = raw.get("color")
    if color:
        out["color"] = color
    return out


def _bbox_from_raw(raw: Dict[str, Any]) -> Dict[str, float]:
    bbox = raw.get("bbox") if isinstance(raw.get("bbox"), dict) else {}
    return {
        "x": float(bbox.get("x") or 0.0),
        "y": float(bbox.get("y") or 0.0),
        "w": float(bbox.get("w") or 0.0),
        "h": float(bbox.get("h") or 0.0),
    }


class BlueprintComposer:
    def __init__(self) -> None:
        self._client = ConfiguredMultimodalClient()

    async def compose(
        self,
        *,
        deck_brief: Dict[str, Any],
        page_plan: Dict[str, Any],
        visual_analysis: Dict[str, Any],
        image_asset_map: Dict[str, str],
        icon_svg_map: Dict[str, Dict[str, str]] | None = None,
        source_slide_image_url: str,
        user_id: str,
        session_id: str,
        progress_callback: Callable[[Dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> FreeformPageBlueprint:
        regions = list(visual_analysis.get("regions") or [])
        if not regions:
            payload = await self._client.call_json(
                prompt=build_blueprint_compose_prompt(
                    deck_brief=deck_brief,
                    page_plan=page_plan,
                    visual_analysis=visual_analysis,
                    image_asset_map=image_asset_map,
                    source_slide_image_url=source_slide_image_url,
                    icon_svg_map=icon_svg_map or {},
                ),
                stage="presentation_image_native_blueprint_compose",
                intent="generation",
                user_id=user_id,
                session_id=session_id,
                request_payload_extra={"page_id": str(page_plan.get("page_id") or "")},
            )
            page = ComposerPageBlueprint.model_validate(payload)
        else:
            await _emit_progress(
                progress_callback,
                {
                    "stage": "blueprint_compose",
                    "status": "running",
                    "page_id": str(page_plan.get("page_id") or ""),
                    "region_count": len(regions),
                    "message": f"开始分区域重建 blueprint（{len(regions)} 个区域）",
                },
            )
            partial_pages: List[ComposerPageBlueprint] = []
            total_regions = len(regions)
            for index, region in enumerate(regions, start=1):
                region_label = str(region.get("semantic_role") or region.get("region_type") or region.get("id") or f"region_{index}").strip()
                await _emit_progress(
                    progress_callback,
                    {
                        "stage": "blueprint_region_compose",
                        "status": "running",
                        "page_id": str(page_plan.get("page_id") or ""),
                        "region_id": str(region.get("id") or ""),
                        "region_index": index,
                        "region_total": total_regions,
                        "message": f"开始重建 blueprint 区域 {index}/{total_regions}：{region_label}",
                    },
                )
                region_analysis = _visual_analysis_for_region(visual_analysis=visual_analysis, region=region)
                payload = await self._client.call_json(
                    prompt=build_blueprint_compose_prompt(
                        deck_brief=deck_brief,
                        page_plan=page_plan,
                        visual_analysis=region_analysis,
                        image_asset_map=image_asset_map,
                        source_slide_image_url=source_slide_image_url,
                        icon_svg_map=icon_svg_map or {},
                        focus_region=region,
                    ),
                    stage="presentation_image_native_blueprint_compose_region",
                    intent="generation",
                    user_id=user_id,
                    session_id=f"{session_id}::blueprint::{str(region.get('id') or index)}",
                    request_payload_extra={
                        "page_id": str(page_plan.get("page_id") or ""),
                        "region_id": str(region.get("id") or ""),
                        "region_index": index,
                        "region_total": total_regions,
                    },
                )
                partial_page = ComposerPageBlueprint.model_validate(payload)
                partial_pages.append(partial_page)
                await _emit_progress(
                    progress_callback,
                    {
                        "stage": "blueprint_region_compose",
                        "status": "completed",
                        "page_id": str(page_plan.get("page_id") or ""),
                        "region_id": str(region.get("id") or ""),
                        "region_index": index,
                        "region_total": total_regions,
                        "block_count": len(list(partial_page.blocks or [])),
                        "partial_blueprint": partial_page.model_dump(),
                        "message": f"区域 {index}/{total_regions} blueprint 完成：{region_label}（{len(list(partial_page.blocks or []))} 个 blocks）",
                    },
                )
            page = _merge_partial_pages(
                page_plan=page_plan,
                deck_brief=deck_brief,
                partial_pages=partial_pages,
            )
            await _emit_progress(
                progress_callback,
                {
                    "stage": "blueprint_compose",
                    "status": "completed",
                    "page_id": str(page_plan.get("page_id") or ""),
                    "block_count": len(list(page.blocks or [])),
                    "message": f"blueprint 分区域重建完成：{len(list(page.blocks or []))} 个 blocks",
                },
            )
        page.page_id = str(page.page_id or page_plan.get("page_id") or "").strip() or "page_01"
        if not page.page_title:
            page.page_title = str(page_plan.get("key_takeaway") or "").strip()
        if not page.design_intent:
            page.design_intent = str(page_plan.get("visual_intent") or "").strip()
        page = enrich_page_from_analysis(
            page=page,
            page_plan=page_plan,
            analysis=visual_analysis,
            icon_svg_map=icon_svg_map or {},
        )
        return page


def fallback_page_from_analysis(
    *,
    page_plan: Dict[str, Any],
    analysis: Dict[str, Any],
    image_asset_map: Dict[str, str],
    source_slide_image_url: str,
    icon_svg_map: Dict[str, Dict[str, str]] | None = None,
) -> FreeformPageBlueprint:
    """Deterministic last-resort mapper so generation never returns an empty page."""
    blocks: List[FreeformBlock] = []
    page_id = str(page_plan.get("page_id") or analysis.get("page_id") or "page_01").strip() or "page_01"
    asset_by_id = dict(image_asset_map or {})

    for elem in list(analysis.get("elements") or []):
        if not isinstance(elem, dict):
            continue
        bbox = elem.get("bbox") if isinstance(elem.get("bbox"), dict) else {}
        etype = str(elem.get("type") or "shape").strip().lower()
        strategy = str(elem.get("render_strategy") or "freeform_block").strip().lower()
        elem_id = str(elem.get("id") or f"{page_id}_elem_{len(blocks)+1}").strip()
        style = _style_from_visual(elem.get("style") if isinstance(elem.get("style"), dict) else {})
        z = int(elem.get("z_index") or len(blocks))
        if strategy == "ignore" or etype == "text":
            continue
        if strategy == "image_asset" or etype in {"background", "illustration"}:
            content = asset_by_id.get(elem_id) or source_slide_image_url
            blocks.append(
                FreeformBlock(
                    id=elem_id,
                    type="image",
                    role=etype,
                    x=float(bbox.get("x") or 0),
                    y=float(bbox.get("y") or 0),
                    w=float(bbox.get("w") or 1),
                    h=float(bbox.get("h") or 1),
                    z_index=z,
                    content=content,
                    image_prompt=str(elem.get("asset_prompt") or elem.get("content_hint") or ""),
                    style={"fit": "cover", **style},
                )
            )
        elif etype == "line":
            blocks.append(
                FreeformBlock(
                    id=elem_id,
                    type="line",
                    role=str(elem.get("semantic_role") or "line"),
                    x=float(bbox.get("x") or 0),
                    y=float(bbox.get("y") or 0),
                    x2=float(bbox.get("x") or 0) + float(bbox.get("w") or 0.1),
                    y2=float(bbox.get("y") or 0) + float(bbox.get("h") or 0.0),
                    w=float(bbox.get("w") or 0.1),
                    h=float(bbox.get("h") or 0.01),
                    z_index=z,
                    style=style,
                )
            )
        elif etype == "icon":
            icon_svg = ""
            if icon_svg_map and elem_id in icon_svg_map:
                icon_svg = str((icon_svg_map.get(elem_id) or {}).get("svg") or "")
            blocks.append(
                FreeformBlock(
                    id=elem_id,
                    type="icon",
                    role=str(elem.get("semantic_role") or "icon"),
                    x=float(bbox.get("x") or 0),
                    y=float(bbox.get("y") or 0),
                    w=float(bbox.get("w") or 0.04),
                    h=float(bbox.get("h") or 0.06),
                    z_index=z,
                    icon=str(elem.get("content_hint") or "sparkles"),
                    icon_svg=icon_svg,
                    style=style,
                )
            )
        else:
            blocks.append(
                FreeformBlock(
                    id=elem_id,
                    type="rectangle",
                    role=str(elem.get("semantic_role") or etype),
                    x=float(bbox.get("x") or 0),
                    y=float(bbox.get("y") or 0),
                    w=float(bbox.get("w") or 0.1),
                    h=float(bbox.get("h") or 0.1),
                    z_index=z,
                    style=style,
                )
            )

    text_elements = [e for e in list(analysis.get("elements") or []) if isinstance(e, dict) and str(e.get("type") or "") == "text"]
    planned_texts = [t for t in list(page_plan.get("planned_texts") or []) if isinstance(t, dict) and str(t.get("text") or "").strip()]
    for idx, text in enumerate(planned_texts):
        ref_id = str(text.get("id") or f"text_{idx+1}")
        match = next((e for e in text_elements if str(e.get("text_ref_id") or "") == ref_id), None)
        bbox = match.get("bbox") if isinstance(match, dict) and isinstance(match.get("bbox"), dict) else {}
        blocks.append(
            FreeformBlock(
                id=f"{page_id}_{ref_id}",
                type="text_box",
                role=str(text.get("role") or "body"),
                x=float(bbox.get("x") if bbox.get("x") is not None else 0.08),
                y=float(bbox.get("y") if bbox.get("y") is not None else 0.12 + idx * 0.12),
                w=float(bbox.get("w") if bbox.get("w") is not None else 0.72),
                h=float(bbox.get("h") if bbox.get("h") is not None else 0.08),
                z_index=20 + idx,
                content=str(text.get("text") or ""),
                style={
                    "font_size": 44 if str(text.get("role")) == "title" else 24,
                    "font_weight": "bold" if int(text.get("priority") or 0) >= 8 else "normal",
                    "color": "#111827",
                    "line_height": 1.18,
                    "text_align": "left",
                },
            )
        )
    page = FreeformPageBlueprint(
        page_id=page_id,
        page_title=str(page_plan.get("key_takeaway") or "").strip(),
        layout_type="image_native_fallback",
        design_intent=str(page_plan.get("visual_intent") or "").strip(),
        blocks=blocks,
    )
    return enrich_page_from_analysis(
        page=page,
        page_plan=page_plan,
        analysis=analysis,
        icon_svg_map=icon_svg_map or {},
    )


def enrich_page_from_analysis(
    *,
    page: FreeformPageBlueprint,
    page_plan: Dict[str, Any],
    analysis: Dict[str, Any],
    icon_svg_map: Dict[str, Dict[str, str]],
) -> FreeformPageBlueprint:
    """Deterministically preserve semantic text/icons the LLM composer missed.

    This is shared by production image-native generation and the single-image
    test runner, so POC-style reconstruction improvements are not test-only.
    """
    out = page.model_copy(deep=True)
    planned_text_by_id = {
        str(item.get("id") or "").strip(): str(item.get("text") or "").strip()
        for item in list(page_plan.get("planned_texts") or [])
        if isinstance(item, dict)
    }

    existing_texts = [entry for entry in _iter_blocks_with_page_geometry(list(out.blocks or [])) if str(entry["block"].type) == "text_box"]
    existing_ids = {str(block.id or "").strip() for block in _iter_blocks(list(out.blocks or []))}
    max_z = max([int(block.z_index or 0) for block in _iter_blocks(list(out.blocks or []))] or [0])
    _reconcile_existing_text_styles_from_analysis(page=out, analysis=analysis)

    for text in _analysis_text_items(analysis):
        text_id = str(text.get("id") or "").strip()
        if not text_id or text_id in existing_ids:
            continue
        content = _resolve_text_content(text, planned_text_by_id)
        if not content:
            continue
        bbox = text.get("bbox") if isinstance(text.get("bbox"), dict) else {}
        if _duplicates_existing_text(content, bbox, existing_texts):
            continue
        font = text.get("font") if isinstance(text.get("font"), dict) else {}
        style = _text_style_from_analysis(text, font)
        max_z += 1
        out.blocks.append(
            FreeformBlock(
                id=text_id,
                type="text_box",
                role=str(text.get("role") or "body").strip() or "body",
                x=float(bbox.get("x") or 0),
                y=float(bbox.get("y") or 0),
                w=float(bbox.get("w") or 0.1),
                h=float(bbox.get("h") or 0.04),
                z_index=int(text.get("z_index") or max_z),
                content=content,
                style=style,
            )
        )
        existing_texts.append(
            {
                "block": out.blocks[-1],
                "x": float(out.blocks[-1].x or 0.0),
                "y": float(out.blocks[-1].y or 0.0),
                "w": float(out.blocks[-1].w or 0.0),
                "h": float(out.blocks[-1].h or 0.0),
            }
        )
        existing_ids.add(text_id)

    for block in _iter_blocks(list(out.blocks or [])):
        if str(block.type or "").strip().lower() != "icon":
            continue
        icon_id = str(block.id or "").strip()
        svg = str((icon_svg_map.get(icon_id) or {}).get("svg") or "").strip()
        if svg and not str(block.icon_svg or "").strip():
            block.icon_svg = svg
    _preserve_missing_visual_elements(
        page=out,
        analysis=analysis,
        icon_svg_map=icon_svg_map,
        existing_ids=existing_ids,
    )
    _enhance_semantic_modules(
        page=out,
        analysis=analysis,
        existing_ids=existing_ids,
    )
    return out


async def _emit_progress(
    progress_callback: Callable[[Dict[str, Any]], Awaitable[None] | None] | None,
    payload: Dict[str, Any],
) -> None:
    if progress_callback is None:
        return
    result = progress_callback(dict(payload or {}))
    if hasattr(result, "__await__"):
        await result


def _merge_partial_pages(
    *,
    page_plan: Dict[str, Any],
    deck_brief: Dict[str, Any],
    partial_pages: List[ComposerPageBlueprint],
) -> ComposerPageBlueprint:
    merged_blocks: List[FreeformBlock] = []
    seen_ids: Dict[str, int] = {}
    page_title = ""
    page_subtitle = ""
    layout_type = "image_native_region_compose"
    design_intent = str(page_plan.get("visual_intent") or "").strip()
    page_style: Dict[str, Any] = {}
    for page in partial_pages:
        if not page_title:
            page_title = str(page.page_title or "").strip()
        if not page_subtitle:
            page_subtitle = str(page.page_subtitle or "").strip()
        if not page_style and isinstance(page.style, dict):
            page_style = dict(page.style or {})
        if str(page.layout_type or "").strip():
            layout_type = str(page.layout_type or "").strip()
        for block in list(page.blocks or []):
            block_id = str(block.id or "").strip()
            if not block_id:
                merged_blocks.append(block)
                continue
            if block_id in seen_ids:
                merged_blocks[seen_ids[block_id]] = block
            else:
                seen_ids[block_id] = len(merged_blocks)
                merged_blocks.append(block)
    return ComposerPageBlueprint(
        page_id=str(page_plan.get("page_id") or "page_01").strip() or "page_01",
        page_title=page_title or str(page_plan.get("key_takeaway") or "").strip(),
        page_subtitle=page_subtitle,
        layout_type=layout_type,
        design_intent=design_intent,
        style=page_style,
        blocks=merged_blocks,
    )


def _visual_analysis_for_region(*, visual_analysis: Dict[str, Any], region: Dict[str, Any]) -> Dict[str, Any]:
    region_id = str(region.get("id") or "").strip()
    bbox = region.get("bbox") if isinstance(region.get("bbox"), dict) else {}
    related_group_ids = {
        str(item or "").strip()
        for item in list(region.get("related_group_ids") or [])
        if str(item or "").strip()
    }
    groups = [
        dict(group)
        for group in list(visual_analysis.get("groups") or [])
        if isinstance(group, dict) and (
            str(group.get("id") or "").strip() in related_group_ids
            or _bbox_overlaps(group.get("bbox"), bbox)
        )
    ]
    element_ids_from_groups = {
        str(child or "").strip()
        for group in groups
        for child in list(group.get("child_ids") or [])
        if str(child or "").strip()
    }
    elements = [
        dict(elem)
        for elem in list(visual_analysis.get("elements") or [])
        if isinstance(elem, dict) and (
            str(elem.get("group_id") or "").strip() in related_group_ids
            or str(elem.get("id") or "").strip() in element_ids_from_groups
            or _bbox_overlaps(elem.get("bbox"), bbox)
        )
    ]
    text_elements = [
        dict(text)
        for text in list(visual_analysis.get("text_elements") or [])
        if isinstance(text, dict) and (
            str(text.get("group_id") or "").strip() in related_group_ids
            or _bbox_overlaps(text.get("bbox"), bbox)
        )
    ]
    all_ids = {
        str(item.get("id") or "").strip()
        for item in elements + text_elements + groups
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    relationships = [
        dict(rel)
        for rel in list(visual_analysis.get("relationships") or [])
        if isinstance(rel, dict)
        and str(rel.get("source_id") or "").strip() in all_ids
        and str(rel.get("target_id") or "").strip() in all_ids
    ]
    image_assets = [
        dict(asset)
        for asset in list(visual_analysis.get("image_assets") or [])
        if isinstance(asset, dict) and _bbox_overlaps(asset.get("bbox"), bbox)
    ]
    return {
        "page_id": str(visual_analysis.get("page_id") or ""),
        "canvas": dict(visual_analysis.get("canvas") or {"w": 1600, "h": 900, "aspect": "16:9"}),
        "style": dict(visual_analysis.get("style") or {}),
        "layout": dict(visual_analysis.get("layout") or {}),
        "regions": [dict(region)],
        "elements": elements,
        "text_elements": text_elements,
        "groups": groups,
        "relationships": relationships,
        "image_assets": image_assets,
        "reconstruction_notes": list(visual_analysis.get("reconstruction_notes") or []),
        "risks": list(visual_analysis.get("risks") or []),
    }


def _bbox_overlaps(raw_a: Dict[str, Any] | None, raw_b: Dict[str, Any] | None) -> bool:
    if not isinstance(raw_a, dict) or not isinstance(raw_b, dict):
        return False
    ax1 = float(raw_a.get("x") or 0.0)
    ay1 = float(raw_a.get("y") or 0.0)
    ax2 = ax1 + float(raw_a.get("w") or 0.0)
    ay2 = ay1 + float(raw_a.get("h") or 0.0)
    bx1 = float(raw_b.get("x") or 0.0)
    by1 = float(raw_b.get("y") or 0.0)
    bx2 = bx1 + float(raw_b.get("w") or 0.0)
    by2 = by1 + float(raw_b.get("h") or 0.0)
    return ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1


def _analysis_text_items(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw in list((analysis or {}).get("text_elements") or []):
        if isinstance(raw, dict):
            items.append(dict(raw))
    for raw in list((analysis or {}).get("elements") or []):
        if isinstance(raw, dict) and str(raw.get("type") or "").strip().lower() == "text":
            item = dict(raw)
            if "text" not in item and "content" in item:
                item["text"] = item.get("content")
            items.append(item)
    return items


def _analysis_visual_items(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw in list((analysis or {}).get("elements") or []):
        if not isinstance(raw, dict):
            continue
        if str(raw.get("type") or "").strip().lower() == "text":
            continue
        items.append(dict(raw))
    return items


def _resolve_text_content(item: Dict[str, Any], planned_text_by_id: Dict[str, str]) -> str:
    ref_id = str(item.get("text_ref_id") or "").strip()
    if ref_id and planned_text_by_id.get(ref_id):
        return planned_text_by_id[ref_id]
    for key in ("text", "content", "label", "title", "description"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def _text_style_from_analysis(item: Dict[str, Any], font: Dict[str, Any]) -> Dict[str, Any]:
    style = dict(item.get("style") or {}) if isinstance(item.get("style"), dict) else {}
    color = font.get("color") or style.get("color") or "#111827"
    size = font.get("size_px") or font.get("font_size") or style.get("font_size") or 20
    weight = font.get("weight") or style.get("font_weight") or 400
    align = item.get("align") or style.get("text_align") or "left"
    line_height = font.get("line_height") or style.get("line_height") or 1.18
    return {
        "font_size": size,
        "font_weight": weight,
        "color": color,
        "line_height": line_height,
        "text_align": align,
        "letter_spacing": font.get("letter_spacing") or style.get("letter_spacing") or 0,
        "overflow": "visible",
    }


def _reconcile_existing_text_styles_from_analysis(
    *,
    page: FreeformPageBlueprint,
    analysis: Dict[str, Any],
) -> None:
    """Keep composer text colors aligned with the visual analysis source.

    The composer can occasionally restyle an already analyzed text block while
    preserving its id/content. For image-native rebuilds the analysis is closer
    to the source image, so matching ids should inherit its typography.
    """
    analysis_by_id = {
        str(item.get("id") or "").strip(): item
        for item in _analysis_text_items(analysis)
        if str(item.get("id") or "").strip()
    }
    for block in _iter_blocks(list(page.blocks or [])):
        if str(block.type or "").strip().lower() != "text_box":
            continue
        source = analysis_by_id.get(str(block.id or "").strip())
        if not source:
            continue
        source_text = _resolve_text_content(source, {})
        if source_text and str(block.content or "").strip() and " ".join(source_text.split()) != " ".join(str(block.content or "").split()):
            continue
        font = source.get("font") if isinstance(source.get("font"), dict) else {}
        source_style = _text_style_from_analysis(source, font)
        merged = dict(block.style or {})
        for key in ("font_size", "font_weight", "color", "line_height", "text_align", "letter_spacing"):
            value = source_style.get(key)
            if value not in (None, ""):
                merged[key] = value
        merged.setdefault("overflow", "visible")
        block.style = merged


def _duplicates_existing_text(content: str, bbox: Dict[str, Any], existing: List[Dict[str, Any]]) -> bool:
    normalized = " ".join(str(content or "").split())
    for entry in existing:
        block = entry["block"]
        if " ".join(str(block.content or "").split()) != normalized:
            continue
        try:
            dx = abs(float(entry["x"] or 0) - float(bbox.get("x") or 0))
            dy = abs(float(entry["y"] or 0) - float(bbox.get("y") or 0))
            if dx < 0.04 and dy < 0.04:
                return True
        except Exception:
            return True
    return False


def _preserve_missing_visual_elements(
    *,
    page: FreeformPageBlueprint,
    analysis: Dict[str, Any],
    icon_svg_map: Dict[str, Dict[str, str]],
    existing_ids: set[str],
) -> None:
    visual_items = _analysis_visual_items(analysis)
    max_z = max([int(block.z_index or 0) for block in _iter_blocks(list(page.blocks or []))] or [0])
    existing_blocks = list(_iter_blocks_with_page_geometry(list(page.blocks or [])))
    for item in visual_items:
        item_id = str(item.get("id") or "").strip()
        if not item_id or item_id in existing_ids:
            continue
        render_strategy = str(item.get("render_strategy") or "").strip().lower()
        elem_type = str(item.get("type") or "").strip().lower()
        if render_strategy == "ignore":
            continue
        if elem_type in {"background", "illustration"}:
            continue
        if render_strategy == "image_asset":
            continue
        bbox = _bbox_from_raw(item)
        if elem_type == "line":
            if bbox["w"] <= 0 and bbox["h"] <= 0:
                continue
        elif bbox["w"] <= 0 or bbox["h"] <= 0:
            continue
        if _has_similar_visual_block(item=item, bbox=bbox, existing=existing_blocks):
            continue
        style = _style_from_visual(item.get("style") if isinstance(item.get("style"), dict) else {})
        max_z += 1
        block = _visual_item_to_block(
            item=item,
            bbox=bbox,
            style=style,
            z_index=max_z,
            icon_svg_map=icon_svg_map,
        )
        if block is None:
            continue
        page.blocks.append(block)
        existing_blocks.append(
            {
                "block": block,
                "x": float(block.x or 0.0),
                "y": float(block.y or 0.0),
                "w": float(block.w or 0.0),
                "h": float(block.h or 0.0),
            }
        )
        existing_ids.add(item_id)


def _visual_item_to_block(
    *,
    item: Dict[str, Any],
    bbox: Dict[str, float],
    style: Dict[str, Any],
    z_index: int,
    icon_svg_map: Dict[str, Dict[str, str]],
) -> FreeformBlock | None:
    item_id = str(item.get("id") or "").strip()
    elem_type = str(item.get("type") or "").strip().lower()
    role = (
        str(item.get("structural_role") or "").strip()
        or str(item.get("semantic_role") or "").strip()
        or elem_type
    )
    if elem_type == "line":
        return FreeformBlock(
            id=item_id,
            type="line",
            role=role,
            x=bbox["x"],
            y=bbox["y"],
            x2=bbox["x"] + bbox["w"],
            y2=bbox["y"] + bbox["h"],
            w=bbox["w"],
            h=max(bbox["h"], 0.002),
            z_index=int(item.get("z_index") or z_index),
            style=style,
        )
    if elem_type == "icon":
        semantic = str(item.get("content_hint") or item.get("nearby_text") or item.get("semantic_role") or "icon").strip()
        icon_svg = str((icon_svg_map.get(item_id) or {}).get("svg") or "").strip()
        return FreeformBlock(
            id=item_id,
            type="icon",
            role=role,
            x=bbox["x"],
            y=bbox["y"],
            w=bbox["w"],
            h=bbox["h"],
            z_index=int(item.get("z_index") or z_index),
            icon=semantic or "sparkles",
            icon_svg=icon_svg,
            style=style,
        )
    if elem_type == "circle" or _looks_like_circle_item(item):
        return FreeformBlock(
            id=item_id,
            type="circle",
            role=role,
            x=bbox["x"],
            y=bbox["y"],
            w=bbox["w"],
            h=bbox["h"],
            z_index=int(item.get("z_index") or z_index),
            style=style,
        )
    if elem_type in {"panel", "shape", "decorative"} or _looks_like_rect_item(item):
        return FreeformBlock(
            id=item_id,
            type="rectangle",
            role=role,
            x=bbox["x"],
            y=bbox["y"],
            w=bbox["w"],
            h=bbox["h"],
            z_index=int(item.get("z_index") or z_index),
            style=style,
        )
    return None


def _enhance_semantic_modules(
    *,
    page: FreeformPageBlueprint,
    analysis: Dict[str, Any],
    existing_ids: set[str],
) -> None:
    _enhance_layered_diagrams(page=page, analysis=analysis, existing_ids=existing_ids)


def _enhance_layered_diagrams(
    *,
    page: FreeformPageBlueprint,
    analysis: Dict[str, Any],
    existing_ids: set[str],
) -> None:
    groups = [dict(g) for g in list((analysis or {}).get("groups") or []) if isinstance(g, dict)]
    elements = [dict(e) for e in list((analysis or {}).get("elements") or []) if isinstance(e, dict)]
    page_entries = _iter_blocks_with_page_geometry(list(page.blocks or []))
    max_z = max([int(entry["block"].z_index or 0) for entry in page_entries] or [0])

    for group in groups:
        if not _is_layered_technical_diagram_group(group=group, elements=elements):
            continue
        group_id = str(group.get("id") or "").strip()
        layer_items = [
            dict(item)
            for item in elements
            if str(item.get("group_id") or "").strip() == group_id
            and _is_layer_container_item(item)
        ]
        layer_items.sort(key=lambda item: float(_bbox_from_raw(item)["x"]))
        if len(layer_items) < 3:
            continue
        bundle_line_ids = {
            str(item.get("id") or "").strip()
            for item in elements
            if str(item.get("group_id") or "").strip() == group_id
            and _is_connector_bundle_item(item)
            and str(item.get("id") or "").strip()
        }
        if bundle_line_ids:
            _remove_blocks_by_ids(page.blocks, bundle_line_ids)
            existing_ids.difference_update(bundle_line_ids)
            page_entries = _iter_blocks_with_page_geometry(list(page.blocks or []))
        region_bbox = _bbox_from_raw(group)
        existing_region_circles = [
            entry for entry in page_entries
            if str(entry["block"].type or "").strip().lower() == "circle"
            and _bbox_overlaps(
                {"x": entry["x"], "y": entry["y"], "w": entry["w"], "h": entry["h"]},
                region_bbox,
            )
        ]
        existing_region_lines = [
            entry for entry in page_entries
            if str(entry["block"].type or "").strip().lower() == "line"
            and _bbox_overlaps(
                {"x": entry["x"], "y": entry["y"], "w": entry["w"], "h": entry["h"]},
                region_bbox,
            )
        ]

        if len(existing_region_circles) < max(6, len(layer_items)):
            new_nodes = _build_layer_nodes(layer_items=layer_items, existing_ids=existing_ids)
            for block in new_nodes:
                max_z = max(max_z, int(block.z_index or 0))
                page.blocks.append(block)
                existing_ids.add(str(block.id or "").strip())
        if bundle_line_ids or len(existing_region_lines) < max(4, len(layer_items)):
            new_lines = _build_layer_connectors(layer_items=layer_items, elements=elements, existing_ids=existing_ids, base_z=max_z)
            for block in new_lines:
                max_z = max(max_z, int(block.z_index or 0))
                page.blocks.append(block)
                existing_ids.add(str(block.id or "").strip())
        page_entries = _iter_blocks_with_page_geometry(list(page.blocks or []))


def _is_layered_technical_diagram_group(*, group: Dict[str, Any], elements: List[Dict[str, Any]]) -> bool:
    if str(group.get("group_type") or "").strip().lower() != "diagram_region":
        return False
    group_id = str(group.get("id") or "").strip()
    group_text = " ".join(
        [
            group_id,
            str(group.get("semantic_role") or ""),
            str(group.get("notes") or ""),
        ]
    ).lower()
    if not any(hint in group_text for hint in _TECHNICAL_DIAGRAM_HINTS):
        child_ids = {str(child or "").strip() for child in list(group.get("child_ids") or []) if str(child or "").strip()}
        matched = [
            item for item in elements
            if str(item.get("id") or "").strip() in child_ids
            and _is_layer_container_item(item)
        ]
        return len(matched) >= 3
    return True


def _is_layer_container_item(item: Dict[str, Any]) -> bool:
    elem_type = str(item.get("type") or "").strip().lower()
    if elem_type not in {"panel", "shape", "diagram"}:
        return False
    structural_role = str(item.get("structural_role") or "").strip().lower()
    if any(token in structural_role for token in ("label", "connector", "ellipsis", "omission")):
        return False
    role_text = " ".join(
        [
            structural_role,
            str(item.get("semantic_role") or ""),
            str(item.get("content_hint") or ""),
            str(item.get("visual_description") or ""),
            str(item.get("id") or ""),
        ]
    ).lower()
    return any(hint in role_text for hint in _LAYER_ROLE_HINTS)


def _is_connector_bundle_item(item: Dict[str, Any]) -> bool:
    if str(item.get("type") or "").strip().lower() != "line":
        return False
    role_text = " ".join(
        [
            str(item.get("structural_role") or ""),
            str(item.get("semantic_role") or ""),
            str(item.get("content_hint") or ""),
            str(item.get("id") or ""),
        ]
    ).lower()
    return "connector" in role_text or "bundle" in role_text or "principal" in role_text


def _remove_blocks_by_ids(blocks: List[FreeformBlock], ids: set[str]) -> None:
    if not ids:
        return
    kept: List[FreeformBlock] = []
    for block in list(blocks or []):
        block_id = str(block.id or "").strip()
        if block_id in ids:
            continue
        if block.children:
            _remove_blocks_by_ids(block.children, ids)
        kept.append(block)
    blocks[:] = kept


def _infer_representative_node_count(item: Dict[str, Any], *, layer_index: int, total_layers: int) -> int:
    haystack = " ".join(
        [
            str(item.get("content_hint") or ""),
            str(item.get("visual_description") or ""),
            str(item.get("geometry_hint") or ""),
            str(item.get("semantic_role") or ""),
            str(item.get("id") or ""),
        ]
    ).lower()
    if "output" in haystack or layer_index == total_layers - 1:
        return 2
    if "input" in haystack or layer_index == 0:
        return 3
    if "hidden" in haystack:
        return 4
    if "four" in haystack or re.search(r"\b4\b", haystack):
        return 4
    if "three" in haystack or re.search(r"\b3\b", haystack):
        return 3
    if "two" in haystack or re.search(r"\b2\b", haystack):
        return 2
    return 3


def _layer_node_centers(*, bbox: Dict[str, float], count: int) -> List[tuple[float, float, float]]:
    diameter = min(max(bbox["w"] * 0.32, 0.010), max(0.014, bbox["h"] / max(count + 1, 3) * 0.48))
    top_pad = max(diameter * 0.8, bbox["h"] * 0.08)
    usable_h = max(diameter, bbox["h"] - top_pad * 2)
    if count == 1:
        y_offsets = [bbox["y"] + bbox["h"] / 2.0 - diameter / 2.0]
    else:
        step = usable_h / max(count - 1, 1)
        y_offsets = [bbox["y"] + top_pad + idx * step - diameter / 2.0 for idx in range(count)]
    x = bbox["x"] + bbox["w"] / 2.0 - diameter / 2.0
    centers: List[tuple[float, float, float]] = []
    for y in y_offsets:
        clamped_y = max(bbox["y"] + 0.004, min(y, bbox["y"] + bbox["h"] - diameter - 0.004))
        centers.append((x + diameter / 2.0, clamped_y + diameter / 2.0, diameter))
    return centers


def _build_layer_nodes(*, layer_items: List[Dict[str, Any]], existing_ids: set[str]) -> List[FreeformBlock]:
    blocks: List[FreeformBlock] = []
    total_layers = len(layer_items)
    for layer_index, layer in enumerate(layer_items):
        bbox = _bbox_from_raw(layer)
        count = _infer_representative_node_count(layer, layer_index=layer_index, total_layers=total_layers)
        count = max(2, min(4, count))
        centers = _layer_node_centers(bbox=bbox, count=count)
        style = {
            "background": "rgba(96,165,250,0.18)",
            "border_color": "#60A5FA",
            "box_shadow": "0 0 10px rgba(14,165,255,0.18)",
            "opacity": 1,
        }
        layer_id = str(layer.get("id") or f"layer_{layer_index+1}")
        for idx, (cx, cy, diameter) in enumerate(centers, start=1):
            block_id = f"{layer_id}_node_{idx:02d}"
            if block_id in existing_ids:
                continue
            blocks.append(
                FreeformBlock(
                    id=block_id,
                    type="circle",
                    role="diagram_node",
                    x=cx - diameter / 2.0,
                    y=cy - diameter / 2.0,
                    w=diameter,
                    h=diameter,
                    z_index=6,
                    style=style,
                )
            )
    return blocks


def _build_layer_connectors(
    *,
    layer_items: List[Dict[str, Any]],
    elements: List[Dict[str, Any]],
    existing_ids: set[str],
    base_z: int,
) -> List[FreeformBlock]:
    blocks: List[FreeformBlock] = []
    bundle_style = {}
    for item in elements:
        if str(item.get("type") or "").strip().lower() != "line":
            continue
        role_text = " ".join(
            [
                str(item.get("structural_role") or ""),
                str(item.get("semantic_role") or ""),
                str(item.get("id") or ""),
            ]
        ).lower()
        if "connect" in role_text or "bundle" in role_text or "topology" in role_text:
            bundle_style = _style_from_visual(item.get("style") if isinstance(item.get("style"), dict) else {})
            break
    line_style = {
        "border_color": str(bundle_style.get("border_color") or "#0EA5FF"),
        "opacity": min(float(bundle_style.get("opacity", 0.5) or 0.5), 0.55),
        "box_shadow": str(bundle_style.get("box_shadow") or "0 0 8px rgba(14,165,255,0.12)"),
        "color": str(bundle_style.get("color") or "#0EA5FF"),
        "line_weight": 1.0,
    }
    total_layers = len(layer_items)
    for layer_index, (left, right) in enumerate(zip(layer_items, layer_items[1:])):
        left_bbox = _bbox_from_raw(left)
        right_bbox = _bbox_from_raw(right)
        left_count = max(2, min(4, _infer_representative_node_count(left, layer_index=layer_index, total_layers=total_layers)))
        right_count = max(2, min(4, _infer_representative_node_count(right, layer_index=layer_index + 1, total_layers=total_layers)))
        left_centers = _layer_node_centers(bbox=left_bbox, count=left_count)
        right_centers = _layer_node_centers(bbox=right_bbox, count=right_count)
        pairs = [(li, ri) for li in range(len(left_centers)) for ri in range(len(right_centers))]
        cap = 12
        if len(pairs) > cap:
            step = max(1, len(pairs) // cap)
            pairs = pairs[::step][:cap]
        for idx, (left_node_idx, right_node_idx) in enumerate(pairs, start=1):
            lcx, lcy, _ = left_centers[left_node_idx]
            rcx, rcy, _ = right_centers[right_node_idx]
            block_id = f"{str(left.get('id') or 'layer')}_{str(right.get('id') or 'layer')}_conn_{idx:02d}"
            if block_id in existing_ids:
                continue
            x1 = lcx + left_bbox["w"] * 0.18
            x2 = rcx - right_bbox["w"] * 0.18
            blocks.append(
                FreeformBlock(
                    id=block_id,
                    type="line",
                    role="diagram_connector",
                    x=x1,
                    y=lcy,
                    x2=x2,
                    y2=rcy,
                    w=max(0.01, x2 - x1),
                    h=max(0.002, abs(rcy - lcy)),
                    z_index=3,
                    style=line_style,
                )
            )
    return blocks


def _connector_anchor_positions(bbox: Dict[str, float], node_count: int, anchors: int) -> List[float]:
    diameter = min(max(bbox["w"] * 0.32, 0.010), max(0.014, bbox["h"] / max(node_count + 1, 3) * 0.48))
    top_pad = max(diameter * 0.8, bbox["h"] * 0.08)
    usable_h = max(diameter, bbox["h"] - top_pad * 2)
    positions = []
    if node_count <= 1:
        positions = [bbox["y"] + bbox["h"] / 2.0]
    else:
        step = usable_h / max(node_count - 1, 1)
        positions = [bbox["y"] + top_pad + idx * step for idx in range(node_count)]
    if anchors >= len(positions):
        return positions
    if anchors == 2:
        return [positions[0], positions[-1]]
    mid = positions[len(positions) // 2]
    return [positions[0], mid, positions[-1]]


def _looks_like_circle_item(item: Dict[str, Any]) -> bool:
    role = " ".join(
        [
            str(item.get("semantic_role") or "").strip().lower(),
            str(item.get("structural_role") or "").strip().lower(),
            str(item.get("geometry_hint") or "").strip().lower(),
            " ".join(str(tag).strip().lower() for tag in list(item.get("relation_tags") or [])),
        ]
    )
    return any(token in role for token in ("node", "dot", "point", "circle", "badge"))


def _looks_like_rect_item(item: Dict[str, Any]) -> bool:
    elem_type = str(item.get("type") or "").strip().lower()
    if elem_type in {"panel", "shape", "decorative"}:
        return True
    role = " ".join(
        [
            str(item.get("semantic_role") or "").strip().lower(),
            str(item.get("structural_role") or "").strip().lower(),
            str(item.get("context_type") or "").strip().lower(),
        ]
    )
    return any(token in role for token in ("panel", "card", "container", "surface", "band", "axis_highlight"))


def _has_similar_visual_block(item: Dict[str, Any], bbox: Dict[str, float], existing: List[Dict[str, Any]]) -> bool:
    target_type = _normalized_target_type(item)
    target_role = str(item.get("structural_role") or item.get("semantic_role") or "").strip().lower()
    for entry in existing:
        block = entry["block"]
        block_type = str(block.type or "").strip().lower()
        if block_type != target_type:
            continue
        block_role = str(block.role or "").strip().lower()
        if target_role and block_role and target_role != block_role:
            continue
        dx = abs(float(entry["x"] or 0.0) - bbox["x"])
        dy = abs(float(entry["y"] or 0.0) - bbox["y"])
        dw = abs(float(entry["w"] or 0.0) - bbox["w"])
        dh = abs(float(entry["h"] or 0.0) - bbox["h"])
        if dx < 0.03 and dy < 0.03 and dw < 0.04 and dh < 0.04:
            return True
    return False


def _normalized_target_type(item: Dict[str, Any]) -> str:
    elem_type = str(item.get("type") or "").strip().lower()
    if elem_type == "line":
        return "line"
    if elem_type == "icon":
        return "icon"
    if elem_type == "circle" or _looks_like_circle_item(item):
        return "circle"
    return "rectangle"


def _iter_blocks(blocks: List[FreeformBlock]):
    for block in blocks:
        yield block
        if block.children:
            yield from _iter_blocks(list(block.children or []))


def _iter_blocks_with_page_geometry(
    blocks: List[FreeformBlock],
    *,
    parent_x: float = 0.0,
    parent_y: float = 0.0,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for block in blocks:
        coordinate_space = str(block.coordinate_space or "page").strip().lower()
        base_x = parent_x if coordinate_space == "parent" else 0.0
        base_y = parent_y if coordinate_space == "parent" else 0.0
        abs_x = base_x + float(block.x or 0.0)
        abs_y = base_y + float(block.y or 0.0)
        out.append(
            {
                "block": block,
                "x": abs_x,
                "y": abs_y,
                "w": float(block.w or 0.0),
                "h": float(block.h or 0.0),
            }
        )
        if block.children:
            out.extend(_iter_blocks_with_page_geometry(list(block.children or []), parent_x=abs_x, parent_y=abs_y))
    return out
