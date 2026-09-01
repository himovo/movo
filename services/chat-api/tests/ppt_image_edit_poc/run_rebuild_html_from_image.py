from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import httpx


ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = ROOT.parents[1]
ENV_PATH = BACKEND_ROOT / ".env"
DEFAULT_ENDPOINT = ""
DEFAULT_MODEL = "gpt-5.4"
SLIDE_W = 1536
SLIDE_H = 864

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.llm.providers.azure_gpt_image import AzureGptImageClient


def load_env(path: Path) -> Dict[str, str]:
    values = dict(os.environ)
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in values:
            values[key] = value
    return values


def parse_json_object(text: str) -> Dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("no JSON object found in model output")
    return json.loads(match.group(0))


def extract_output_text(resp_json: Dict[str, Any]) -> str:
    if isinstance(resp_json.get("output_text"), str) and resp_json.get("output_text"):
        return str(resp_json["output_text"])
    chunks: List[str] = []
    for item in resp_json.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            ctype = str(content.get("type") or "")
            if ctype in {"output_text", "text"} and content.get("text"):
                chunks.append(str(content["text"]))
    if chunks:
        return "\n".join(chunks)
    raise ValueError(f"cannot extract output text from response keys={list(resp_json.keys())}")


def extract_html(text: str) -> str:
    block = re.search(r"```html\s*([\s\S]*?)```", text, re.IGNORECASE)
    if block:
        return block.group(1).strip()
    generic = re.search(r"```[\w-]*\s*([\s\S]*?)```", text)
    if generic and "<html" in generic.group(1).lower():
        return generic.group(1).strip()
    if "<html" in text.lower():
        start = text.lower().find("<!doctype")
        if start < 0:
            start = text.lower().find("<html")
        return text[start:].strip()
    raise ValueError("no HTML content found in model output")


def call_responses(
    *,
    endpoint: str,
    model: str,
    api_key: str,
    prompt: str,
    image_b64: str | None,
    timeout_seconds: int,
) -> Dict[str, Any]:
    content: List[Dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    if image_b64:
        content.append({"type": "input_image", "image_url": f"data:image/png;base64,{image_b64}"})
    payload = {
        "model": model,
        "input": [{"role": "user", "content": content}],
        "temperature": 0,
    }
    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        resp = client.post(
            endpoint,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json=payload,
        )
    return {"status_code": resp.status_code, "text": resp.text, "json": (resp.json() if resp.status_code < 500 else None)}


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip()).strip("_") or "asset"


def estimate_wrapped_line_count(text: str, width_px: float, font_size_px: float) -> int:
    lines = max(1, str(text or "").count("\n") + 1)
    plain = str(text or "").replace("\n", " ").strip()
    if not plain:
        return lines
    avg_char_w = max(1.0, font_size_px * 0.55)
    chars_per_line = max(1, int(width_px / avg_char_w))
    wrapped = (len(plain) + chars_per_line - 1) // chars_per_line
    return max(lines, wrapped)


