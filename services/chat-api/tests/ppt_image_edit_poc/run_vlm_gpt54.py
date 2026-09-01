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
SCHEMA_PATH = ROOT / "slide_schema.json"
DEFAULT_ENDPOINT = ""
DEFAULT_MODEL = "gpt-5.4"


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


def read_schema() -> Dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def find_slide(schema: Dict[str, Any], slide_id: str) -> Dict[str, Any]:
    for slide in schema.get("slides", []):
        if str(slide.get("id")) == slide_id:
            return slide
    raise KeyError(f"slide_id not found: {slide_id}")


def parse_json_object(text: str) -> Dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("no JSON object found in model text output")
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


def choose_default_image(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"image not found: {path}")
        return path
    runs_dir = ROOT / "runs"
    if not runs_dir.exists():
        raise FileNotFoundError(f"runs dir not found: {runs_dir}")
    run_dirs = sorted([p for p in runs_dir.iterdir() if p.is_dir()])
    if not run_dirs:
        raise FileNotFoundError(f"no run directories under: {runs_dir}")
    latest = run_dirs[-1]
    cover_a = latest / "cover_A.png"
    if not cover_a.exists():
        raise FileNotFoundError(f"default image not found: {cover_a}")
    return cover_a


def build_prompt(slide: Dict[str, Any]) -> str:
    slots = [{"id": s.get("id"), "role": s.get("role"), "schema_text": s.get("text")} for s in slide.get("text_slots", [])]
    return (
        "You are locating editable text regions in a generated PowerPoint slide image.\n"
        "Do OCR and style extraction from the image.\n"
        "For each schema slot, infer text bounding box and style from the image.\n"
        "You must return one object for every schema slot id, with no omissions.\n"
        "font_size must be an integer in image pixels and must be measured per rendered line/span from visible glyph height, not copied or shared by slot.\n"
        "Use this definition: font_size is the typographic size whose uppercase glyph core height is closest to the observed glyph core height in the image.\n"
        "Estimate from glyph core only (ignore glow, shadow, blur, stroke, and outer effects).\n"
        "Different visual text heights must produce different font_size values, even within the same slot/title block.\n"
        "Do not force style consistency across lines: each line must have independently measured font_size.\n"
        "Also infer font_family_hint per item from this closed set: sans|serif|mono.\n"
        "Return font_weight as regular|bold and font_weight_value as numeric 100..900.\n"
        "Return line-level OCR results with one object per rendered line.\n"
        "Return span-level style results with one object per contiguous same-style segment in each line.\n"
        "If a line has mixed styles/colors, you must split into multiple spans and never collapse into dominant color.\n"
        "color must be core glyph fill color in strict #RRGGBB format (ignore glow/shadow).\n"
        "If uncertain, keep item and lower confidence instead of omitting.\n"
        "Do not copy style values from schema_text; infer from visual appearance in the image.\n"
        "Return strict JSON only with this shape: "
        "{\"text_slots\":[{\"id\":\"...\",\"bbox\":{\"x\":0,\"y\":0,\"w\":0,\"h\":0},"
        "\"align\":\"left|center|right\",\"font_size\":24,\"font_weight\":\"regular|bold\",\"font_weight_value\":700,\"font_family_hint\":\"sans\","
        "\"color\":\"#RRGGBB\",\"recognized_text\":\"...\",\"confidence\":0.0}],"
        "\"text_lines\":[{\"line_id\":\"...\",\"slot_id\":\"...\",\"order\":1,\"text\":\"...\","
        "\"bbox\":{\"x\":0,\"y\":0,\"w\":0,\"h\":0},\"align\":\"left|center|right\","
        "\"font_size\":24,\"font_weight\":\"regular|bold\",\"font_weight_value\":700,\"font_family_hint\":\"sans\",\"color\":\"#RRGGBB\",\"confidence\":0.0}],"
        "\"text_spans\":[{\"span_id\":\"...\",\"line_id\":\"...\",\"slot_id\":\"...\",\"order\":1,\"text\":\"...\","
        "\"char_start\":0,\"char_end\":2,"
        "\"bbox\":{\"x\":0,\"y\":0,\"w\":0,\"h\":0},\"font_size\":24,\"font_weight\":\"regular|bold\",\"font_weight_value\":700,\"font_family_hint\":\"sans\","
        "\"color\":\"#RRGGBB\",\"confidence\":0.0}]}\n"
        "Whitespace fidelity is mandatory: preserve spaces and punctuation exactly in span text.\n"
        "Do not trim span text.\n"
        "For each line, concatenating span.text by order must equal line.text exactly (character-for-character).\n"
        "char_start/char_end are 0-based, end-exclusive indexes into line.text.\n"
        "Coordinates must be normalized 0..1 relative to full slide.\n\n"
        f"Schema slots:\n{json.dumps(slots, ensure_ascii=False)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Call Azure Responses(gpt-5.4) for slide OCR/style extraction.")
    parser.add_argument("--slide-id", default="cover", help="slide id in slide_schema.json, default: cover")
    parser.add_argument("--image", default="", help="path to input image (default latest runs/*/cover_A.png)")
    parser.add_argument("--endpoint", default="", help="full responses endpoint with api-version query")
    parser.add_argument("--model", default="", help="model/deployment name, default gpt-5.4")
    parser.add_argument("--api-key", default="", help="api key (or set in env)")
    parser.add_argument("--timeout", type=int, default=120, help="http timeout seconds")
    args = parser.parse_args()

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

    image_path = choose_default_image(args.image.strip() or None)
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    schema = read_schema()
    slide = find_slide(schema, args.slide_id)
    prompt = build_prompt(slide)

    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": f"data:image/png;base64,{image_b64}"},
                ],
            }
        ],
        "temperature": 0,
    }

    run_dir = ROOT / "runs" / datetime.now().strftime("%Y%m%d_%H%M%S_gpt54")
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_path = run_dir / f"{args.slide_id}_gpt54_raw.json"
    text_path = run_dir / f"{args.slide_id}_gpt54_text.txt"
    layout_path = run_dir / f"{args.slide_id}_gpt54_layout.json"

    print(
        json.dumps(
            {
                "endpoint": endpoint,
                "model": model,
                "slide_id": args.slide_id,
                "image": str(image_path),
                "run_dir": str(run_dir),
            },
            ensure_ascii=False,
        )
    )

    with httpx.Client(timeout=args.timeout, follow_redirects=True) as client:
        resp = client.post(
            endpoint,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json=payload,
        )
    raw_path.write_text(resp.text, encoding="utf-8")
    if resp.status_code >= 400:
        print(f"http_{resp.status_code}: {resp.text[:800]}", file=sys.stderr)
        print(json.dumps({"run_dir": str(run_dir), "raw": str(raw_path)}, ensure_ascii=False, indent=2))
        return 1

    raw_json = resp.json()
    text = extract_output_text(raw_json)
    text_path.write_text(text, encoding="utf-8")
    layout = parse_json_object(text)
    layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"run_dir": str(run_dir), "raw": str(raw_path), "text": str(text_path), "layout": str(layout_path)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
