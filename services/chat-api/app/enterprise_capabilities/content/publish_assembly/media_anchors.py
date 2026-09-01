from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from bs4 import BeautifulSoup
from markdown_it import MarkdownIt


MARKDOWN_IMAGE_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)"
)
_ANCHOR_LIMIT = 180


@dataclass(frozen=True)
class MarkdownMediaAnchor:
    source_url: str
    alt_text: str
    anchor_after_text: str
    anchor_before_text: str
    anchor_plain_offset: int


def extract_markdown_media_anchors(markdown: str) -> List[MarkdownMediaAnchor]:
    """Preserve where each Markdown image belongs in the rendered body."""

    source = str(markdown or "")
    matches = list(MARKDOWN_IMAGE_RE.finditer(source))
    anchors: List[MarkdownMediaAnchor] = []
    for match in matches:
        before = _plain_text_without_images(source[: match.start()])
        after = _plain_text_without_images(source[match.end() :])
        anchors.append(
            MarkdownMediaAnchor(
                source_url=str(match.group("url") or "").strip(),
                alt_text=str(match.group("alt") or "").strip(),
                anchor_after_text=_anchor_tail(before),
                anchor_before_text=_anchor_head(after),
                anchor_plain_offset=len(_compact(before)),
            )
        )
    return anchors


def strip_markdown_images(markdown: str) -> str:
    return MARKDOWN_IMAGE_RE.sub("", str(markdown or ""))


def end_of_body_anchor(markdown: str) -> MarkdownMediaAnchor:
    plain = _plain_text_without_images(markdown)
    return MarkdownMediaAnchor(
        source_url="",
        alt_text="",
        anchor_after_text=_anchor_tail(plain),
        anchor_before_text="",
        anchor_plain_offset=len(_compact(plain)),
    )


def _plain_text_without_images(markdown: str) -> str:
    parser = MarkdownIt("commonmark", {"html": False, "linkify": False})
    rendered = parser.render(strip_markdown_images(markdown))
    plain = BeautifulSoup(rendered, "html.parser").get_text("\n", strip=True)
    return re.sub(r"\s+", " ", plain).strip()


def _anchor_tail(value: str) -> str:
    compact = re.sub(r"\s+", " ", str(value or "")).strip()
    return compact[-_ANCHOR_LIMIT:]


def _anchor_head(value: str) -> str:
    compact = re.sub(r"\s+", " ", str(value or "")).strip()
    return compact[:_ANCHOR_LIMIT]


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


__all__ = [
    "MARKDOWN_IMAGE_RE",
    "MarkdownMediaAnchor",
    "end_of_body_anchor",
    "extract_markdown_media_anchors",
    "strip_markdown_images",
]
