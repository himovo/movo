from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TEST_ROOT = PROJECT_ROOT / "test" / "PPT"
DEFAULT_IMAGE_CACHE = DEFAULT_TEST_ROOT / "images"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.presentation.contracts import FreeformDeckBlueprint
from app.services.presentation.html_renderer import HtmlRenderer
from app.services.presentation.image_native.blueprint_postprocess import postprocess_image_native_page
from app.services.presentation.structural_sanitizer import sanitize_deck
from app.utils.oss_uploader import AliyunOSSUploader


def _safe_slug(value: str, fallback: str = "deck") -> str:
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


def _default_run_dir(blueprint: FreeformDeckBlueprint) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_TEST_ROOT / f"{stamp}_blueprint_rebuild_{_safe_slug(blueprint.deck_id)}"


def _load_blueprint(args: argparse.Namespace) -> str:
    if args.blueprint:
        return Path(args.blueprint).expanduser().read_text(encoding="utf-8")
    if args.blueprint_object_path:
        import httpx

        uploader = AliyunOSSUploader()
        url = uploader.sign_url(args.blueprint_object_path)
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text
    raise ValueError("provide --blueprint or --blueprint-object-path")


def _download_image(url: str, target: Path) -> bool:
    if not url or target.exists():
        return target.exists()
    import httpx

    target.parent.mkdir(parents=True, exist_ok=True)
    resp = httpx.get(url, timeout=60)
    resp.raise_for_status()
    target.write_bytes(resp.content)
    return True


def rebuild(args: argparse.Namespace) -> dict:
    raw = _load_blueprint(args)
    blueprint = FreeformDeckBlueprint.model_validate_json(raw)
    uploader = AliyunOSSUploader()
    artifacts = list((blueprint.runtime or {}).get("image_native_artifacts") or [])
    downloaded_images = []

    for idx, page in enumerate(list(blueprint.pages or [])):
        artifact = artifacts[idx] if idx < len(artifacts) and isinstance(artifacts[idx], dict) else {}
        object_path = str(artifact.get("full_slide_image_object_path") or "").strip()
        image_url = uploader.sign_url(object_path) if object_path else str(artifact.get("full_slide_image_url") or "")
        if args.download_images_to and object_path and image_url:
            target = Path(args.download_images_to).expanduser().resolve() / Path(object_path).name
            _download_image(image_url, target)
            downloaded_images.append(str(target))
        asset_map = artifact.get("image_asset_map") if isinstance(artifact.get("image_asset_map"), dict) else {}
        blueprint.pages[idx] = postprocess_image_native_page(
            page,
            source_slide_image_url=image_url,
            image_asset_map=asset_map,
        )

    if not args.no_sanitize:
        blueprint = sanitize_deck(blueprint)
    html = HtmlRenderer().compile(blueprint=blueprint).html

    run_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else _default_run_dir(blueprint)
    out_html = Path(args.out_html).expanduser() if args.out_html else run_dir / "reconstructed.html"
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")

    out_blueprint = Path(args.out_blueprint).expanduser() if args.out_blueprint else out_html.with_suffix(".blueprint.json")
    out_blueprint.parent.mkdir(parents=True, exist_ok=True)
    out_blueprint.write_text(json.dumps(blueprint.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "html": str(out_html),
        "blueprint": str(out_blueprint),
        "downloaded_images": downloaded_images,
        "slide_count": len(list(blueprint.pages or [])),
        "html_chars": len(html),
        "image_placeholders": html.count("ff-shape-image-placeholder"),
        "real_image_tags": html.count('<img class="ff-shape-image"'),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild image-native HTML from an existing blueprint, reusing generated images.")
    parser.add_argument("--blueprint", default="", help="local blueprint json path")
    parser.add_argument("--blueprint-object-path", default="", help="OSS object path for blueprint json")
    parser.add_argument("--out-dir", default="", help="output directory; defaults to test/PPT/<timestamp>_blueprint_rebuild_<deck>")
    parser.add_argument("--out-html", default="", help="output HTML path; defaults to <out-dir>/reconstructed.html")
    parser.add_argument("--out-blueprint", default="", help="optional output blueprint path")
    parser.add_argument("--download-images-to", default=str(DEFAULT_IMAGE_CACHE), help="download full-slide generated images into this directory")
    parser.add_argument("--no-sanitize", action="store_true", help="skip structural sanitizer")
    args = parser.parse_args()
    result = rebuild(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
