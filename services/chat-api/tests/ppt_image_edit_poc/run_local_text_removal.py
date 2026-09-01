from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def load_run_poc_module(script_dir: Path):
    run_poc_path = script_dir / "run_poc.py"
    spec = importlib.util.spec_from_file_location("ppt_image_edit_poc_run_poc", run_poc_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from: {run_poc_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def guess_layout_path(image_a: Path) -> Path | None:
    parent = image_a.parent
    stem = image_a.stem
    candidates = [
        parent / f"{stem}_layout.json",
        parent / f"{stem.replace('_A', '')}_layout.json",
        parent / f"{stem.replace('_A', '')}_gpt54_layout.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    all_layouts = sorted(parent.glob("*_layout.json"))
    return all_layouts[0] if all_layouts else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Local text removal for an existing A image")
    parser.add_argument("--image-a", required=True, help="Path to existing A image (e.g. cover_A.png)")
    parser.add_argument("--layout-json", default="", help="Path to layout json (optional, auto-detect if omitted)")
    parser.add_argument("--out-b", default="", help="Output B image path (default: <A_stem>_B_local.png)")
    parser.add_argument("--out-mask", default="", help="Output mask path (default: <A_stem>_mask_local.png)")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    poc = load_run_poc_module(script_dir)

    image_a = Path(args.image_a).expanduser().resolve()
    if not image_a.exists():
        raise FileNotFoundError(f"image not found: {image_a}")

    layout_path = Path(args.layout_json).expanduser().resolve() if args.layout_json else guess_layout_path(image_a)
    if layout_path is None or not layout_path.exists():
        raise FileNotFoundError("layout json not found. pass --layout-json explicitly")

    out_mask = (
        Path(args.out_mask).expanduser().resolve()
        if args.out_mask
        else image_a.with_name(f"{image_a.stem}_mask_local.png")
    )
    out_b = (
        Path(args.out_b).expanduser().resolve()
        if args.out_b
        else image_a.with_name(f"{image_a.stem}_B_local.png")
    )

    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    if not any(layout.get(k) for k in ["text_spans", "text_lines", "text_slots"]):
        raise ValueError(f"layout has no usable text regions: {layout_path}")

    poc.build_mask(layout, out_mask)
    poc.local_inpaint_text(image_a, out_mask, out_b, log=None)
    poc.normalize_slide_image(out_b)

    print(json.dumps({
        "image_a": str(image_a),
        "layout_json": str(layout_path),
        "mask": str(out_mask),
        "b": str(out_b),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
