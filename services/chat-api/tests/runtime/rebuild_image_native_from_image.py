from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TEST_ROOT = PROJECT_ROOT / "test" / "PPT"
DEFAULT_IMAGE_CACHE = DEFAULT_TEST_ROOT / "images"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.presentation.contracts import (
    DeckBrief,
    DesignTokens,
    FreeformDeckBlueprint,
    PageBrief,
)
from app.services.presentation.html_renderer import HtmlRenderer
from app.services.presentation.image_native.blueprint_mapper import (
    BlueprintComposer,
    fallback_page_from_analysis,
)
from app.services.presentation.image_native.blueprint_postprocess import postprocess_image_native_page
from app.services.presentation.image_native.contracts import ImageNativePagePlan, PlannedText
from app.services.presentation.image_native.icon_generator import ImageNativeIconSvgGenerator
from app.services.presentation.image_native.visual_analyzer import VisualSemanticAnalyzer
from app.services.presentation.structural_sanitizer import sanitize_deck
from app.services.presentation.theme_factory_catalog import build_freeform_theme_from_design_tokens


def _parse_texts(value: str) -> List[PlannedText]:
    raw = str(value or "").strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("--texts must be a JSON list")
    out: List[PlannedText] = []
    for idx, item in enumerate(parsed, start=1):
        if isinstance(item, str):
            out.append(PlannedText(id=f"text_{idx}", role="body", text=item, priority=5))
        elif isinstance(item, dict):
            out.append(PlannedText.model_validate(item))
    return out


def _load_page_plan(args: argparse.Namespace) -> ImageNativePagePlan:
    if args.page_plan:
        return ImageNativePagePlan.model_validate_json(Path(args.page_plan).expanduser().read_text(encoding="utf-8"))
    texts = _parse_texts(args.texts)
    if not texts and args.title:
        texts.append(PlannedText(id="title", role="title", text=args.title, priority=10))
    if args.subtitle:
        texts.append(PlannedText(id="subtitle", role="subtitle", text=args.subtitle, priority=8))
    return ImageNativePagePlan(
        page_id=args.page_id,
        page_index=1,
        page_type=args.page_type,
        page_goal=args.page_goal or args.title or "Rebuild one slide image into editable HTML",
        key_takeaway=args.title or args.page_goal or "Image-native slide reconstruction",
        visual_intent=args.visual_intent or "Recover the slide's visual structure, hierarchy, and editable text areas.",
        composition_intent=args.composition_intent or "Infer composition from the input image.",
        planned_texts=texts,
        full_slide_prompt="",
        visual_must_haves=[],
        reconstruction_rules=[
            "Use the input image as visual source of truth.",
            "Known planned_texts are authoritative when present.",
            "Reconstruct to FreeformPageBlueprint-compatible editable blocks.",
        ],
    )


def _deck_brief_from_args(args: argparse.Namespace, page_plan: ImageNativePagePlan) -> DeckBrief:
    page_brief = PageBrief(
        page_id=page_plan.page_id,
        page_index=1,
        page_type=page_plan.page_type,
        page_goal=page_plan.page_goal,
        key_takeaway=page_plan.key_takeaway,
        visual_intent=page_plan.visual_intent,
        composition_intent=page_plan.composition_intent,
        must_include=[item.text for item in page_plan.planned_texts if item.text],
        visual_center=page_plan.visual_intent,
        dominant_move=page_plan.composition_intent,
    )
    return DeckBrief(
        deck_id=args.deck_id,
        deck_goal=args.deck_goal or "Single image-native rebuild test",
        target_audience=args.target_audience or "internal reviewer",
        language="zh-CN",
        design_tokens=DesignTokens(
            primary_color=args.primary_color,
            secondary_color=args.secondary_color,
            accent_color=args.accent_color,
            page_background="#ffffff",
            title_color="#111827",
            body_color="#1f2937",
            muted_color="#64748b",
            font_family="'PingFang SC', 'Microsoft YaHei', sans-serif",
        ),
        page_briefs=[page_brief.model_dump()],
        visual_direction=[args.visual_intent or "image-native reconstruction"],
    )


