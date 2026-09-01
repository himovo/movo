from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import httpx
from PIL import Image, ImageDraw

import run_poc


ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = ROOT.parents[1]
ENV_PATH = BACKEND_ROOT / ".env"
SCHEMA_PATH = ROOT / "slide_schema.json"
SLIDE_W = run_poc.SLIDE_W
SLIDE_H = run_poc.SLIDE_H


def parse_json_object(text: str) -> Dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", text or "")
    if not match:
        raise ValueError("no JSON object found in planner response")
    return json.loads(match.group(0))


def extract_responses_output_text(resp_json: Dict[str, Any]) -> str:
    if isinstance(resp_json.get("output_text"), str) and resp_json.get("output_text"):
        return str(resp_json["output_text"])
    chunks: List[str] = []
    for item in resp_json.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            if str(content.get("type") or "") in {"output_text", "text"} and content.get("text"):
                chunks.append(str(content["text"]))
    if chunks:
        return "\n".join(chunks)
    raise ValueError(f"cannot extract output text from response keys={list(resp_json.keys())}")


def planner_prompt(slide: Dict[str, Any]) -> str:
    text_slots = [
        {
            "id": s.get("id"),
            "role": s.get("role"),
            "text": s.get("text"),
            "initial_bbox": {"x": s.get("x"), "y": s.get("y"), "w": s.get("w"), "h": s.get("h")},
            "initial_style": {
                "font_size": s.get("font_size"),
                "font_weight": s.get("font_weight"),
                "color": s.get("color"),
                "align": s.get("align"),
            },
        }
        for s in slide.get("text_slots", [])
    ]
    chart_slots = [
        {
            "id": c.get("id"),
            "type": c.get("type"),
            "title": c.get("title"),
            "initial_bbox": {"x": c.get("x"), "y": c.get("y"), "w": c.get("w"), "h": c.get("h")},
            "labels": c.get("labels"),
            "values": c.get("values"),
        }
        for c in slide.get("chart_slots", [])
    ]
    return (
        "You are a senior presentation layout designer.\n"
        "Plan a 16:9 slide layout BEFORE image generation.\n"
        "The image model will generate a premium no-text background B that must reserve your planned zones.\n"
        "PowerPoint will later overlay editable text/chart/table objects using the same coordinates.\n\n"
        "Hard rules:\n"
        "- Return strict JSON only.\n"
        "- Coordinates are normalized 0..1 relative to the whole slide.\n"
        "- Keep all text and chart boxes inside the safe area x=0.045..0.955, y=0.055..0.92.\n"
        "- Leave clear spacing between boxes; avoid overlaps.\n"
        "- Pick zones that an image model can render as empty containers or clean whitespace.\n"
        "- Do not ask the image model to render any text, letters, numbers, labels, tick labels, watermarks, logos, or pseudo text.\n"
        "- The PPT overlay uses schema text as source of truth; do not rewrite text.\n\n"
        "Composition contract:\n"
        "- The generated background B must look like a finished premium slide even before editable text is overlaid, but with all text areas empty.\n"
        "- Do not leave important text zones as bare black/empty space. A hint like 'clean whitespace' is not enough; specify the visible treatment that makes it designed.\n"
        "- If using negative space for text, design it as an intentional field with lighting falloff, vignette, gradient, nearby divider/accent, surrounding panel edge, or other visible structure.\n"
        "- For each important text group, plan either a supporting visual region (panel/card/field/divider/accent/badge) or a clearly described negative-space treatment.\n"
        "- Avoid tiny decorative elements that do not support the text hierarchy; decorative regions should anchor, balance, or frame the editable content.\n"
        "- Use visual regions to express the whole layout composition: content group, focal visual area, balance/flow, and secondary accents.\n\n"
        "Self-check before returning JSON:\n"
        "- Does B look like a complete premium slide background if all editable text is temporarily hidden? If not, revise the plan.\n"
        "- Does every title/headline/subtitle/metric/body slot have either an overlapping/nearby visual support region or an explicit designed negative-space treatment? If not, revise the plan.\n"
        "- Are visual regions substantial enough to create composition, not just tiny ornaments? If not, revise the plan.\n"
        "- Is the image prompt concise but specific enough for the image model to generate the full slide layout in one pass? If not, revise it.\n\n"
        "Return this JSON shape:\n"
        "{\n"
        "  \"slide_id\":\"...\",\n"
        "  \"design_intent\":\"...\",\n"
        "  \"background_prompt\":\"one concise no-text image prompt\",\n"
        "  \"negative_prompt\":\"text, letters, numbers, labels, watermarks, pseudo text\",\n"
        "  \"visual_regions\":[{\"id\":\"region_1\",\"type\":\"panel|card|divider|badge|icon|background_motif|chart_container|table_container|decorative\",\"bbox\":{\"x\":0,\"y\":0,\"w\":0,\"h\":0},\"style_hint\":\"...\"}],\n"
        "  \"text_slots\":[{\"id\":\"...\",\"role\":\"...\",\"bbox\":{\"x\":0,\"y\":0,\"w\":0,\"h\":0},\"align\":\"left|center|right\","
        "\"font_size\":24,\"font_weight\":\"regular|bold\",\"font_weight_value\":400,\"font_family_hint\":\"sans\","
        "\"color\":\"#RRGGBB\",\"container_hint\":\"designed empty panel/card/field or intentional negative-space treatment with visible lighting/accent/edge\"}],\n"
        "  \"text_lines\":[{\"line_id\":\"...\",\"slot_id\":\"...\",\"order\":1,\"text\":\"schema text or substring\","
        "\"bbox\":{\"x\":0,\"y\":0,\"w\":0,\"h\":0},\"align\":\"left|center|right\",\"font_size\":24,"
        "\"font_weight\":\"regular|bold\",\"font_weight_value\":400,\"font_family_hint\":\"sans\",\"color\":\"#RRGGBB\"}],\n"
        "  \"text_spans\":[{\"span_id\":\"...\",\"line_id\":\"...\",\"slot_id\":\"...\",\"order\":1,\"text\":\"...\","
        "\"char_start\":0,\"char_end\":4,\"bbox\":{\"x\":0,\"y\":0,\"w\":0,\"h\":0},\"font_size\":24,"
        "\"font_weight\":\"regular|bold\",\"font_weight_value\":400,\"font_family_hint\":\"sans\",\"color\":\"#RRGGBB\"}],\n"
        "  \"chart_slots\":[{\"id\":\"...\",\"bbox\":{\"x\":0,\"y\":0,\"w\":0,\"h\":0},\"container_hint\":\"empty chart panel\"}],\n"
        "  \"image_instructions\":[\"...\"]\n"
        "}\n\n"
        "Design guidance:\n"
        "- Infer the slide composition from the schema, slide type, content roles, and visual style request.\n"
        "- Plan a full visual system, not just text coordinates: empty panels, badges, dividers, chart containers, icon placeholders, visual anchors, lighting direction, and negative space.\n"
        "- Visual regions must be generated by the image model as part of B. Do not assume a later programmatic drawing pass will add decorative structure.\n"
        "- Adapt hierarchy to the slide type and text roles. Important message roles should get stronger size, contrast, and placement; support roles should be quieter.\n"
        "- For data slides, reserve clean chart/table zones and ask for empty chart panels without axis labels, tick labels, legends, numbers, or fake text.\n"
        "- If any text slot naturally benefits from multiple lines or mixed color emphasis, express that in text_lines/text_spans while preserving the exact schema text.\n\n"
        f"Slide id: {slide.get('id')}\n"
        f"Slide type: {slide.get('type')}\n"
        f"Visual style request: {slide.get('visual_prompt')}\n"
        f"Text slots:\n{json.dumps(text_slots, ensure_ascii=False, indent=2)}\n"
        f"Chart slots:\n{json.dumps(chart_slots, ensure_ascii=False, indent=2)}\n"
    )


