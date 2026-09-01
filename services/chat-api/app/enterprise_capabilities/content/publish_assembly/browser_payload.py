from __future__ import annotations

import re
from typing import Any, Dict, Iterable

from bs4 import BeautifulSoup
from markdown_it import MarkdownIt

from .browser_media import collect_browser_publish_media
from .contracts import BrowserPublishPayload
from .media_anchors import strip_markdown_images


_LEADING_H1_RE = re.compile(r"^\s{0,3}#\s+(?P<title>.+?)\s*$")


def build_browser_publish_payload(
    markdown_content: str,
    *,
    visual_assets: Iterable[Any] | None = None,
) -> BrowserPublishPayload | None:
    """Project a generated Markdown artifact into a browser-form handoff.

    The payload is channel-neutral. Navigation and field discovery remain the
    Browser Agent Loop's responsibility; this function only preserves the
    generated title, body representations, and ordered media inputs.
    """

    markdown = str(markdown_content or "").strip()
    if not markdown:
        return None

    title, body_markdown = _split_title(markdown)
    media = collect_browser_publish_media(
        body_markdown,
        visual_assets=visual_assets,
    )
    text_markdown = strip_markdown_images(body_markdown)
    text_markdown = re.sub(r"\n{3,}", "\n\n", text_markdown).strip()

    parser = MarkdownIt("commonmark", {"html": False, "linkify": False})
    body_html = parser.render(text_markdown).strip()
    body_plain_text = BeautifulSoup(body_html, "html.parser").get_text("\n", strip=True)
    body_plain_text = re.sub(r"\n{3,}", "\n\n", body_plain_text).strip()

    return BrowserPublishPayload(
        title=title,
        body_markdown=text_markdown,
        body_plain_text=body_plain_text,
        body_html=body_html,
        media=media,
    )


def attach_browser_publish_payload(
    artifacts: Dict[str, Any],
    *,
    enabled: bool,
    visual_assets: Iterable[Any] | None = None,
) -> bool:
    """Attach the handoff only for generation nodes scoped to a browser."""
    if not enabled or not isinstance(artifacts, dict):
        return False
    payload = build_browser_publish_payload(
        str(artifacts.get("answer") or ""),
        visual_assets=visual_assets,
    )
    if payload is None:
        return False
    artifacts["publish_payload"] = payload.model_dump()
    return True


def _split_title(markdown: str) -> tuple[str, str]:
    lines = str(markdown or "").splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        match = _LEADING_H1_RE.match(line)
        if not match:
            return "", str(markdown or "").strip()
        title = _plain_inline_text(match.group("title"))
        body = "\n".join(lines[:index] + lines[index + 1 :]).strip()
        return title, body
    return "", ""


def _plain_inline_text(value: str) -> str:
    parser = MarkdownIt("commonmark", {"html": False, "linkify": False})
    rendered = parser.renderInline(str(value or ""))
    return BeautifulSoup(rendered, "html.parser").get_text(" ", strip=True)


__all__ = ["attach_browser_publish_payload", "build_browser_publish_payload"]