def analysis_layout_issues(analysis: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    for t in analysis.get("text_elements", []) or []:
        if not isinstance(t, dict):
            continue
        text = str(t.get("text", ""))
        bbox = t.get("bbox") or {}
        font = t.get("font") or {}
        width_px = float(bbox.get("w", 0.0) or 0.0) * SLIDE_W
        height_px = float(bbox.get("h", 0.0) or 0.0) * SLIDE_H
        size = float(font.get("size_px", 0) or 0)
        line_h = float(font.get("line_height", 1.2) or 1.2)
        if width_px <= 1 or height_px <= 1 or size <= 1:
            continue
        line_count = estimate_wrapped_line_count(text, width_px, size)
        required = size * line_h * line_count
        if required > height_px * 0.98:
            issues.append(
                f"text_overflow_risk:{t.get('id','')}:required={required:.1f}px>bbox_h={height_px:.1f}px lines={line_count}"
            )
    return issues


def build_analysis_reconcile_prompt(analysis: Dict[str, Any], issues: List[str]) -> str:
    return (
        "You are a layout verifier.\n"
        "Input JSON is from a slide reverse-design model.\n"
        "Your task is to normalize and repair it for production rendering.\n"
        "Return full JSON with same top-level schema and fields.\n"
        "Do not drop elements.\n"
        "Keep style/theme semantics unchanged.\n\n"
        "Repair rules:\n"
        "- Fix text bbox/font so text can fit without clipping under inferred wrapping.\n"
        "- Keep typography hierarchy stable (title > subtitle > body/label).\n"
        "- Keep all bbox within 0..1 bounds.\n"
        "- Preserve relative layout and reading flow.\n"
        "- If title split into parts, keep baseline continuity and avoid excessive vertical gaps.\n"
        "- Ensure badge-like containers have enough internal room for icon + divider + text.\n"
        "- Keep generation_plan.image_assets intact and add missing entries for image_model elements if needed.\n\n"
        f"Detected issues:\n{json.dumps(issues, ensure_ascii=False)}\n\n"
        f"Input JSON:\n{json.dumps(analysis, ensure_ascii=False)}"
    )


def generate_image_assets(
    analysis: Dict[str, Any],
    env: Dict[str, str],
    run_dir: Path,
) -> Dict[str, str]:
    assets_dir = run_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    out: Dict[str, str] = {}
    image_assets = ((analysis.get("generation_plan") or {}).get("image_assets") or [])
    for item in image_assets:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("id", "")).strip()
        prompt = str(item.get("prompt", "")).strip()
        size = str(item.get("size", "")).strip() or env.get("AZURE_IMAGE_SIZE", "1536x864")
        if not asset_id or not prompt:
            continue
        env_for_asset = dict(env)
        env_for_asset["AZURE_IMAGE_SIZE"] = size
        try:
            client = AzureGptImageClient(env=env_for_asset)
            result = client.generate_image(prompt)
            out_path = assets_dir / f"{safe_name(asset_id)}.png"
            out_path.write_bytes(result.image_bytes)
            out[asset_id] = str(out_path)
        except Exception as exc:
            print(f"asset_generation_failed id={asset_id}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return out


def build_analysis_prompt(icon_map: Dict[str, str]) -> str:
    return (
        "You are a senior visual designer and front-end architect.\n"
        "Analyze the provided slide image A and output a strict JSON object only.\n\n"
        "Goal:\n"
        "1) Describe overall style (tone, color system, background language, depth, lighting, typography).\n"
        "2) Decompose all visible elements.\n"
        "3) Decide for each element whether it should be produced by image model or HTML/CSS/SVG.\n"
        "4) For non-text visual assets that need generation, provide high-quality prompt drafts for gpt-image-2.\n"
        "5) Keep output generic and reusable, do not hardcode this specific case.\n\n"
        "Rules:\n"
        "- Coordinate system uses normalized values 0..1 relative to full canvas.\n"
        f"- Assume canvas size is {SLIDE_W}x{SLIDE_H}.\n"
        "- Every visible element must be listed in elements[] with bbox and z_index.\n"
        "- Text content in image should go to text_elements[].\n"
        "- Icons should prefer icon mapping when semantically matched.\n"
        "- For icon mapping, choose key in local_icon_key if matched, else empty string.\n\n"
        f"Available local icon map (key -> path): {json.dumps(icon_map, ensure_ascii=False)}\n\n"
        "Return strict JSON only with this shape:\n"
        "{"
        "\"canvas\":{\"w\":1536,\"h\":864,\"aspect\":\"16:9\"},"
        "\"style\":{\"theme\":\"\",\"mood\":\"\",\"palette\":[\"#000000\"],\"typography\":{\"family_hint\":\"sans\",\"weight_scale\":\"\"},\"background_language\":\"\",\"lighting\":\"\"},"
        "\"layout\":{\"grid_hint\":\"\",\"visual_flow\":\"\",\"safe_margins\":{\"left\":0.0,\"top\":0.0,\"right\":0.0,\"bottom\":0.0}},"
        "\"elements\":[{\"id\":\"\",\"type\":\"background|illustration|panel|shape|line|icon|chart|text\",\"render_by\":\"image_model|html_css_svg\",\"bbox\":{\"x\":0.0,\"y\":0.0,\"w\":0.0,\"h\":0.0},\"z_index\":1,\"style\":{\"fill\":\"\",\"stroke\":\"\",\"radius\":0,\"opacity\":1.0,\"shadow\":\"\"},\"notes\":\"\",\"asset_prompt\":\"\",\"local_icon_key\":\"\",\"icon_semantic\":\"gauge|diamond|pencil|chart|sparkles|rocket|unknown\"}],"
        "\"text_elements\":[{\"id\":\"\",\"bbox\":{\"x\":0.0,\"y\":0.0,\"w\":0.0,\"h\":0.0},\"z_index\":1,\"text\":\"\",\"role\":\"title|subtitle|body|label\",\"align\":\"left|center|right\",\"font\":{\"size_px\":48,\"weight\":700,\"family_hint\":\"sans\",\"color\":\"#FFFFFF\",\"line_height\":1.2,\"letter_spacing\":0}}],"
        "\"generation_plan\":{\"image_assets\":[{\"id\":\"\",\"purpose\":\"background|illustration\",\"prompt\":\"\",\"size\":\"1536x864\"}],\"html_constraints\":[\"\"],\"risks\":[\"\"],\"checks\":[\"\"]}"
        "}"
    )


def build_icon_svg_prompt(analysis: Dict[str, Any]) -> str:
    icon_elements = [e for e in analysis.get("elements", []) if str(e.get("type", "")).lower() == "icon"]
    icon_specs: List[Dict[str, Any]] = []
    for e in icon_elements:
        icon_specs.append(
            {
                "id": e.get("id", ""),
                "notes": e.get("notes", ""),
                "semantic": e.get("icon_semantic", ""),
                "stroke": ((e.get("style") or {}).get("stroke", "#00D9FF")),
                "bbox": e.get("bbox", {}),
            }
        )
    return (
        "You are a senior icon designer.\n"
        "Generate detailed, complete inline SVG for each icon spec.\n"
        "Do not simplify into minimal marks.\n"
        "Every icon must be visually complete and recognizable at small size.\n"
        "Use only stroke-based style unless explicitly needed.\n"
        "Keep background transparent.\n"
        "Output strict JSON only:\n"
        "{\"icons\":[{\"id\":\"\",\"viewBox\":\"0 0 100 100\",\"svg\":\"<svg ...>...</svg>\",\"notes\":\"\"}]}\n"
        "Rules:\n"
        "- Keep each icon centered and balanced in the viewBox.\n"
        "- Use stroke-linecap=round and stroke-linejoin=round where suitable.\n"
        "- Ensure line thickness and details survive at 24px display.\n"
        "- Match stroke color from spec unless clear reason to differ.\n"
        "- svg field must be a full <svg>...</svg> snippet.\n\n"
        f"Icon specs:\n{json.dumps(icon_specs, ensure_ascii=False)}"
    )


def build_html_prompt(
    analysis: Dict[str, Any],
    icon_svg_map: Dict[str, Dict[str, str]],
    image_asset_map: Dict[str, str],
) -> str:
    return (
        "Generate one self-contained HTML file (with embedded CSS and optional inline SVG) that reconstructs the slide.\n"
        "Use the provided JSON as single source of truth.\n"
        "Do not add unrelated visual elements.\n"
        "Do not remove listed elements.\n"
        "Canvas must be exactly 1536x864 inside .slide.\n"
        "Output HTML only.\n\n"
        "Requirements:\n"
        "- Keep all major layout blocks and hierarchy.\n"
        "- Text must be editable HTML text nodes, not baked into images.\n"
        "- Use local icon path when local_icon_key is present.\n"
        "- For icon elements, use provided icon_svg_map snippets directly; do not redraw or simplify icon geometry.\n"
        "- Keep icon SVG viewBox and preserveAspectRatio='xMidYMid meet'.\n"
        "- Ensure icon containers do not clip strokes.\n"
        "- Prefer real image assets from image_asset_map for image_model elements.\n"
        "- Use placeholders only when an asset id is truly missing.\n"
        "- Text nodes must avoid fixed-height clipping: use min-height/auto-height and width constraints.\n"
        "- For badges/chips containing icon+text, use flex layout and keep text inside container.\n"
        "- Avoid hardcoded per-case coordinates not grounded in JSON.\n"
        "- Include a debug comment at top listing unresolved image assets ids.\n\n"
        f"Design JSON:\n{json.dumps(analysis, ensure_ascii=False)}\n\n"
        f"icon_svg_map:\n{json.dumps(icon_svg_map, ensure_ascii=False)}\n\n"
        f"image_asset_map:\n{json.dumps(image_asset_map, ensure_ascii=False)}"
    )


def build_html_repair_prompt(
    analysis: Dict[str, Any],
    html: str,
    image_asset_map: Dict[str, str],
) -> str:
    return (
        "You are an HTML layout QA engineer.\n"
        "Repair the given HTML to improve generalization and prevent clipping/overflow.\n"
        "Keep same visual intent and hierarchy.\n"
        "Return full HTML only.\n\n"
        "Mandatory repairs:\n"
        "- Remove fixed-height clipping risk for text blocks.\n"
        "- Ensure multiline text uses proper line-height and can wrap.\n"
        "- Ensure badge/capsule text and border never overflow.\n"
        "- For image_model assets, use image_asset_map src when available.\n"
        "- Keep icon SVG complete and not clipped.\n"
        "- Keep canvas exactly 1536x864.\n\n"
        f"Design JSON:\n{json.dumps(analysis, ensure_ascii=False)}\n\n"
        f"image_asset_map:\n{json.dumps(image_asset_map, ensure_ascii=False)}\n\n"
        f"Current HTML:\n{html}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Given one image A, use GPT-5.4 to produce structured design JSON and reconstructed HTML."
    )
    parser.add_argument("--image", required=True, help="path to source image A")
    parser.add_argument("--endpoint", default="", help="Azure OpenAI responses endpoint")
    parser.add_argument("--model", default="", help="model/deployment name (default gpt-5.4)")
    parser.add_argument("--api-key", default="", help="api key or use env")
    parser.add_argument("--icon-map", default="", help="optional icon map json file, format: {\"key\":\"/path/icon.svg\"}")
    parser.add_argument("--timeout", type=int, default=180, help="http timeout seconds")
    parser.add_argument("--skip-image-assets", action="store_true", help="skip gpt-image-2 asset generation")
    args = parser.parse_args()

    image_path = Path(args.image).expanduser().resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"image not found: {image_path}")

    env = load_env(ENV_PATH)
    endpoint = (
        args.endpoint.strip()
        or env.get("AZURE_VLM_GPT54_ENDPOINT", "").strip()
        or env.get("AZURE_VLM_RESPONSES_ENDPOINT", "").strip()
        or DEFAULT_ENDPOINT
    )
    model = args.model.strip() or env.get("AZURE_VLM_GPT54_MODEL", "").strip() or DEFAULT_MODEL
    api_key = (
        args.api_key.strip()
        or env.get("AZURE_VLM_GPT54_API_KEY", "").strip()
        or env.get("AZURE_IMAGE_OPENAI_API_KEY", "").strip()
    )
    if not api_key:
        print("missing api key: --api-key or AZURE_VLM_GPT54_API_KEY (fallback AZURE_IMAGE_OPENAI_API_KEY)", file=sys.stderr)
        return 2

    icon_map: Dict[str, str] = {}
    if args.icon_map.strip():
        icon_map_path = Path(args.icon_map).expanduser().resolve()
        if not icon_map_path.exists():
            raise FileNotFoundError(f"icon map file not found: {icon_map_path}")
        icon_map = json.loads(icon_map_path.read_text(encoding="utf-8"))
        if not isinstance(icon_map, dict):
            raise ValueError("icon map json must be an object")

    run_dir = ROOT / "runs" / datetime.now().strftime("%Y%m%d_%H%M%S_html_rebuild")
    run_dir.mkdir(parents=True, exist_ok=True)
    analysis_raw_path = run_dir / "analysis_raw.json"
    analysis_text_path = run_dir / "analysis_text.txt"
    analysis_json_path = run_dir / "analysis.json"
    icons_raw_path = run_dir / "icons_raw.json"
    icons_text_path = run_dir / "icons_text.txt"
    icons_json_path = run_dir / "icons.json"
    html_raw_path = run_dir / "html_raw.json"
    html_text_path = run_dir / "html_text.txt"
    html_path = run_dir / "reconstructed.html"

    print(
        json.dumps(
            {"step": "start", "image": str(image_path), "endpoint": endpoint, "model": model, "run_dir": str(run_dir)},
            ensure_ascii=False,
        )
    )

    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")

    analysis_prompt = build_analysis_prompt(icon_map)
    analysis_resp = call_responses(
        endpoint=endpoint,
        model=model,
        api_key=api_key,
        prompt=analysis_prompt,
        image_b64=image_b64,
        timeout_seconds=args.timeout,
    )
    analysis_raw_path.write_text(analysis_resp["text"], encoding="utf-8")
    if analysis_resp["status_code"] >= 400:
        print(f"analysis http_{analysis_resp['status_code']}: {analysis_resp['text'][:800]}", file=sys.stderr)
        return 1

    analysis_json_payload = analysis_resp["json"] or json.loads(analysis_resp["text"])
    analysis_text = extract_output_text(analysis_json_payload)
    analysis_text_path.write_text(analysis_text, encoding="utf-8")
    analysis = parse_json_object(analysis_text)
    issues = analysis_layout_issues(analysis)
    if issues:
        reconcile_prompt = build_analysis_reconcile_prompt(analysis, issues)
        rec_resp = call_responses(
            endpoint=endpoint,
            model=model,
            api_key=api_key,
            prompt=reconcile_prompt,
            image_b64=None,
            timeout_seconds=args.timeout,
        )
        if rec_resp["status_code"] < 400:
            rec_payload = rec_resp["json"] or json.loads(rec_resp["text"])
            rec_text = extract_output_text(rec_payload)
            analysis = parse_json_object(rec_text)
            issues = analysis_layout_issues(analysis)
    analysis_json_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"step": "analysis_done", "analysis_json": str(analysis_json_path), "analysis_issues_after_reconcile": issues},
            ensure_ascii=False,
        )
    )

    image_asset_map: Dict[str, str] = {}
    if not args.skip_image_assets:
        image_asset_map = generate_image_assets(analysis, env, run_dir)
    (run_dir / "image_assets.json").write_text(json.dumps(image_asset_map, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"step": "image_assets_done", "count": len(image_asset_map)}, ensure_ascii=False))

    icon_prompt = build_icon_svg_prompt(analysis)
    icon_svg_map: Dict[str, Dict[str, str]] = {}
    try:
        icons_resp = call_responses(
            endpoint=endpoint,
            model=model,
            api_key=api_key,
            prompt=icon_prompt,
            image_b64=None,
            timeout_seconds=args.timeout,
        )
        icons_raw_path.write_text(icons_resp["text"], encoding="utf-8")
        if icons_resp["status_code"] < 400:
            icons_json_payload = icons_resp["json"] or json.loads(icons_resp["text"])
            icons_text = extract_output_text(icons_json_payload)
            icons_text_path.write_text(icons_text, encoding="utf-8")
            icons = parse_json_object(icons_text)
            icons_json_path.write_text(json.dumps(icons, ensure_ascii=False, indent=2), encoding="utf-8")
            for item in icons.get("icons", []) or []:
                if not isinstance(item, dict):
                    continue
                icon_id = str(item.get("id", "")).strip()
                svg = str(item.get("svg", "")).strip()
                view_box = str(item.get("viewBox", "")).strip() or "0 0 100 100"
                if icon_id and svg:
                    icon_svg_map[icon_id] = {"svg": svg, "viewBox": view_box}
        else:
            print(f"icons http_{icons_resp['status_code']}: {icons_resp['text'][:500]}", file=sys.stderr)
    except Exception as exc:
        print(f"icons parse failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    print(
        json.dumps(
            {"step": "icons_done", "icons_json": str(icons_json_path), "icon_count": len(icon_svg_map)},
            ensure_ascii=False,
        )
    )

    html_prompt = build_html_prompt(analysis, icon_svg_map, image_asset_map)
    html_resp = call_responses(
        endpoint=endpoint,
        model=model,
        api_key=api_key,
        prompt=html_prompt,
        image_b64=None,
        timeout_seconds=args.timeout,
    )
    html_raw_path.write_text(html_resp["text"], encoding="utf-8")
    if html_resp["status_code"] >= 400:
        print(f"html http_{html_resp['status_code']}: {html_resp['text'][:800]}", file=sys.stderr)
        return 1

    html_json_payload = html_resp["json"] or json.loads(html_resp["text"])
    html_text = extract_output_text(html_json_payload)
    html = extract_html(html_text)

    repair_prompt = build_html_repair_prompt(analysis, html, image_asset_map)
    repair_resp = call_responses(
        endpoint=endpoint,
        model=model,
        api_key=api_key,
        prompt=repair_prompt,
        image_b64=None,
        timeout_seconds=args.timeout,
    )
    if repair_resp["status_code"] < 400:
        repair_payload = repair_resp["json"] or json.loads(repair_resp["text"])
        repaired_text = extract_output_text(repair_payload)
        repaired_html = extract_html(repaired_text)
        if repaired_html and len(repaired_html) > 200:
            html = repaired_html
            html_text = repaired_text
    html_text_path.write_text(html_text, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    print(
        json.dumps(
            {
                "step": "done",
                "run_dir": str(run_dir),
                "analysis_json": str(analysis_json_path),
                "icons_json": str(icons_json_path),
                "reconstructed_html": str(html_path),
                "analysis_raw": str(analysis_raw_path),
                "icons_raw": str(icons_raw_path),
                "html_raw": str(html_raw_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