def plan_layout_gpt54(
    slide: Dict[str, Any],
    env: Dict[str, str],
    log: run_poc.RunLogger,
    *,
    endpoint_override: str = "",
    model_override: str = "",
    api_key_override: str = "",
    timeout: int = 120,
) -> Dict[str, Any]:
    endpoint = (
        endpoint_override.strip()
        or env.get("AZURE_LAYOUT_GPT54_ENDPOINT", "").strip()
        or env.get("AZURE_VLM_GPT54_ENDPOINT", "").strip()
        or env.get("AZURE_VLM_RESPONSES_ENDPOINT", "").strip()
    )
    model = model_override.strip() or env.get("AZURE_LAYOUT_GPT54_MODEL", "").strip() or env.get("AZURE_VLM_GPT54_MODEL", "").strip() or "gpt-5.4"
    api_key = (
        api_key_override.strip()
        or env.get("AZURE_LAYOUT_GPT54_API_KEY", "").strip()
        or env.get("AZURE_VLM_GPT54_API_KEY", "").strip()
        or env.get("OPENAI_API_KEY", "").strip()
    )
    if not endpoint:
        raise RuntimeError("missing GPT-5.4 planner endpoint")
    if not api_key:
        raise RuntimeError("missing GPT-5.4 planner API key")
    prompt = planner_prompt(slide)
    payload = {
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        "temperature": 0,
    }
    started = time.monotonic()
    log.log(
        "layout_planner_request",
        slide=slide.get("id"),
        endpoint=endpoint,
        model=model,
        prompt_chars=len(prompt),
        prompt_preview=prompt[:700],
    )
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.post(endpoint, headers={"api-key": api_key, "Content-Type": "application/json"}, json=payload)
    log.log(
        "layout_planner_response",
        slide=slide.get("id"),
        status_code=resp.status_code,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        content_type=resp.headers.get("content-type", ""),
        request_id=resp.headers.get("x-ms-request-id", "") or resp.headers.get("apim-request-id", ""),
        response_preview=(resp.text or "")[:1200],
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"layout planner http_{resp.status_code}: {resp.text[:1200]}")
    text = extract_responses_output_text(resp.json())
    plan = parse_json_object(text)
    return postprocess_plan(normalize_plan(plan, slide), slide)


