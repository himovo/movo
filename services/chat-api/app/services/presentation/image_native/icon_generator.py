from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

from app.llm.configured_multimodal import ConfiguredMultimodalClient, parse_json_object
from app.services.presentation.icon_library import load_inline_svg_map, resolve_icon_from_texts

logger = logging.getLogger(__name__)


def _icon_specs_from_analysis(analysis: Dict[str, Any], max_icons: int) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    seen: set[str] = set()
    groups = {
        str(group.get("id") or "").strip(): group
        for group in list((analysis or {}).get("groups") or [])
        if isinstance(group, dict) and str(group.get("id") or "").strip()
    }
    for elem in list((analysis or {}).get("elements") or []):
        if not isinstance(elem, dict):
            continue
        if str(elem.get("type") or "").strip().lower() != "icon":
            continue
        icon_id = str(elem.get("id") or "").strip()
        if not icon_id or icon_id in seen:
            continue
        style = elem.get("style") if isinstance(elem.get("style"), dict) else {}
        bbox = elem.get("bbox") if isinstance(elem.get("bbox"), dict) else {}
        group_id = str(elem.get("group_id") or "").strip()
        group = groups.get(group_id) if group_id else {}
        specs.append(
            {
                "id": icon_id,
                "semantic": str(elem.get("content_hint") or elem.get("semantic_role") or "icon").strip(),
                "bbox": bbox,
                "stroke": str(style.get("stroke") or style.get("color") or "#2563eb").strip(),
                "fill": str(style.get("fill") or "").strip(),
                "structural_role": str(elem.get("structural_role") or "").strip(),
                "context_type": str(elem.get("context_type") or "").strip(),
                "group_type": str(group.get("group_type") or "").strip(),
                "group_role": str(group.get("semantic_role") or "").strip(),
                "group_notes": str(group.get("notes") or "").strip(),
                "visual_description": str(elem.get("visual_description") or "").strip(),
                "geometry_hint": str(elem.get("geometry_hint") or "").strip(),
                "nearby_text": _nearest_text_for_bbox(analysis, bbox),
                "relation_tags": [str(tag).strip() for tag in list(elem.get("relation_tags") or []) if str(tag).strip()][:8],
            }
        )
        seen.add(icon_id)
        if len(specs) >= max_icons:
            break
    return specs


def _resolve_local_icon_name(spec: Dict[str, Any]) -> str:
    combined = _combined_icon_context(spec)
    semantic = str(spec.get("semantic") or "").strip()
    structural_role = str(spec.get("structural_role") or "").strip()
    context_type = str(spec.get("context_type") or "").strip()
    group_role = str(spec.get("group_role") or "").strip()
    visual_description = str(spec.get("visual_description") or "").strip()
    geometry_hint = str(spec.get("geometry_hint") or "").strip()
    nearby_text = str(spec.get("nearby_text") or "").strip()
    relation_tags = " ".join(str(tag).strip() for tag in list(spec.get("relation_tags") or []) if str(tag).strip())

    # Targeted overrides for image-native PPT rebuild semantics that are more
    # specific than the generic shared library keyword rules.
    if any(token in combined for token in ("gpu", "graphics card", "dual fans", "算力")):
        return "server"
    if "database" in combined or "cylinder" in combined or "数据" in combined:
        return "database"
    if any(token in combined for token in ("brain", "cognition", "neural", "神经")):
        return "brain"
    if "rocket" in combined:
        return "rocket"
    if any(token in combined for token in ("target", "bullseye")):
        return "target-arrow"
    if "cloud" in combined:
        return "cloud"
    if any(token in combined for token in ("line chart", "trend", "rising", "growth")):
        return "chart-line"
    if any(token in combined for token in ("distributed training", "distributed", "hexagon", "mesh", "honeycomb")):
        return "git-branch"
    if any(token in combined for token in ("cnn", "rnn", "node chain", "grid feeding", "recurrent")):
        return "git-branch"
    if any(token in combined for token in ("stacked layers", "stacked layer", "three offset", "offset diamond", "rhombus-like layers")):
        return "hierarchy"
    if any(token in combined for token in ("hexagon network", "hexagonal outer frame", "network icon", "network", "layers", "stacked")):
        return "network"
    if any(token in combined for token in ("head outline", "head profile", "representation")):
        return "brain"
    return resolve_icon_from_texts(
        semantic,
        visual_description,
        geometry_hint,
        nearby_text,
        structural_role,
        context_type,
        group_role,
        relation_tags,
        fallback="sparkles",
    )


