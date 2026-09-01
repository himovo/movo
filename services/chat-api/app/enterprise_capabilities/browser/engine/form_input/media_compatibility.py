"""Generic compatibility checks between pending media and file inputs."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable
from urllib.parse import urlparse


_IMAGE_EXTENSIONS = {
    ".avif", ".bmp", ".gif", ".heic", ".heif", ".jpeg", ".jpg", ".png",
    ".svg", ".tif", ".tiff", ".webp",
}
_VIDEO_EXTENSIONS = {
    ".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".webm",
}


def requested_media_kinds(candidates: Iterable[Any]) -> set[str]:
    kinds: set[str] = set()
    for candidate in candidates:
        for raw in list(getattr(candidate, "value", None) or []):
            suffix = Path(urlparse(str(raw)).path).suffix.casefold()
            if suffix in _IMAGE_EXTENSIONS:
                kinds.add("image")
            elif suffix in _VIDEO_EXTENSIONS:
                kinds.add("video")
            else:
                kinds.add("attachment")
    return kinds or {"attachment"}


def file_input_accepts_media(
    target: Dict[str, Any],
    requested_kinds: set[str],
) -> bool:
    """Return whether an input's explicit accept contract permits the media."""

    accept = str(target.get("accept") or "").strip().casefold()
    if not accept or accept == "*/*":
        return True

    concrete_kinds = requested_kinds & {"image", "video"}
    if not concrete_kinds:
        return True

    tokens = {
        token.strip()
        for token in accept.split(",")
        if token.strip()
    }
    if not tokens:
        return True
    return all(_kind_is_accepted(kind, tokens) for kind in concrete_kinds)


def _kind_is_accepted(kind: str, tokens: set[str]) -> bool:
    if "*/*" in tokens or f"{kind}/*" in tokens:
        return True
    extensions = _IMAGE_EXTENSIONS if kind == "image" else _VIDEO_EXTENSIONS
    return any(
        token.startswith(f"{kind}/") or token in extensions
        for token in tokens
    )


__all__ = ["file_input_accepts_media", "requested_media_kinds"]