def fallback_plan(slide: Dict[str, Any]) -> Dict[str, Any]:
    return postprocess_plan(
        normalize_plan(
        {
            "slide_id": slide.get("id"),
            "design_intent": slide.get("visual_prompt", ""),
            "background_prompt": str(slide.get("visual_prompt", "")),
            "negative_prompt": "text, letters, numbers, labels, watermarks, pseudo text",
            "text_slots": [
                {
                    "id": slot.get("id"),
                    "role": slot.get("role", "body"),
                    "bbox": {"x": slot.get("x"), "y": slot.get("y"), "w": slot.get("w"), "h": slot.get("h")},
                    "align": slot.get("align", "left"),
                    "font_size": slot.get("font_size", 20),
                    "font_weight": slot.get("font_weight", "regular"),
                    "font_weight_value": 700 if str(slot.get("font_weight", "")).lower() == "bold" else 400,
                    "font_family_hint": "sans",
                    "color": slot.get("color", "#ffffff"),
                    "container_hint": "clean reserved area",
                }
                for slot in slide.get("text_slots", [])
            ],
            "chart_slots": [
                {"id": chart.get("id"), "bbox": {"x": chart.get("x"), "y": chart.get("y"), "w": chart.get("w"), "h": chart.get("h")}, "container_hint": "empty chart panel"}
                for chart in slide.get("chart_slots", [])
            ],
            "image_instructions": [],
        },
        slide,
        ),
        slide,
    )


