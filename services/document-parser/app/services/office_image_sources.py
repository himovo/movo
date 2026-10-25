"""Find raster images referenced by OOXML document parts."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
OTHER_IMAGE_EXTENSIONS = {".emf", ".wmf", ".wdp", ".svg", ".eps", ".heic", ".heif"}
_SLIDE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
_SHEET = re.compile(r"^xl/worksheets/sheet(\d+)\.xml$")


@dataclass(frozen=True)
class EmbeddedImage:
    media_path: str
    data: bytes
    locations: tuple[str, ...]
    page_no: int | None


@dataclass(frozen=True)
class OfficeImageInventory:
    images: list[EmbeddedImage]
    unsupported_media_paths: list[str]


def discover_office_images(path: Path) -> list[EmbeddedImage]:
    """Return referenced images with slide/sheet/part provenance, without editing the file."""
    return inspect_office_images(path).images


def inspect_office_images(path: Path) -> OfficeImageInventory:
    with ZipFile(path) as archive:
        parents = _relationship_parents(archive)
        output: list[EmbeddedImage] = []
        unsupported: list[str] = []
        for entry in archive.infolist():
            name = entry.filename
            if not _is_media_part(name) or name not in parents:
                continue
            if Path(name).suffix.lower() in OTHER_IMAGE_EXTENSIONS:
                unsupported.append(name)
                continue
            if not _is_media_image(name):
                continue
            locations = tuple(sorted(_locations(name, parents)))
            page_numbers = {int(match.group(1)) for item in locations if (match := _SLIDE.fullmatch(item))}
            page_no = next(iter(page_numbers)) if len(page_numbers) == 1 else None
            output.append(EmbeddedImage(name, archive.read(entry), locations, page_no))
        return OfficeImageInventory(output, unsupported)


def _is_media_image(name: str) -> bool:
    return _is_media_part(name) and Path(name).suffix.lower() in RASTER_EXTENSIONS


def _is_media_part(name: str) -> bool:
    return name.startswith(("word/media/", "ppt/media/", "xl/media/"))


def _relationship_parents(archive: ZipFile) -> dict[str, set[str]]:
    parents: dict[str, set[str]] = {}
    for rel_path in archive.namelist():
        if "/_rels/" not in rel_path or not rel_path.endswith(".rels"):
            continue
        source = rel_path.replace("/_rels/", "/", 1).removesuffix(".rels")
        try:
            relationships = ElementTree.fromstring(archive.read(rel_path))
        except ElementTree.ParseError:
            continue
        for item in relationships:
            if item.get("TargetMode") == "External":
                continue
            target = str(item.get("Target") or "")
            if not target:
                continue
            resolved = (
                posixpath.normpath(target.lstrip("/")) if target.startswith("/")
                else posixpath.normpath(posixpath.join(posixpath.dirname(source), target))
            )
            if not resolved.startswith("../"):
                parents.setdefault(resolved, set()).add(source)
    return parents


def _locations(media_path: str, parents: dict[str, set[str]]) -> set[str]:
    seen = {media_path}
    pending = [media_path]
    locations: set[str] = set()
    while pending:
        part = pending.pop()
        for parent in parents.get(part, ()):
            if parent in seen:
                continue
            seen.add(parent)
            if _SLIDE.fullmatch(parent) or _SHEET.fullmatch(parent) or parent.startswith("word/"):
                locations.add(parent)
            if len(seen) < 100:
                pending.append(parent)
    return locations


def location_title(image: EmbeddedImage) -> str:
    if image.page_no is not None:
        return f"第 {image.page_no} 页嵌入图片"
    for part in image.locations:
        if match := _SHEET.fullmatch(part):
            return f"工作表 {match.group(1)} 嵌入图片"
    return "文档嵌入图片"
