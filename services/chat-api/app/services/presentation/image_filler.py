"""Fill image blocks in a FreeformDeckBlueprint with real generated images.

Wires the deck's ``type=="image"`` blocks into the existing text-to-image
service (``app.tools.infographic.generate_infographic_asset``), uploading the
result to OSS and writing the signed URL back into ``block.content``.

Design goals:
  * Only fill blocks that still hold a placeholder (``content`` is empty or
    not a valid http URL) and carry a non-empty ``image_prompt``.
  * Skip entirely when the feature flag is off, when no image blocks exist,
    or when the generation service fails — callers must never block.
  * Cache per-deck by (prompt, size) so the same prompt is generated once.
  * Bounded concurrency and per-deck cap to keep latency and spend in check.
  * Leave the block's geometry / role / styling untouched — only ``content``
    is mutated.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Iterable, List, Tuple

from app.services.presentation.contracts import (
    FreeformBlock,
    FreeformDeckBlueprint,
    FreeformPageBlueprint,
)
from app.tools.infographic import generate_infographic_asset

logger = logging.getLogger(__name__)


# Bounded concurrency so we don't slam the image service for a 20-page deck.
_DEFAULT_CONCURRENCY = 4
# Hard ceiling per deck — we prefer placeholder over runaway cost.
_DEFAULT_MAX_IMAGES_PER_DECK = 20
# Per-image generation timeout. Matches the infographic service default.
_DEFAULT_IMAGE_TIMEOUT_SECONDS = 90.0


def _is_http_url(value: str) -> bool:
    s = str(value or "").strip().lower()
    return s.startswith("http://") or s.startswith("https://")


def _iter_image_blocks(blocks: Iterable[FreeformBlock]) -> List[FreeformBlock]:
    """Walk the block tree and return every ``type=="image"`` node."""
    out: List[FreeformBlock] = []
    for block in blocks or []:
        if str(block.type or "").strip().lower() == "image":
            out.append(block)
        children = list(getattr(block, "children", None) or [])
        if children:
            out.extend(_iter_image_blocks(children))
    return out


def _resolve_size_for_block(block: FreeformBlock) -> str:
    """Pick a qwen-image-compatible output size that roughly matches the
    block's aspect ratio on the slide. We only need the ratio; absolute
    pixels are ignored on render since the renderer rescales anyway.
    """
    try:
        w = float(block.w or 0.0)
        h = float(block.h or 0.0)
    except Exception:
        w, h = 0.0, 0.0
    if w <= 0 or h <= 0:
        aspect = 1.0
    else:
        aspect = (w * 1920.0) / max(1.0, h * 1080.0)
    if aspect >= 1.3:
        return "1664*928"    # landscape ~16:9
    if aspect <= 0.77:
        return "928*1664"    # portrait ~9:16
    return "1328*1328"       # near-square


def _resolve_prompt(block: FreeformBlock) -> str:
    """Pick the best available text prompt for this image block."""
    candidates = [
        str(block.image_prompt or "").strip(),
        str(block.content or "").strip() if not _is_http_url(block.content or "") else "",
    ]
    for text in candidates:
        if text:
            return text
    return ""


def _is_enabled() -> bool:
    env_val = str(os.getenv("PRESENTATION_IMAGE_GEN_ENABLED", "")).strip().lower()
    if env_val in {"0", "false", "no", "off"}:
        return False
    return True


class ImageFiller:
    """Generate images for a finished blueprint, replacing placeholders."""

    def __init__(
        self,
        *,
        concurrency: int = _DEFAULT_CONCURRENCY,
        max_images_per_deck: int = _DEFAULT_MAX_IMAGES_PER_DECK,
        timeout_seconds: float = _DEFAULT_IMAGE_TIMEOUT_SECONDS,
    ) -> None:
        self._concurrency = max(1, int(concurrency))
        self._max_images = max(0, int(max_images_per_deck))
        self._timeout_seconds = float(timeout_seconds)

    async def fill(
        self,
        blueprint: FreeformDeckBlueprint,
        *,
        user_id: str,
    ) -> FreeformDeckBlueprint:
        if not _is_enabled():
            logger.info(
                "presentation_image_fill skipped reason=disabled_by_env deck_id=%s",
                str(blueprint.deck_id or "").strip(),
            )
            return blueprint
        targets: List[Tuple[FreeformPageBlueprint, FreeformBlock, str, str]] = []
        for page in list(blueprint.pages or []):
            for block in _iter_image_blocks(list(page.blocks or [])):
                # Skip blocks already pointing at a real URL.
                if _is_http_url(getattr(block, "content", "")):
                    continue
                prompt = _resolve_prompt(block)
                if not prompt:
                    continue
                size = _resolve_size_for_block(block)
                targets.append((page, block, prompt, size))
                if self._max_images and len(targets) >= self._max_images:
                    break
            if self._max_images and len(targets) >= self._max_images:
                logger.info(
                    "presentation_image_fill cap_hit deck_id=%s max=%s",
                    str(blueprint.deck_id or "").strip(),
                    self._max_images,
                )
                break
        if not targets:
            logger.info(
                "presentation_image_fill skipped reason=no_image_blocks deck_id=%s",
                str(blueprint.deck_id or "").strip(),
            )
            return blueprint

        logger.info(
            "presentation_image_fill start deck_id=%s image_count=%s concurrency=%s",
            str(blueprint.deck_id or "").strip(),
            len(targets),
            self._concurrency,
        )

        # Deduplicate by (prompt, size) so identical requests only hit the
        # service once. Many decks use the same prompt across hero/cover
        # + sibling pages.
        cache: dict[Tuple[str, str], str] = {}
        sem = asyncio.Semaphore(self._concurrency)

        async def _one(block: FreeformBlock, prompt: str, size: str) -> None:
            key = (prompt, size)
            if key in cache:
                block.content = cache[key]
                return
            async with sem:
                try:
                    result = await asyncio.wait_for(
                        generate_infographic_asset(
                            prompt=prompt,
                            user_id=user_id or "anonymous",
                            size=size,
                            timeout_seconds=self._timeout_seconds,
                        ),
                        timeout=self._timeout_seconds + 10.0,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "presentation_image_fill timeout block_id=%s prompt=%r size=%s",
                        str(block.id or ""),
                        prompt[:80],
                        size,
                    )
                    return
                except Exception:
                    logger.warning(
                        "presentation_image_fill exception block_id=%s prompt=%r size=%s",
                        str(block.id or ""),
                        prompt[:80],
                        size,
                        exc_info=True,
                    )
                    return
            if not bool(result.get("ok")):
                logger.warning(
                    "presentation_image_fill failed block_id=%s error=%s",
                    str(block.id or ""),
                    str(result.get("error") or ""),
                )
                return
            url = str(result.get("image_url") or "").strip()
            if not _is_http_url(url):
                logger.warning(
                    "presentation_image_fill invalid_url block_id=%s url=%s",
                    str(block.id or ""),
                    url,
                )
                return
            cache[key] = url
            block.content = url
            logger.info(
                "presentation_image_fill ok block_id=%s size=%s prompt=%r",
                str(block.id or ""),
                size,
                prompt[:80],
            )

        await asyncio.gather(
            *[_one(block, prompt, size) for _page, block, prompt, size in targets],
            return_exceptions=True,
        )
        filled = sum(1 for _p, b, _pr, _s in targets if _is_http_url(b.content or ""))
        logger.info(
            "presentation_image_fill done deck_id=%s filled=%s/%s",
            str(blueprint.deck_id or "").strip(),
            filled,
            len(targets),
        )
        return blueprint