def clamp(value: Any, default: float, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(lo, min(hi, parsed))


def normalize_plan(plan: Dict[str, Any], slide: Dict[str, Any]) -> Dict[str, Any]:
    fallback_text = {str(s.get("id")): s for s in slide.get("text_slots", [])}
    fallback_charts = {str(c.get("id")): c for c in slide.get("chart_slots", [])}
    text_items = []
    incoming_text = {str(item.get("id")): item for item in plan.get("text_slots", []) if isinstance(item, dict)}
    for slot_id, src in fallback_text.items():
        item = incoming_text.get(slot_id, {})
        bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else {}
        text_items.append(
            {
                "id": slot_id,
                "role": str(item.get("role") or src.get("role") or "body"),
                "bbox": {
                    "x": clamp(bbox.get("x"), float(src.get("x", 0.05)), 0.0, 0.96),
                    "y": clamp(bbox.get("y"), float(src.get("y", 0.08)), 0.0, 0.92),
                    "w": clamp(bbox.get("w"), float(src.get("w", 0.3)), 0.03, 0.95),
                    "h": clamp(bbox.get("h"), float(src.get("h", 0.08)), 0.03, 0.5),
                },
                "align": str(item.get("align") or src.get("align") or "left"),
                "font_size": int(clamp(item.get("font_size"), float(src.get("font_size", 20)), 8, 64)),
                "font_weight": str(item.get("font_weight") or src.get("font_weight") or "regular"),
                "font_weight_value": int(clamp(item.get("font_weight_value"), 700 if str(src.get("font_weight", "")).lower() == "bold" else 400, 100, 900)),
                "font_family_hint": str(item.get("font_family_hint") or "sans"),
                "color": str(item.get("color") or src.get("color") or "#ffffff"),
                "container_hint": str(item.get("container_hint") or "reserved text area"),
            }
        )
    chart_items = []
    incoming_charts = {str(item.get("id")): item for item in plan.get("chart_slots", []) if isinstance(item, dict)}
    for chart_id, src in fallback_charts.items():
        item = incoming_charts.get(chart_id, {})
        bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else {}
        chart_items.append(
            {
                "id": chart_id,
                "bbox": {
                    "x": clamp(bbox.get("x"), float(src.get("x", 0.1)), 0.0, 0.96),
                    "y": clamp(bbox.get("y"), float(src.get("y", 0.45)), 0.0, 0.92),
                    "w": clamp(bbox.get("w"), float(src.get("w", 0.7)), 0.05, 0.95),
                    "h": clamp(bbox.get("h"), float(src.get("h", 0.3)), 0.05, 0.7),
                },
                "container_hint": str(item.get("container_hint") or "empty chart panel"),
            }
        )
    visual_regions = []
    for item in list(plan.get("visual_regions") or []):
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else {}
        visual_regions.append(
            {
                "id": str(item.get("id") or f"region_{len(visual_regions)+1}"),
                "type": str(item.get("type") or "decorative"),
                "bbox": {
                    "x": clamp(bbox.get("x"), 0.08, 0.0, 0.96),
                    "y": clamp(bbox.get("y"), 0.1, 0.0, 0.92),
                    "w": clamp(bbox.get("w"), 0.2, 0.02, 0.95),
                    "h": clamp(bbox.get("h"), 0.12, 0.02, 0.85),
                },
                "style_hint": str(item.get("style_hint") or ""),
            }
        )
    out = {
        "slide_id": str(plan.get("slide_id") or slide.get("id")),
        "source": str(plan.get("source") or "gpt54_layout_planner"),
        "design_intent": str(plan.get("design_intent") or slide.get("visual_prompt") or ""),
        "background_prompt": str(plan.get("background_prompt") or slide.get("visual_prompt") or ""),
        "negative_prompt": str(plan.get("negative_prompt") or "text, letters, numbers, labels, watermarks, pseudo text"),
        "visual_regions": visual_regions,
        "text_slots": text_items,
        "chart_slots": chart_items,
        "image_instructions": [str(x) for x in list(plan.get("image_instructions") or []) if str(x).strip()],
    }
    for key in ("text_lines", "text_spans"):
        if isinstance(plan.get(key), list):
            out[key] = [dict(x) for x in plan.get(key, []) if isinstance(x, dict)]
    return out


def comparable_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def slot_style_lookup(plan: Dict[str, Any], slide: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    schema_text = {str(s.get("id")): s for s in slide.get("text_slots", [])}
    lookup: Dict[str, Dict[str, Any]] = {}
    for item in plan.get("text_slots", []):
        slot_id = str(item.get("id"))
        src = schema_text.get(slot_id, {})
        lookup[slot_id] = {
            "slot_id": slot_id,
            "bbox": dict(item.get("bbox") or {}),
            "align": item.get("align") or src.get("align", "left"),
            "font_size": item.get("font_size") or src.get("font_size", 20),
            "font_weight": item.get("font_weight") or src.get("font_weight", "regular"),
            "font_weight_value": item.get("font_weight_value") or (700 if str(src.get("font_weight", "")).lower() == "bold" else 400),
            "font_family_hint": item.get("font_family_hint") or "sans",
            "color": item.get("color") or src.get("color", "#ffffff"),
        }
    return lookup


def fallback_line(slot_id: str, text: str, style: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "line_id": f"{slot_id}_l1",
        "slot_id": slot_id,
        "order": 1,
        "text": text,
        "bbox": dict(style.get("bbox") or {}),
        "align": style.get("align", "left"),
        "font_size": style.get("font_size", 20),
        "font_weight": style.get("font_weight", "regular"),
        "font_weight_value": style.get("font_weight_value", 400),
        "font_family_hint": style.get("font_family_hint", "sans"),
        "color": style.get("color", "#ffffff"),
        "confidence": 1.0,
        "source": "schema_text_fallback",
    }


def sanitize_text_lines(plan: Dict[str, Any], slide: Dict[str, Any]) -> List[Dict[str, Any]]:
    schema_text = {str(s.get("id")): str(s.get("text") or "") for s in slide.get("text_slots", [])}
    styles = slot_style_lookup(plan, slide)
    raw_lines = [x for x in plan.get("text_lines", []) if isinstance(x, dict)]
    output: List[Dict[str, Any]] = []
    for slot_id, schema_value in schema_text.items():
        style = styles.get(slot_id)
        if not style:
            continue
        candidates = [dict(x) for x in raw_lines if str(x.get("slot_id")) == slot_id and str(x.get("text") or "").strip()]
        candidates.sort(key=lambda x: int(clamp(x.get("order"), len(output) + 1, 0, 999)))
        planned_text = comparable_text("".join(str(x.get("text") or "") for x in candidates))
        if not candidates or planned_text != comparable_text(schema_value):
            output.append(fallback_line(slot_id, schema_value, style))
            continue
        for idx, line in enumerate(candidates, start=1):
            bbox = line.get("bbox") if isinstance(line.get("bbox"), dict) else style.get("bbox") or {}
            output.append(
                {
                    "line_id": str(line.get("line_id") or f"{slot_id}_l{idx}"),
                    "slot_id": slot_id,
                    "order": idx,
                    "text": str(line.get("text") or ""),
                    "bbox": {
                        "x": clamp(bbox.get("x"), float((style.get("bbox") or {}).get("x", 0.05)), 0.0, 0.96),
                        "y": clamp(bbox.get("y"), float((style.get("bbox") or {}).get("y", 0.1)), 0.0, 0.92),
                        "w": clamp(bbox.get("w"), float((style.get("bbox") or {}).get("w", 0.3)), 0.03, 0.95),
                        "h": clamp(bbox.get("h"), float((style.get("bbox") or {}).get("h", 0.06)), 0.02, 0.35),
                    },
                    "align": line.get("align") or style.get("align", "left"),
                    "font_size": int(clamp(line.get("font_size"), float(style.get("font_size", 20)), 8, 72)),
                    "font_weight": line.get("font_weight") or style.get("font_weight", "regular"),
                    "font_weight_value": int(clamp(line.get("font_weight_value"), float(style.get("font_weight_value", 400)), 100, 900)),
                    "font_family_hint": line.get("font_family_hint") or style.get("font_family_hint", "sans"),
                    "color": line.get("color") or style.get("color", "#ffffff"),
                    "confidence": line.get("confidence", 1.0),
                    "source": "planner",
                }
            )
    return output


def fallback_span(line: Dict[str, Any]) -> Dict[str, Any]:
    text = str(line.get("text") or "")
    return {
        "span_id": f"{line.get('line_id')}_s1",
        "line_id": line.get("line_id"),
        "slot_id": line.get("slot_id"),
        "order": 1,
        "text": text,
        "char_start": 0,
        "char_end": len(text),
        "bbox": dict(line.get("bbox") or {}),
        "font_size": line.get("font_size", 20),
        "font_weight": line.get("font_weight", "regular"),
        "font_weight_value": line.get("font_weight_value", 400),
        "font_family_hint": line.get("font_family_hint", "sans"),
        "color": line.get("color", "#ffffff"),
        "confidence": line.get("confidence", 1.0),
        "source": "line_text_fallback",
    }


def sanitize_text_spans(plan: Dict[str, Any], text_lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    raw_spans = [x for x in plan.get("text_spans", []) if isinstance(x, dict)]
    output: List[Dict[str, Any]] = []
    for line in text_lines:
        line_id = str(line.get("line_id"))
        line_text = str(line.get("text") or "")
        candidates = [dict(x) for x in raw_spans if str(x.get("line_id")) == line_id and str(x.get("text") or "").strip()]
        candidates.sort(key=lambda x: int(clamp(x.get("order"), len(output) + 1, 0, 999)))
        planned_text = comparable_text("".join(str(x.get("text") or "") for x in candidates))
        if not candidates or planned_text != comparable_text(line_text):
            output.append(fallback_span(line))
            continue
        for idx, span in enumerate(candidates, start=1):
            bbox = span.get("bbox") if isinstance(span.get("bbox"), dict) else line.get("bbox") or {}
            text = str(span.get("text") or "")
            output.append(
                {
                    "span_id": str(span.get("span_id") or f"{line_id}_s{idx}"),
                    "line_id": line_id,
                    "slot_id": line.get("slot_id"),
                    "order": idx,
                    "text": text,
                    "char_start": int(clamp(span.get("char_start"), 0, 0, max(0, len(line_text)))),
                    "char_end": int(clamp(span.get("char_end"), len(text), 0, max(0, len(line_text)))),
                    "bbox": {
                        "x": clamp(bbox.get("x"), float((line.get("bbox") or {}).get("x", 0.05)), 0.0, 0.96),
                        "y": clamp(bbox.get("y"), float((line.get("bbox") or {}).get("y", 0.1)), 0.0, 0.92),
                        "w": clamp(bbox.get("w"), float((line.get("bbox") or {}).get("w", 0.3)), 0.01, 0.95),
                        "h": clamp(bbox.get("h"), float((line.get("bbox") or {}).get("h", 0.05)), 0.01, 0.35),
                    },
                    "font_size": int(clamp(span.get("font_size"), float(line.get("font_size", 20)), 8, 72)),
                    "font_weight": span.get("font_weight") or line.get("font_weight", "regular"),
                    "font_weight_value": int(clamp(span.get("font_weight_value"), float(line.get("font_weight_value", 400)), 100, 900)),
                    "font_family_hint": span.get("font_family_hint") or line.get("font_family_hint", "sans"),
                    "color": span.get("color") or line.get("color", "#ffffff"),
                    "confidence": span.get("confidence", line.get("confidence", 1.0)),
                    "source": "planner",
                }
            )
    return output


def rect_overlap_ratio(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    ax0 = clamp(a.get("x"), 0.0)
    ay0 = clamp(a.get("y"), 0.0)
    ax1 = ax0 + clamp(a.get("w"), 0.0)
    ay1 = ay0 + clamp(a.get("h"), 0.0)
    bx0 = clamp(b.get("x"), 0.0)
    by0 = clamp(b.get("y"), 0.0)
    bx1 = bx0 + clamp(b.get("w"), 0.0)
    by1 = by0 + clamp(b.get("h"), 0.0)
    iw = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    ih = max(0.0, min(ay1, by1) - max(ay0, by0))
    area = max(0.0001, (ax1 - ax0) * (ay1 - ay0))
    return (iw * ih) / area


def bbox_center_distance(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    ax = clamp(a.get("x"), 0.0) + clamp(a.get("w"), 0.0) / 2
    ay = clamp(a.get("y"), 0.0) + clamp(a.get("h"), 0.0) / 2
    bx = clamp(b.get("x"), 0.0) + clamp(b.get("w"), 0.0) / 2
    by = clamp(b.get("y"), 0.0) + clamp(b.get("h"), 0.0) / 2
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def plan_quality_warnings(plan: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    visual_regions = [r for r in plan.get("visual_regions", []) if isinstance(r, dict)]
    text_slots = [s for s in plan.get("text_slots", []) if isinstance(s, dict)]
    if len(visual_regions) < 3:
        warnings.append("Planner produced too few visual regions; B may look like a plain background instead of a complete slide layout.")
    large_regions = [r for r in visual_regions if (r.get("bbox") or {}).get("w", 0) * (r.get("bbox") or {}).get("h", 0) >= 0.08]
    if not large_regions:
        warnings.append("Planner did not produce a large visual anchor region; composition may lack structure.")
    for slot in text_slots:
        role = str(slot.get("role") or "").lower()
        if role not in {"title", "subtitle", "headline", "metric", "body"}:
            continue
        bbox = slot.get("bbox") or {}
        hint = str(slot.get("container_hint") or "").lower()
        supported = any(
            rect_overlap_ratio(bbox, region.get("bbox") or {}) >= 0.35 or bbox_center_distance(bbox, region.get("bbox") or {}) <= 0.18
            for region in visual_regions
        )
        has_intentional_negative_space = "negative" in hint and any(
            word in hint
            for word in (
                "light",
                "lighting",
                "vignette",
                "gradient",
                "divider",
                "accent",
                "panel",
                "edge",
                "glow",
                "frame",
                "structure",
            )
        )
        if not supported and not has_intentional_negative_space:
            warnings.append(
                f"Text slot '{slot.get('id')}' has no nearby/supporting visual region or explicit designed negative-space treatment; avoid a bare empty area."
            )
    return warnings


def postprocess_plan(plan: Dict[str, Any], slide: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(plan)
    out["source"] = str(out.get("source") or "gpt54_layout_planner")
    out["text_lines"] = sanitize_text_lines(out, slide)
    out["text_spans"] = sanitize_text_spans(out, out["text_lines"])
    out["postprocess"] = "generic_schema_text_validation"
    out["quality_warnings"] = plan_quality_warnings(out)
    return out


def layout_for_overlay(plan: Dict[str, Any], slide: Dict[str, Any]) -> Dict[str, Any]:
    schema_text = {str(s.get("id")): s for s in slide.get("text_slots", [])}
    text_slots = []
    text_lines = []
    text_spans = []
    for item in plan.get("text_slots", []):
        slot_id = str(item.get("id"))
        src = schema_text.get(slot_id, {})
        slot = {
            "id": slot_id,
            "role": item.get("role") or src.get("role", "body"),
            "bbox": dict(item.get("bbox") or {}),
            "align": item.get("align") or src.get("align", "left"),
            "font_size": item.get("font_size") or src.get("font_size", 20),
            "font_weight": item.get("font_weight") or src.get("font_weight", "regular"),
            "font_weight_value": item.get("font_weight_value") or (700 if str(src.get("font_weight", "")).lower() == "bold" else 400),
            "font_family_hint": item.get("font_family_hint") or "sans",
            "color": item.get("color") or src.get("color", "#ffffff"),
        }
        text_slots.append(slot)
    if isinstance(plan.get("text_lines"), list) and plan.get("text_lines"):
        text_lines = [dict(x, confidence=x.get("confidence", 1.0)) for x in plan.get("text_lines", []) if isinstance(x, dict)]
    else:
        for slot in text_slots:
            slot_id = str(slot.get("id"))
            src = schema_text.get(slot_id, {})
            line_id = f"{slot_id}_l1"
            text = str(src.get("text", ""))
            text_lines.append({**slot, "line_id": line_id, "slot_id": slot_id, "order": 1, "text": text, "confidence": 1.0})
    if isinstance(plan.get("text_spans"), list) and plan.get("text_spans"):
        text_spans = [dict(x, confidence=x.get("confidence", 1.0)) for x in plan.get("text_spans", []) if isinstance(x, dict)]
    else:
        for line in text_lines:
            text = str(line.get("text", ""))
            text_spans.append(
                {
                    **line,
                    "span_id": f"{line.get('line_id')}_s1",
                    "line_id": line.get("line_id"),
                    "slot_id": line.get("slot_id"),
                    "order": 1,
                    "text": text,
                    "char_start": 0,
                    "char_end": len(text),
                    "confidence": 1.0,
                }
            )
    return {"source": "layout_first_plan", "text_slots": text_slots, "text_lines": text_lines, "text_spans": text_spans}


def apply_plan_to_slide(slide: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(slide)
    by_text_id = {str(item.get("id")): item for item in plan.get("text_slots", [])}
    for slot in out.get("text_slots", []):
        item = by_text_id.get(str(slot.get("id")))
        if not item:
            continue
        bbox = item.get("bbox") or {}
        slot.update(
            {
                "x": bbox.get("x", slot.get("x")),
                "y": bbox.get("y", slot.get("y")),
                "w": bbox.get("w", slot.get("w")),
                "h": bbox.get("h", slot.get("h")),
                "font_size": item.get("font_size", slot.get("font_size")),
                "font_weight": item.get("font_weight", slot.get("font_weight")),
                "font_weight_value": item.get("font_weight_value", slot.get("font_weight_value")),
                "font_family_hint": item.get("font_family_hint", slot.get("font_family_hint", "sans")),
                "color": item.get("color", slot.get("color")),
                "align": item.get("align", slot.get("align")),
            }
        )
    by_chart_id = {str(item.get("id")): item for item in plan.get("chart_slots", [])}
    for chart in out.get("chart_slots", []):
        item = by_chart_id.get(str(chart.get("id")))
        if not item:
            continue
        bbox = item.get("bbox") or {}
        chart.update({"x": bbox.get("x", chart.get("x")), "y": bbox.get("y", chart.get("y")), "w": bbox.get("w", chart.get("w")), "h": bbox.get("h", chart.get("h"))})
    return out


def background_prompt_from_plan(slide: Dict[str, Any], plan: Dict[str, Any]) -> str:
    region_lines = []
    for item in plan.get("visual_regions", []):
        bbox = item.get("bbox") or {}
        region_lines.append(
            f"- {item.get('id')} ({item.get('type')}): x={bbox.get('x'):.3f}, y={bbox.get('y'):.3f}, "
            f"w={bbox.get('w'):.3f}, h={bbox.get('h'):.3f}; {item.get('style_hint')}"
        )
    text_reservations = []
    for item in plan.get("text_slots", []):
        bbox = item.get("bbox") or {}
        text_reservations.append(
            f"- {item.get('id')} ({item.get('role')}): x={bbox.get('x'):.3f}, y={bbox.get('y'):.3f}, "
            f"w={bbox.get('w'):.3f}, h={bbox.get('h'):.3f}; {item.get('container_hint')}"
        )
    chart_reservations = []
    for item in plan.get("chart_slots", []):
        bbox = item.get("bbox") or {}
        chart_reservations.append(
            f"- {item.get('id')}: x={bbox.get('x'):.3f}, y={bbox.get('y'):.3f}, w={bbox.get('w'):.3f}, h={bbox.get('h'):.3f}; {item.get('container_hint')}"
        )
    instructions = "\n".join(plan.get("image_instructions") or [])
    composition_brief = (
        "Use the planned visual regions as a composition brief, not as a technical wireframe. "
        "Create an integrated slide background with visible hierarchy: a readable editable-content zone, a focal visual zone, and balancing accents. "
        "Reserved text zones should feel intentionally designed through empty panels, negative-space lighting, surrounding dividers, or soft container structure, not as abandoned blank areas."
    )
    return (
        "Create a premium 16:9 PowerPoint slide BACKGROUND ONLY.\n"
        "The slide must contain the full visual design: background, empty cards, empty chart panels, non-text icons, lighting, shadows, and decorative elements.\n"
        "Every planned visual region below must be part of this generated image; there is no later programmatic drawing pass for decorative structure.\n"
        "ABSOLUTELY NO TEXT: no letters, no numbers, no labels, no tick labels, no UI text, no watermark, no logo wordmark, no pseudo text, no readable glyphs.\n"
        "Reserve clean empty zones for editable PowerPoint objects that will be overlaid later.\n"
        "Keep reserved zones calm and readable, but integrated into the visual design through panels, negative space, light falloff, or container structure.\n\n"
        f"Composition brief: {composition_brief}\n\n"
        f"Visual style: {plan.get('background_prompt') or slide.get('visual_prompt')}\n"
        f"Design intent: {plan.get('design_intent')}\n\n"
        "Planned visual structure / empty containers:\n"
        + ("\n".join(region_lines) if region_lines else "- none")
        + "\n\n"
        "Reserved text zones:\n"
        + ("\n".join(text_reservations) if text_reservations else "- none")
        + "\n\nReserved chart/table zones:\n"
        + ("\n".join(chart_reservations) if chart_reservations else "- none")
        + "\n\nAdditional instructions:\n"
        + (instructions if instructions else "- Use refined executive presentation design with consistent visual hierarchy.")
    )


def dry_run_background(plan: Dict[str, Any], out_path: Path) -> None:
    img = Image.new("RGB", (SLIDE_W, SLIDE_H), "#0f172a")
    draw = ImageDraw.Draw(img, "RGBA")
    for i in range(0, SLIDE_W, 56):
        alpha = int(22 * (1 - i / SLIDE_W))
        draw.line([(i, 0), (i - 220, SLIDE_H)], fill=(56, 189, 248, max(0, alpha)), width=2)
    draw.ellipse((980, -180, 1740, 580), fill=(14, 165, 233, 42))
    draw.ellipse((780, 500, 1320, 1020), fill=(34, 197, 94, 24))
    draw.rounded_rectangle((70, 70, SLIDE_W - 70, SLIDE_H - 70), radius=34, outline=(148, 163, 184, 60), width=2)
    for item in plan.get("visual_regions", []):
        x, y, w, h = run_poc.rect_px(item.get("bbox") or {})
        region_type = str(item.get("type") or "")
        radius = max(8, min(28, h // 4))
        fill = (2, 8, 23, 95) if "panel" in region_type or "card" in region_type else (14, 165, 233, 28)
        draw.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=fill, outline=(125, 211, 252, 90), width=2)
    for item in plan.get("text_slots", []):
        x, y, w, h = run_poc.rect_px(item.get("bbox") or {})
        draw.rounded_rectangle((x - 14, y - 10, x + w + 14, y + h + 10), radius=18, fill=(15, 23, 42, 70), outline=(148, 163, 184, 45), width=1)
    for item in plan.get("chart_slots", []):
        x, y, w, h = run_poc.rect_px(item.get("bbox") or {})
        draw.rounded_rectangle((x, y, x + w, y + h), radius=26, fill=(2, 6, 23, 120), outline=(125, 211, 252, 100), width=2)
    img.save(out_path)


def build_html(schema: Dict[str, Any], run_dir: Path, manifest: Dict[str, Any]) -> None:
    rows = []
    for slide in manifest.get("slides", []):
        sid = slide["id"]
        rows.append(
            f"""
            <section class="slide-block">
              <h2>{sid}: {slide.get('type', '')}</h2>
              <div class="grid">
                <figure><img src="{sid}_B.png"><figcaption>B: no-text image2 background</figcaption></figure>
                <figure><img src="{sid}_C_preview.png"><figcaption>C preview: B + editable overlay</figcaption></figure>
              </div>
              <details><summary>Layout plan JSON</summary><pre>{json.dumps(manifest.get('plans', {}).get(sid, {}), ensure_ascii=False, indent=2)}</pre></details>
            </section>
            """
        )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Layout-First PPT Image PoC</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0b1020; color: #e5e7eb; }}
    header {{ padding: 28px 36px; border-bottom: 1px solid rgba(255,255,255,.12); }}
    h1 {{ margin: 0 0 10px; font-size: 24px; }}
    a {{ color: #67e8f9; }}
    .meta {{ color: #94a3b8; font-size: 14px; }}
    .slide-block {{ padding: 28px 36px 38px; border-bottom: 1px solid rgba(255,255,255,.1); }}
    h2 {{ margin: 0 0 18px; font-size: 18px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(320px, 1fr)); gap: 18px; }}
    figure {{ margin: 0; background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); border-radius: 8px; overflow: hidden; }}
    img {{ display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: contain; background: #020617; }}
    figcaption {{ padding: 10px 12px; color: #cbd5e1; font-size: 13px; }}
    details {{ margin-top: 16px; }}
    pre {{ overflow: auto; background: #020617; padding: 14px; border-radius: 8px; color: #d1d5db; }}
  </style>
</head>
<body>
  <header>
    <h1>Layout-First PPT Image PoC</h1>
    <div class="meta">PPTX: <a href="layout_first_poc.pptx">layout_first_poc.pptx</a> · Manifest: <a href="manifest.json">manifest.json</a> · Log: <a href="api_debug.log">api_debug.log</a></div>
  </header>
  {''.join(rows)}
</body>
</html>"""
    (run_dir / "comparison.html").write_text(html, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Layout-first PoC: GPT-5.4 plans layout, image2 generates no-text B, PPT overlays editable objects.")
    parser.add_argument("--mode", choices=["api", "dry-run", "auto"], default="auto")
    parser.add_argument("--max-slides", type=int, default=1)
    parser.add_argument("--planner-endpoint", default="")
    parser.add_argument("--planner-model", default="")
    parser.add_argument("--planner-api-key", default="")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    env = run_poc.load_env(ENV_PATH)
    schema = run_poc.read_schema()
    run_dir = ROOT / "runs" / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_layout_first")
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_poc.RunLogger(run_dir / "api_debug.log")
    use_api = args.mode == "api" or (args.mode == "auto" and bool(env.get("AZURE_IMAGE_OPENAI_API_KEY", "").strip()))
    slides = list(schema.get("slides", []))
    if args.max_slides > 0:
        slides = slides[: args.max_slides]

    planned_schema = deepcopy(schema)
    planned_schema["slides"] = []
    plans: Dict[str, Any] = {}
    layouts: Dict[str, Any] = {}
    backgrounds: Dict[str, Path] = {}
    manifest: Dict[str, Any] = {
        "mode": "api" if use_api else "dry-run",
        "planner": "gpt-5.4",
        "slides": [{"id": s.get("id"), "type": s.get("type")} for s in slides],
        "plans": plans,
        "layouts": layouts,
        "errors": [],
        "env_summary": run_poc.env_summary(env),
    }
    log.log("layout_first_run_start", run_dir=str(run_dir), mode=manifest["mode"], max_slides=args.max_slides, env=manifest["env_summary"])

    for slide in slides:
        sid = run_poc.safe_name(str(slide.get("id") or "slide"))
        log.log("slide_start", slide=sid, type=slide.get("type", ""))
        try:
            if use_api:
                plan = plan_layout_gpt54(
                    slide,
                    env,
                    log,
                    endpoint_override=args.planner_endpoint,
                    model_override=args.planner_model,
                    api_key_override=args.planner_api_key,
                    timeout=args.timeout,
                )
            else:
                plan = fallback_plan(slide)
                plan["source"] = "schema_fallback_dry_run"
                log.log("layout_planner_dry_run", slide=sid)
        except Exception as exc:
            log.log("layout_planner_fallback", slide=sid, exception_type=type(exc).__name__, error=str(exc))
            manifest["errors"].append({"slide": sid, "stage": "layout_planner", "error": str(exc)})
            plan = fallback_plan(slide)
            plan["source"] = "schema_fallback_after_error"
        plans[sid] = plan
        (run_dir / f"{sid}_layout_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

        planned_slide = apply_plan_to_slide(slide, plan)
        planned_schema["slides"].append(planned_slide)
        layout = layout_for_overlay(plan, planned_slide)
        layouts[sid] = layout
        (run_dir / f"{sid}_overlay_layout.json").write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")

        b_path = run_dir / f"{sid}_B.png"
        prompt = background_prompt_from_plan(planned_slide, plan)
        (run_dir / f"{sid}_background_prompt.txt").write_text(prompt, encoding="utf-8")
        try:
            if use_api:
                manifest.setdefault("background_generation", {})[sid] = run_poc.generate_image_api(prompt, b_path, env, log)
            else:
                dry_run_background(plan, b_path)
                manifest.setdefault("background_generation", {})[sid] = {"ok": True, "dry_run": True}
        except Exception as exc:
            log.log("background_generation_fallback", slide=sid, exception_type=type(exc).__name__, error=str(exc))
            manifest["errors"].append({"slide": sid, "stage": "background_generation", "error": str(exc)})
            dry_run_background(plan, b_path)
            manifest.setdefault("background_generation", {})[sid] = {"ok": False, "fallback": "dry_run_background", "error": str(exc)}
        run_poc.normalize_slide_image(b_path)
        log.log("background_postprocess", slide=sid, action="normalize_only", note="B is not decorated by Python; all visual structure must come from image2.")
        log.log("background_ready", slide=sid, path=str(b_path), bytes=b_path.stat().st_size)
        backgrounds[str(slide.get("id"))] = b_path

        c_preview = run_dir / f"{sid}_C_preview.png"
        run_poc.render_overlay_preview(b_path, planned_slide, layout, c_preview)
        log.log("preview_ready", slide=sid, path=str(c_preview), bytes=c_preview.stat().st_size)

    planned_schema_path = run_dir / "planned_slide_schema.json"
    planned_schema_path.write_text(json.dumps(planned_schema, ensure_ascii=False, indent=2), encoding="utf-8")
    pptx_path = run_dir / "layout_first_poc.pptx"
    run_poc.make_pptx(planned_schema, layouts, backgrounds, pptx_path)
    log.log("pptx_ready", path=str(pptx_path), bytes=pptx_path.stat().st_size)
    manifest["planned_schema"] = str(planned_schema_path)
    manifest["pptx"] = str(pptx_path)
    manifest["html"] = str(run_dir / "comparison.html")
    manifest["log"] = str(run_dir / "api_debug.log")
    manifest["api_events"] = log.events
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    build_html(planned_schema, run_dir, manifest)
    manifest["api_events"] = log.events
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "html": str(run_dir / "comparison.html"), "pptx": str(pptx_path), "log": str(run_dir / "api_debug.log")}, ensure_ascii=False, indent=2))
    return 2 if manifest["errors"] and args.mode == "api" else 0


if __name__ == "__main__":
    raise SystemExit(main())