def _safe_slug(value: str, fallback: str = "slide") -> str:
    allowed = []
    for char in str(value or ""):
        if char.isalnum():
            allowed.append(char)
        elif char in {"-", "_"}:
            allowed.append(char)
        elif char in {" ", ".", "/"}:
            allowed.append("_")
    slug = "".join(allowed).strip("_")
    return slug[:80] or fallback


def _default_out_dir(image_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_TEST_ROOT / f"{stamp}_single_image_rebuild_{_safe_slug(image_path.stem)}"


def _copy_input_to_cache(image_path: Path, out_dir: Path) -> Path:
    DEFAULT_IMAGE_CACHE.mkdir(parents=True, exist_ok=True)
    if image_path.resolve().parent == DEFAULT_IMAGE_CACHE.resolve():
        return image_path
    target = DEFAULT_IMAGE_CACHE / f"{out_dir.name}_{_safe_slug(image_path.stem)}{image_path.suffix.lower() or '.png'}"
    shutil.copy2(image_path, target)
    return target


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _print_progress(message: str, *, started_at: float, stage_started_at: float | None = None) -> None:
    total_elapsed = time.time() - started_at
    if stage_started_at is None:
        print(f"[progress +{total_elapsed:.1f}s] {message}", flush=True)
        return
    stage_elapsed = time.time() - stage_started_at
    print(f"[progress +{total_elapsed:.1f}s | stage {stage_elapsed:.1f}s] {message}", flush=True)


async def rebuild(args: argparse.Namespace) -> Dict[str, Any]:
    run_started_at = time.time()
    image_path = Path(args.image).expanduser().resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"image not found: {image_path}")

    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else _default_out_dir(image_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    cached_image_path = _copy_input_to_cache(image_path, out_dir) if args.cache_input_image else image_path
    _print_progress(f"输出目录: {out_dir}", started_at=run_started_at)

    page_plan = _load_page_plan(args)
    deck_brief = _deck_brief_from_args(args, page_plan)
    image_bytes = image_path.read_bytes()
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    page_plan_path = out_dir / "page_plan.json"
    _write_json(page_plan_path, page_plan.model_dump())
    _print_progress("已写入 page_plan.json", started_at=run_started_at)

    coarse_analysis_path = out_dir / "coarse_regions.json"
    initial_analysis_path = out_dir / "analysis_initial.json"
    repaired_analysis_path = out_dir / "analysis_repaired.json"
    analysis_path = out_dir / "analysis.json"
    icon_map_path = out_dir / "icon_svg_map.json"
    blueprint_path = out_dir / "blueprint.json"
    html_path = out_dir / "reconstructed.html"
    region_analysis_dir = out_dir / "region_analyses"
    blueprint_region_dir = out_dir / "blueprint_regions"
    region_analysis_dir.mkdir(parents=True, exist_ok=True)
    blueprint_region_dir.mkdir(parents=True, exist_ok=True)

    stage_started_at: Dict[str, float] = {}

    def _analysis_progress(payload: Dict[str, Any]) -> None:
        stage = str(payload.get("stage") or "").strip()
        status = str(payload.get("status") or "").strip()
        message = str(payload.get("message") or stage or "analysis").strip()
        region_id = str(payload.get("region_id") or "").strip()
        stage_key = f"{stage}:{region_id}" if region_id else stage
        if status == "running":
            stage_started_at[stage_key] = time.time()
        stage_start = stage_started_at.get(stage_key)
        _print_progress(message, started_at=run_started_at, stage_started_at=stage_start if status == "completed" else None)
        if stage == "coarse_region_analysis" and status == "completed" and isinstance(payload.get("coarse_region_analysis"), dict):
            _write_json(coarse_analysis_path, payload.get("coarse_region_analysis"))
            _print_progress("已写入 coarse_regions.json", started_at=run_started_at)
        if stage == "detail_visual_region_analysis" and status == "completed":
            region_slug = _safe_slug(region_id or str(payload.get("region_index") or "region"))
            region_path = region_analysis_dir / f"{region_slug}.json"
            merged_path = region_analysis_dir / f"{region_slug}__merged.json"
            if isinstance(payload.get("region_visual_analysis"), dict):
                _write_json(region_path, payload.get("region_visual_analysis"))
                _print_progress(f"已写入区域分析 {region_path.name}", started_at=run_started_at)
            if isinstance(payload.get("merged_visual_analysis"), dict):
                _write_json(analysis_path, payload.get("merged_visual_analysis"))
                _write_json(merged_path, payload.get("merged_visual_analysis"))
                _print_progress(f"已更新 analysis.json / {merged_path.name}", started_at=run_started_at)
        if stage == "detail_visual_analysis" and status == "completed" and isinstance(payload.get("visual_analysis"), dict):
            _write_json(initial_analysis_path, payload.get("visual_analysis"))
            _write_json(analysis_path, payload.get("visual_analysis"))
            _print_progress("已写入 analysis_initial.json / analysis.json", started_at=run_started_at)
        if stage == "detail_visual_analysis_repair" and status == "completed" and isinstance(payload.get("visual_analysis_repaired"), dict):
            _write_json(repaired_analysis_path, payload.get("visual_analysis_repaired"))
            _write_json(analysis_path, payload.get("visual_analysis_repaired"))
            _print_progress("已写入 analysis_repaired.json / analysis.json", started_at=run_started_at)
        if stage == "blueprint_region_compose" and status == "completed":
            region_slug = _safe_slug(region_id or str(payload.get("region_index") or "region"))
            region_path = blueprint_region_dir / f"{region_slug}.json"
            if isinstance(payload.get("partial_blueprint"), dict):
                _write_json(region_path, payload.get("partial_blueprint"))
                _print_progress(f"已写入区域 blueprint {region_path.name}", started_at=run_started_at)

    analysis = await VisualSemanticAnalyzer().analyze(
        page_plan=page_plan.model_dump(),
        image_bytes=image_bytes,
        user_id=args.user_id,
        session_id=args.session_id or args.deck_id,
        progress_callback=_analysis_progress,
    )
    _write_json(analysis_path, analysis.model_dump())
    _print_progress("最终 analysis.json 已落盘", started_at=run_started_at)
    icon_svg_map = await ImageNativeIconSvgGenerator().generate_icons(
        analysis=analysis.model_dump(),
        user_id=args.user_id,
        session_id=args.session_id or args.deck_id,
        page_id=page_plan.page_id,
    )
    _write_json(icon_map_path, icon_svg_map)
    _print_progress(f"已写入 icon_svg_map.json（{len(list(icon_svg_map or {}))} 个 icon）", started_at=run_started_at)

    composer = BlueprintComposer()
    source_url = args.source_image_url.strip()
    if not source_url and args.embed_local_image_as_data_url:
        source_url = "data:image/png;base64," + image_b64

    blueprint_started_at = time.time()
    _print_progress("开始重建 blueprint", started_at=run_started_at)
    try:
        page = await composer.compose(
            deck_brief=deck_brief.model_dump(),
            page_plan=page_plan.model_dump(),
            visual_analysis=analysis.model_dump(),
            image_asset_map={},
            icon_svg_map=icon_svg_map,
            source_slide_image_url=source_url,
            user_id=args.user_id,
            session_id=args.session_id or args.deck_id,
            progress_callback=_analysis_progress,
        )
        _print_progress("blueprint 重建完成", started_at=run_started_at, stage_started_at=blueprint_started_at)
    except Exception:
        if not args.allow_fallback:
            raise
        _print_progress("blueprint 重建失败，进入 fallback", started_at=run_started_at, stage_started_at=blueprint_started_at)
        page = fallback_page_from_analysis(
            page_plan=page_plan.model_dump(),
            analysis=analysis.model_dump(),
            image_asset_map={},
            icon_svg_map=icon_svg_map,
            source_slide_image_url=source_url,
        )

    postprocess_started_at = time.time()
    _print_progress("开始 postprocess", started_at=run_started_at)
    page = postprocess_image_native_page(
        page,
        source_slide_image_url=source_url,
        image_asset_map={},
        allow_source_slide_background=args.page_type not in {"content", "agenda"},
    )
    _print_progress("postprocess 完成", started_at=run_started_at, stage_started_at=postprocess_started_at)
    deck = FreeformDeckBlueprint(
        deck_id=args.deck_id,
        deck_goal=deck_brief.deck_goal,
        target_audience=deck_brief.target_audience,
        theme=build_freeform_theme_from_design_tokens(deck_brief.design_tokens),
        pages=[page],
        runtime={
            "source": "single_image_native_rebuild_test",
            "page_plan": page_plan.model_dump(),
            "visual_analysis": analysis.model_dump(),
            "icon_svg_map": icon_svg_map,
            "input_image": str(image_path),
            "cached_input_image": str(cached_image_path),
        },
    )
    if not args.no_sanitize:
        sanitize_started_at = time.time()
        deck = sanitize_deck(deck)
        _print_progress("sanitize 完成", started_at=run_started_at, stage_started_at=sanitize_started_at)
    render_started_at = time.time()
    html = HtmlRenderer().compile(blueprint=deck).html
    _write_json(blueprint_path, deck.model_dump())
    _print_progress("已写入 blueprint.json", started_at=run_started_at)
    html_path.write_text(html, encoding="utf-8")
    _print_progress("已写入 reconstructed.html", started_at=run_started_at, stage_started_at=render_started_at)

    return {
        "out_dir": str(out_dir),
        "cached_input_image": str(cached_image_path),
        "page_plan": str(page_plan_path),
        "analysis": str(analysis_path),
        "blueprint": str(blueprint_path),
        "html": str(html_path),
        "html_chars": len(html),
        "image_placeholders": html.count("ff-shape-image-placeholder"),
        "real_image_tags": html.count('<img class="ff-shape-image"'),
        "tiny_font_count": html.count("font-size:0."),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Given one slide image, use current image-native code to reconstruct editable HTML."
    )
    parser.add_argument("--image", required=True, help="input slide image path")
    parser.add_argument("--out-dir", default="", help="output directory; defaults to test/PPT/<timestamp>_single_image_rebuild_<image>")
    parser.add_argument("--page-plan", default="", help="optional ImageNativePagePlan JSON path")
    parser.add_argument("--texts", default="", help='optional JSON list of known texts, e.g. [{"id":"title","role":"title","text":"..."}]')
    parser.add_argument("--title", default="", help="optional known title text")
    parser.add_argument("--subtitle", default="", help="optional known subtitle text")
    parser.add_argument("--page-id", default="single_image_page")
    parser.add_argument("--page-type", default="content")
    parser.add_argument("--page-goal", default="")
    parser.add_argument("--visual-intent", default="")
    parser.add_argument("--composition-intent", default="")
    parser.add_argument("--deck-id", default="single_image_native_rebuild")
    parser.add_argument("--deck-goal", default="")
    parser.add_argument("--target-audience", default="")
    parser.add_argument("--user-id", default="anonymous")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--primary-color", default="#2563eb")
    parser.add_argument("--secondary-color", default="#0f172a")
    parser.add_argument("--accent-color", default="#38bdf8")
    parser.add_argument("--source-image-url", default="", help="optional URL for the original image if renderer should use it")
    parser.add_argument("--embed-local-image-as-data-url", action="store_true", help="embed input image as data URL for local HTML fallback")
    parser.add_argument("--cache-input-image", action=argparse.BooleanOptionalAction, default=True, help="copy the input image into test/PPT/images")
    parser.add_argument("--allow-fallback", action="store_true", help="fall back to deterministic mapper if blueprint composer fails")
    parser.add_argument("--no-sanitize", action="store_true")
    args = parser.parse_args()

    import asyncio

    result = asyncio.run(rebuild(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