def _combined_icon_context(spec: Dict[str, Any]) -> str:
    relation_tags = " ".join(str(tag).strip() for tag in list(spec.get("relation_tags") or []) if str(tag).strip())
    return " ".join(
        value
        for value in (
            str(spec.get("semantic") or "").strip(),
            str(spec.get("id") or "").strip(),
            str(spec.get("structural_role") or "").strip(),
            str(spec.get("context_type") or "").strip(),
            str(spec.get("group_type") or "").strip(),
            str(spec.get("group_role") or "").strip(),
            str(spec.get("group_notes") or "").strip(),
            str(spec.get("visual_description") or "").strip(),
            str(spec.get("geometry_hint") or "").strip(),
            str(spec.get("nearby_text") or "").strip(),
            relation_tags,
        )
        if value
    ).lower()


def _local_icon_svg_map(icon_specs: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    svg_library = load_inline_svg_map()
    out: Dict[str, Dict[str, str]] = {}
    for spec in icon_specs:
        if not isinstance(spec, dict):
            continue
        icon_id = str(spec.get("id") or "").strip()
        if not icon_id:
            continue
        micro = _micro_diagram_svg(spec)
        if micro:
            name, svg = micro
            out[icon_id] = {"svg": svg, "viewBox": "0 0 100 100", "icon_name": f"micro:{name}"}
            continue
        resolved = _resolve_local_icon_name(spec)
        svg = str(svg_library.get(resolved) or "").strip()
        if not svg:
            continue
        out[icon_id] = {"svg": svg, "viewBox": "0 0 24 24", "icon_name": resolved}
    return out


def _micro_diagram_svg(spec: Dict[str, Any]) -> tuple[str, str] | None:
    """Return deterministic SVG for complex technical icon-like diagrams.

    These templates bridge the gap between generic local icon libraries and
    unconstrained LLM-generated SVG. They are intentionally semantic and small:
    if the icon is a real micro-diagram, use a controlled geometry template;
    otherwise let the regular curated icon library handle it.
    """
    combined = _combined_icon_context(spec)
    if any(token in combined for token in ("cnn", "rnn", "node chain", "grid feeding", "recurrent")):
        return "cnn_rnn_flow", _svg_cnn_rnn_flow()
    if any(token in combined for token in ("gpu", "graphics card", "dual fans", "算力")):
        return "gpu_dual_fan", _svg_gpu_dual_fan()
    if any(token in combined for token in ("distributed training", "distributed", "hexagon", "mesh", "honeycomb", "分布式")):
        return "hex_mesh", _svg_hex_mesh()
    if any(token in combined for token in ("database flow", "data stream", "cylinder", "icon_data", "massive data", "海量数据")):
        return "database_stream", _svg_database_stream()
    if any(token in combined for token in ("stacked layers", "stacked layer", "three offset", "offset diamond", "rhombus-like layers", "icon_stage3_layers")):
        return "stacked_layers", _svg_stacked_layers()
    if any(token in combined for token in ("hexagon network", "network icon", "geometric network")):
        return "node_network", _svg_node_network()
    return None


def _svg_wrap(body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
        'fill="none" stroke="currentColor" stroke-width="4" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f"{body}</svg>"
    )


def _svg_gpu_dual_fan() -> str:
    return _svg_wrap(
        '<rect x="10" y="24" width="80" height="52" rx="5"/>'
        '<path d="M10 36H4M10 48H4M10 60H4M90 36h6M90 48h6M90 60h6"/>'
        '<circle cx="36" cy="50" r="14"/><circle cx="64" cy="50" r="14"/>'
        '<path d="M36 36v28M22 50h28M27 41l18 18M45 41L27 59"/>'
        '<path d="M64 36v28M50 50h28M55 41l18 18M73 41L55 59"/>'
        '<path d="M18 76v8M82 76v8M25 18h50"/>'
    )


def _svg_cnn_rnn_flow() -> str:
    cells = "".join(
        f'<rect x="{12 + col * 11}" y="{24 + row * 11}" width="8" height="8" rx="1"/>'
        for row in range(3)
        for col in range(3)
    )
    return _svg_wrap(
        cells
        + '<path d="M48 50h13M56 43l7 7-7 7"/>'
        '<circle cx="72" cy="32" r="6"/><circle cx="72" cy="50" r="6"/><circle cx="72" cy="68" r="6"/>'
        '<path d="M78 32c12 4 12 32 0 36M72 38v6M72 56v6M66 50H60"/>'
        '<path d="M22 76h56"/>'
    )


def _svg_hex_mesh() -> str:
    nodes = [(50, 18), (75, 32), (75, 62), (50, 78), (25, 62), (25, 32), (50, 48)]
    circles = "".join(f'<circle cx="{x}" cy="{y}" r="5"/>' for x, y in nodes)
    return _svg_wrap(
        '<path d="M50 18l25 14v30L50 78 25 62V32l25-14z"/>'
        '<path d="M50 18v30M75 32L50 48 25 32M75 62L50 48 25 62M50 78V48"/>'
        + circles
    )


def _svg_database_stream() -> str:
    dots = "".join(
        f'<circle cx="{60 + col * 9}" cy="{30 + row * 13}" r="2.2" fill="currentColor" stroke="none"/>'
        for row in range(4)
        for col in range(3)
    )
    return _svg_wrap(
        '<ellipse cx="32" cy="24" rx="18" ry="8"/>'
        '<path d="M14 24v44c0 4 8 8 18 8s18-4 18-8V24"/>'
        '<path d="M14 46c0 4 8 8 18 8s18-4 18-8M14 34c0 4 8 8 18 8s18-4 18-8"/>'
        '<path d="M52 30c10 0 14 0 22 0M52 50c10 0 14 0 22 0M52 70c10 0 14 0 22 0"/>'
        + dots
    )


def _svg_stacked_layers() -> str:
    return _svg_wrap(
        '<path d="M50 16l34 18-34 18-34-18 34-18z"/>'
        '<path d="M18 48l32 17 32-17M18 62l32 17 32-17"/>'
        '<path d="M18 34v7l32 17 32-17v-7"/>'
    )


def _svg_node_network() -> str:
    nodes = [(50, 16), (76, 32), (76, 66), (50, 84), (24, 66), (24, 32), (50, 50)]
    circles = "".join(f'<circle cx="{x}" cy="{y}" r="5"/>' for x, y in nodes)
    return _svg_wrap(
        '<path d="M50 16l26 16v34L50 84 24 66V32l26-16z"/>'
        '<path d="M50 50L50 16M50 50l26-18M50 50l26 16M50 50v34M50 50L24 66M50 50L24 32"/>'
        + circles
    )


def _nearest_text_for_bbox(analysis: Dict[str, Any], bbox: Dict[str, Any]) -> str:
    try:
        cx = float(bbox.get("x") or 0.0) + float(bbox.get("w") or 0.0) / 2.0
        cy = float(bbox.get("y") or 0.0) + float(bbox.get("h") or 0.0) / 2.0
    except Exception:
        return ""
    best_text = ""
    best_score = 999.0
    text_items: List[Dict[str, Any]] = []
    for raw in list((analysis or {}).get("text_elements") or []):
        if isinstance(raw, dict):
            text_items.append(raw)
    for raw in list((analysis or {}).get("elements") or []):
        if isinstance(raw, dict) and str(raw.get("type") or "").strip().lower() == "text":
            text_items.append(raw)
    for raw in text_items:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        text_bbox = raw.get("bbox") if isinstance(raw.get("bbox"), dict) else {}
        if not text or not text_bbox:
            continue
        try:
            tcx = float(text_bbox.get("x") or 0.0) + float(text_bbox.get("w") or 0.0) / 2.0
            tcy = float(text_bbox.get("y") or 0.0) + float(text_bbox.get("h") or 0.0) / 2.0
            dist = abs(cx - tcx) + abs(cy - tcy)
        except Exception:
            continue
        if dist < best_score:
            best_score = dist
            best_text = text
    return best_text[:120]


def build_icon_svg_prompt(icon_specs: List[Dict[str, Any]]) -> str:
    return (
        "You are a senior icon designer for editable PPT reconstruction.\n"
        "Generate complete inline SVG snippets for each icon spec.\n"
        "Return strict JSON only. Do not include markdown.\n\n"
        "Rules:\n"
        "- Output one icon for every input spec id.\n"
        "- SVG must be self-contained <svg>...</svg> markup with viewBox='0 0 100 100'.\n"
        "- Use transparent background.\n"
        "- Prefer stroke-based geometry with stroke-linecap='round' and stroke-linejoin='round'.\n"
        "- Preserve enough detail to be recognizable at small size.\n"
        "- Respect nearby_text, structural_role, and group context. Icons in the same group must not collapse into the same generic glyph unless the specs truly match.\n"
        "- Use visual_description and geometry_hint to preserve the original icon's concrete structure, not just a generic concept symbol.\n"
        "- If semantic says CNN/RNN, hexagon mesh, GPU chip, database flow, timeline node, or neural network, reflect those geometric parts explicitly.\n"
        "- Use currentColor for stroke/fill where possible so renderer can recolor it.\n\n"
        "Output shape:\n"
        "{\"icons\":[{\"id\":\"\",\"viewBox\":\"0 0 100 100\",\"svg\":\"<svg ...>...</svg>\",\"notes\":\"\"}]}\n\n"
        f"Icon specs:\n{json.dumps(icon_specs, ensure_ascii=False)}"
    )


class ImageNativeIconSvgGenerator:
    def __init__(self) -> None:
        self._client = ConfiguredMultimodalClient()

    async def generate_icons(
        self,
        *,
        analysis: Dict[str, Any],
        user_id: str,
        session_id: str,
        page_id: str,
        max_icons: int = 24,
    ) -> Dict[str, Dict[str, str]]:
        specs = _icon_specs_from_analysis(analysis, max_icons=max_icons)
        if not specs:
            return {}
        local_map = _local_icon_svg_map(specs)
        if len(local_map) == len(specs) or str(os.getenv("IMAGE_NATIVE_ICON_USE_LOCAL_ONLY", "1")).strip().lower() not in {"0", "false", "no"}:
            return local_map
        try:
            result = await self._client.call(
                prompt=build_icon_svg_prompt(specs),
                stage="presentation_image_native_icon_svg",
                intent="generation",
                user_id=user_id,
                session_id=session_id,
                request_payload_extra={"page_id": page_id, "icon_count": len(specs)},
            )
            payload = parse_json_object(result.output_text)
        except Exception:
            logger.warning("presentation_image_native_icon_svg_failed page_id=%s", page_id, exc_info=True)
            return {}

        out: Dict[str, Dict[str, str]] = {}
        for item in list(payload.get("icons") or []):
            if not isinstance(item, dict):
                continue
            icon_id = str(item.get("id") or "").strip()
            svg = str(item.get("svg") or "").strip()
            view_box = str(item.get("viewBox") or "0 0 100 100").strip()
            if icon_id and svg.startswith("<svg"):
                out[icon_id] = {"svg": svg, "viewBox": view_box}
        return {**local_map, **out}
