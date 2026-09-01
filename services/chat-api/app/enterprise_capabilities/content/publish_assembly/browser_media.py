from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List
from urllib.parse import unquote, urlsplit, urlunsplit

from .contracts import BrowserPublishMediaSpec
from .media_anchors import end_of_body_anchor, extract_markdown_media_anchors


_SAFE_URL_RE = re.compile(
    r"^(?:https?://|/askai-api/(?:api/)?files/|/api/files/)",
    re.I,
)
_BACKEND_FILE_PREFIXES = (
    "/askai-api/api/files/",
    "/askai-api/files/",
    "/api/files/",
)


def collect_browser_publish_media(
    body_markdown: str,
    *,
    visual_assets: Iterable[Any] | None,
) -> List[BrowserPublishMediaSpec]:
    """Merge browser-bound media without losing authored Markdown positions.

    Inline Markdown images are the positional authority. Visual assets only
    enrich matching inline images or contribute genuinely standalone files.
    """

    assets = [_asset_dict(asset) for asset in list(visual_assets or [])]
    inline_identities: set[str] = set()
    result: List[BrowserPublishMediaSpec] = []

    for anchor in extract_markdown_media_anchors(body_markdown):
        url = str(anchor.source_url or "").strip()
        identity = media_asset_identity(url)
        if not url or not identity or not _SAFE_URL_RE.match(url):
            continue
        matching_asset = next(
            (
                asset
                for asset in assets
                if media_asset_identity(_asset_url(asset)) == identity
            ),
            None,
        )
        alt_text = str(anchor.alt_text or "").strip()
        if not alt_text and matching_asset is not None:
            alt_text = _asset_alt(matching_asset)
        inline_identities.add(identity)
        result.append(
            BrowserPublishMediaSpec(
                source_url=url,
                order=len(result),
                alt_text=alt_text[:240],
                anchor_after_text=anchor.anchor_after_text,
                anchor_before_text=anchor.anchor_before_text,
                anchor_plain_offset=max(0, int(anchor.anchor_plain_offset or 0)),
            )
        )

    fallback_anchor = end_of_body_anchor(body_markdown)
    seen_asset_keys: set[str] = set(inline_identities)
    for asset in assets:
        url = _asset_url(asset)
        identity = media_asset_identity(url)
        if (
            not url
            or not identity
            or identity in inline_identities
            or not _SAFE_URL_RE.match(url)
        ):
            continue
        stable_key = _asset_stable_key(asset, identity=identity)
        if stable_key in seen_asset_keys or identity in seen_asset_keys:
            continue
        seen_asset_keys.add(stable_key)
        seen_asset_keys.add(identity)
        result.append(
            BrowserPublishMediaSpec(
                source_url=url,
                order=len(result),
                alt_text=_asset_alt(asset)[:240],
                anchor_after_text=fallback_anchor.anchor_after_text,
                anchor_before_text=fallback_anchor.anchor_before_text,
                anchor_plain_offset=max(
                    0,
                    int(fallback_anchor.anchor_plain_offset or 0),
                ),
            )
        )
    return result


def media_asset_identity(value: str) -> str:
    """Return a stable identity for equivalent browser-upload URLs."""

    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw

    path = unquote(str(parsed.path or ""))
    for prefix in _BACKEND_FILE_PREFIXES:
        if path.startswith(prefix):
            object_path = path[len(prefix) :].lstrip("/")
            return f"backend-file:{object_path}" if object_path else ""

    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        normalized = urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                path,
                parsed.query,
                "",
            )
        )
        return f"url:{normalized}"
    return f"path:{path or raw}"


def _asset_stable_key(asset: Dict[str, Any], *, identity: str) -> str:
    slot_id = str(asset.get("slot_id") or asset.get("asset_id") or "").strip()
    return f"slot:{slot_id}" if slot_id else identity


def _asset_url(asset: Dict[str, Any]) -> str:
    return str(
        asset.get("source_url")
        or asset.get("image_url")
        or asset.get("url")
        or ""
    ).strip()


def _asset_alt(asset: Dict[str, Any]) -> str:
    return str(asset.get("alt_text") or asset.get("alt") or "").strip()


def _asset_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        payload = model_dump()
        return dict(payload) if isinstance(payload, dict) else {}
    if isinstance(value, str):
        return {"source_url": value}
    return {}


__all__ = ["collect_browser_publish_media", "media_asset_identity"]
