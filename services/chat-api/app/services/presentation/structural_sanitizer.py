"""Deterministic pre-render sanitizer for presentation.

Runs between ``render_prep`` and the HTML renderer. Only touches structural
bugs that are mathematically impossible to render — no layout opinions, no
spatial reasoning, no style judgments. Every rule must pass the offline
replay test: for every page that was ✅ in a prior visual-QC round, the
sanitizer must not modify a single byte. If a rule ever fails that test,
delete the rule.

Currently enforced rules:

1. **line_zero_geometry** — a block with ``type=line`` whose ``w*h`` is
   essentially zero and that has no explicit ``x2``/``y2`` endpoint is
   unrenderable. Assign a tiny placeholder endpoint so the HTML renderer
   can at least draw something, and downstream multimodal QC can then
   flag it for real if needed.

2. **text_html_leak** — a ``text_box`` whose ``content`` contains raw HTML
   tags like ``<span ...>`` is a known LLM failure mode (prompt leakage).
   Strip the tags and keep only the inner text.

3. **decoration_zero_geometry** — a ``rectangle``/``image``/``group`` block
   with ``w*h ≈ 0`` is invisible and contributes nothing to the page. Give
   it a small non-zero placeholder geometry so downstream QC can reason
   about it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, List

from app.services.presentation.contracts import (
    FreeformBlock,
    FreeformDeckBlueprint,
)

logger = logging.getLogger(__name__)


_ZERO_AREA = 0.0001            # below this area a block is considered unrenderable

# Line "invisibility" threshold: any line whose smaller dimension is below this
# is treated as visually-zero, even if its area passes _ZERO_AREA. Catches the
# common LLM failure mode of setting a real width but a 1-pixel stroke (e.g.,
# spine_line w=0.880 h=0.001 → area 0.00088 escapes _ZERO_AREA but is invisible
# at 1080p). Set to half the standard stroke so LLM-intentional fine lines at
# >=0.003 are preserved.
_LINE_INVISIBLE_DIM = 0.0025

# Line fallback sizes — must be large enough that the multimodal QC can
# actually see the line. The previous 0.005 × 0.001 was mathematically legal
# but visually invisible at 1920×1080, so QC kept flagging zero_geometry.
_LINE_STROKE = 0.005           # line thickness (~5 px at 1080)
_LINE_H_LONG = 0.80            # long horizontal line (spine / timeline)
_LINE_V_LONG = 0.60            # long vertical line
_LINE_SHORT = 0.12             # fallback short line for unclassified connectors
_CANVAS_SAFE_EDGE = 0.95       # clamp line endpoints to stay within page bounds
# z_index for sanitized lines: connectors must render BEHIND cards/groups so
# the multimodal QC does not flag a fresh z_order issue right after we make
# them visible. 1 sits above background (0) and below standard cards (3+).
_LINE_FIXED_Z = 1

_DECOR_FALLBACK_W = 0.02       # placeholder decoration size
_DECOR_FALLBACK_H = 0.02
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Text-over-container collision rule (page-level pass)
_TEXT_VS_CONTAINER_VERT_OVERLAP_RATIO = 0.3   # min vertical overlap of text height
_TEXT_VS_CONTAINER_HORIZ_OVERLAP_RATIO = 0.3  # min horizontal overlap of text width
_TEXT_VS_CONTAINER_PUSH_GAP = 0.012           # gap between text and container after push
_TEXT_RULE_TEXT_ROLES = frozenset({"title", "subtitle", "label", "body", ""})
_TEXT_RULE_CONTAINER_TYPES = frozenset({"rectangle", "group"})
_TEXT_RULE_CONTAINER_ROLES = frozenset({"panel", "band", "card", "hero", "group"})

_HORIZONTAL_LINE_KEYWORDS = (
    "spine", "timeline", "horizontal", "horiz", "axis_h", "_h", "hline",
    "divider_h", "process", "stage_line", "step_line", "rail",
)
_VERTICAL_LINE_KEYWORDS = (
    "vertical", "vert", "axis_v", "v_", "vline", "divider_v", "column_line",
)

# Text contrast repair rule (page-level pass)
# WCAG AA requires contrast ratio ≥ 4.5 for normal text. We use 4.0 as a
# slightly looser practical threshold so we only override the LLM's color
# choice when contrast is materially broken, not borderline.
_TEXT_CONTRAST_THRESHOLD = 4.0
_DEFAULT_DARK_TEXT = "#1a1a1a"
_DEFAULT_LIGHT_TEXT = "#ffffff"
_FULL_PAGE_BG_AREA = 0.80
# Substring fragments that imply a "dark" background even when only a
# gradient string is provided. Used as a fallback when we can't parse a
# concrete hex color out of the background style.
_DARK_BG_HINTS = (
    "1e1e1e", "2d3748", "1a1a1a", "0f172a", "111827", "1e293b",
    "1f2937", "0a0a0a", "000000", "212121", "0d1117", "0b1220",
    "151515", "262626", "353e4d", "1c2128",
)
_LIGHT_BG_HINTS = (
    "ffffff", "f8fafc", "f0f4f8", "e2e8f0", "fafafa", "f5f5f5",
    "f1f5f9", "e5e7eb", "ffffe0", "fafbff", "fdf6e3",
)

_HEX_RE = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
_RGB_RE = re.compile(r"rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")
_RGBA_ALPHA_RE = re.compile(r"rgba\s*\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*([0-9.]+)\s*\)")
_MIN_TEXT_ALPHA = 0.40  # below this, text is "decoration-level invisible" and must be boosted


def _classify_line_direction(block: FreeformBlock) -> str:
    """Return 'horizontal', 'vertical', or 'short' based on id/role hints.

    Pure text classification — no spatial reasoning, no sibling lookup. When
    the id or role strongly implies a direction the sanitizer gives the line
    a long fallback along that axis; otherwise it uses a short visible line
    (0.08) that at least becomes detectable by downstream QC.
    """
    bid = str(block.id or "").strip().lower()
    role = str(block.role or "").strip().lower()
    haystack = f"{bid} {role}"
    for kw in _HORIZONTAL_LINE_KEYWORDS:
        if kw in haystack:
            return "horizontal"
    for kw in _VERTICAL_LINE_KEYWORDS:
        if kw in haystack:
            return "vertical"
    return "short"


@dataclass
class SanitizeEdit:
    page_id: str
    block_id: str
    rule: str
    before: str
    after: str


def _area(block: FreeformBlock) -> float:
    return float(block.w or 0.0) * float(block.h or 0.0)


def _rect_str(b: FreeformBlock) -> str:
    return f"({float(b.x or 0):.3f},{float(b.y or 0):.3f},{float(b.w or 0):.3f},{float(b.h or 0):.3f})"


def _sanitize_line_zero_geometry(block: FreeformBlock) -> List[str]:
    """Return list of applied rule names if block was modified.

    Strategy (in priority order):
    1. If the LLM set x2/y2, derive w/h from the endpoints — this preserves
       LLM intent perfectly.
    2. Otherwise classify by id/role keywords:
       - horizontal-style id (spine, timeline, etc.) → long horizontal line
       - vertical-style id → long vertical line
       - everything else → a short visible line
    Endpoints are clamped so the line stays inside [0,1].
    """
    if str(block.type or "").strip().lower() != "line":
        return []
    w_now = float(block.w or 0.0)
    h_now = float(block.h or 0.0)
    if min(w_now, h_now) >= _LINE_INVISIBLE_DIM:
        return []

    x1 = float(block.x or 0.0)
    y1 = float(block.y or 0.0)

    # Force the connector below normal cards. We only LOWER the z_index, never
    # raise it — if the LLM already set a lower (or equal) value we leave it
    # alone. Doing this once here covers all the strategy branches below,
    # because every branch will return after the geometry write.
    current_z = int(block.z_index or 0)
    if current_z > _LINE_FIXED_Z:
        block.z_index = _LINE_FIXED_Z

    # Strategy 1 — endpoints exist, derive w/h from them
    if block.x2 is not None and block.y2 is not None:
        x2 = float(block.x2)
        y2 = float(block.y2)
        new_w = abs(x2 - x1)
        new_h = abs(y2 - y1)
        if new_w * new_h >= _ZERO_AREA:
            block.w = max(new_w, _LINE_STROKE)
            block.h = max(new_h, _LINE_STROKE)
            return ["line_zero_geometry_from_endpoints"]

    # Strategy 1.5 — preserve LLM major axis when one dim is real but the
    # other is invisible. Common case: spine_line at w=0.880 h=0.001 — the
    # length is intentional, only the stroke is wrong. Threshold 0.05 (5% of
    # canvas) keeps us from "rescuing" totally degenerate single-pixel lines.
    if w_now >= 0.05 and h_now < _LINE_INVISIBLE_DIM:
        block.h = _LINE_STROKE
        block.x2 = x1 + w_now
        block.y2 = y1
        return ["line_zero_geometry_thin_horizontal"]
    if h_now >= 0.05 and w_now < _LINE_INVISIBLE_DIM:
        block.w = _LINE_STROKE
        block.x2 = x1
        block.y2 = y1 + h_now
        return ["line_zero_geometry_thin_vertical"]

    # Strategy 2 — direction-aware visible fallback
    direction = _classify_line_direction(block)
    if direction == "horizontal":
        length = min(_LINE_H_LONG, _CANVAS_SAFE_EDGE - x1)
        if length < 0.10:
            length = _LINE_H_LONG
            x1 = max(0.0, _CANVAS_SAFE_EDGE - length)
            block.x = x1
        block.w = length
        block.h = _LINE_STROKE
        block.x2 = x1 + length
        block.y2 = y1
        return ["line_zero_geometry_horizontal"]
    if direction == "vertical":
        length = min(_LINE_V_LONG, _CANVAS_SAFE_EDGE - y1)
        if length < 0.10:
            length = _LINE_V_LONG
            y1 = max(0.0, _CANVAS_SAFE_EDGE - length)
            block.y = y1
        block.w = _LINE_STROKE
        block.h = length
        block.x2 = x1
        block.y2 = y1 + length
        return ["line_zero_geometry_vertical"]
    # Unknown direction — short visible horizontal line
    length = min(_LINE_SHORT, _CANVAS_SAFE_EDGE - x1)
    if length < 0.02:
        length = _LINE_SHORT
        x1 = max(0.0, _CANVAS_SAFE_EDGE - length)
        block.x = x1
    block.w = length
    block.h = _LINE_STROKE
    block.x2 = x1 + length
    block.y2 = y1
    return ["line_zero_geometry_short"]


def _sanitize_text_html_leak(block: FreeformBlock) -> List[str]:
    if str(block.type or "").strip().lower() != "text_box":
        return []
    content = str(block.content or "")
    if not content or "<" not in content:
        return []
    if not _HTML_TAG_RE.search(content):
        return []
    cleaned = _HTML_TAG_RE.sub("", content).strip()
    if cleaned == content:
        return []
    block.content = cleaned
    return ["text_html_leak"]


# Matches the bare token itself (ev_1, doc_abc123, …).
_EVIDENCE_BARE_RE = re.compile(r"(?:ev|doc)_[A-Za-z0-9]+")

# Matches a bracket group that contains ONLY evidence tokens (optionally
# chained by separators). Strips the entire group, brackets included.
#   (ev_1)  [ev_2, ev_3]  （doc_abc）  【ev_1；ev_2】
_EVIDENCE_BRACKET_ONLY_RE = re.compile(
    r"[\(\[\{（【]\s*(?:ev|doc)_[A-Za-z0-9]+"
    r"(?:\s*[,，、;；/]\s*(?:ev|doc)_[A-Za-z0-9]+)*"
    r"\s*[\)\]\}）】]"
)

# Matches a stray token with an optional preceding separator so
# "foo, ev_1, bar" → "foo, bar" and "(text, ev_1)" → "(text)".
_EVIDENCE_WITH_LEADING_SEP_RE = re.compile(
    r"[,，、;；/]?\s*(?:ev|doc)_[A-Za-z0-9]+"
)


def _sanitize_evidence_id_leak(block: FreeformBlock) -> List[str]:
    """Strip any ``ev_1`` / ``doc_xxx`` reference tokens the LLM accidentally
    pasted into visible slide text. These are internal reasoning labels, not
    citations the audience should see.
    """
    if str(block.type or "").strip().lower() != "text_box":
        return []
    content = str(block.content or "")
    if not content or not _EVIDENCE_BARE_RE.search(content):
        return []
    cleaned = _EVIDENCE_BRACKET_ONLY_RE.sub("", content)
    cleaned = _EVIDENCE_WITH_LEADING_SEP_RE.sub("", cleaned)
    # Tidy leftovers: empty brackets, double punctuation, hanging separators.
    cleaned = re.sub(r"\(\s*\)|\[\s*\]|（\s*）|【\s*】", "", cleaned)
    cleaned = re.sub(r"\s*([，。；,;])\s*([。；,;])", r"\2", cleaned)
    cleaned = re.sub(r"\s+([，。；,;.!?)）\]】])", r"\1", cleaned)
    cleaned = re.sub(r"([(（\[【])\s+", r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if cleaned == content:
        return []
    block.content = cleaned
    return ["evidence_id_leak"]


def _sanitize_line_z_order(block: FreeformBlock) -> List[str]:
    """Force every line block to render BEHIND cards.

    LLM-emitted lines almost always represent connectors, axes, dividers, or
    timeline spines — visual elements whose semantic role is to sit BEHIND
    the cards/nodes they relate to. When the LLM picks a high z_index for a
    line (commonly z=4 or z=5, above typical card z=3), the multimodal QC
    flags it as a z_order defect on the very next pass. Clamping line z to
    a max of 1 here removes the defect at the source.

    Risk note: this rule will override LLM intent if the LLM ever wants a
    line to render in front (e.g. a foreground emphasis stroke). That use
    case is extraordinarily rare in business decks and the cost of catching
    it would be many false positives downstream, so we accept the trade.
    """
    if str(block.type or "").strip().lower() != "line":
        return []
    role_text = " ".join(
        [
            str(block.id or ""),
            str(block.role or ""),
            str(block.container_id or ""),
        ]
    ).lower()
    if any(token in role_text for token in ("timeline", "axis", "connector", "network", "divider", "separator", "sep")):
        return []
    current_z = int(block.z_index or 0)
    if current_z <= _LINE_FIXED_Z:
        return []
    block.z_index = _LINE_FIXED_Z
    return ["line_z_order_clamp"]


_DECOR_TYPES = frozenset({"rectangle", "image", "group"})


def _sanitize_decoration_zero_geometry(block: FreeformBlock) -> List[str]:
    block_type = str(block.type or "").strip().lower()
    if block_type not in _DECOR_TYPES:
        return []
    if _area(block) >= _ZERO_AREA:
        return []
    # A group with children whose own geometry is real should keep its
    # children — we only give the parent a placeholder bbox so it renders.
    block.w = max(float(block.w or 0.0), _DECOR_FALLBACK_W)
    block.h = max(float(block.h or 0.0), _DECOR_FALLBACK_H)
    return ["decoration_zero_geometry"]


def _sanitize_full_page_background_z(block: FreeformBlock) -> List[str]:
    """Move full-page background rects behind all content.

    Image-native compose may emit a final ``bg_full`` rectangle with a large
    z-index. Renderers correctly honor that z-index, which makes the page look
    blank because the background covers every other block. Any near-full-page
    background rectangle is structural background, not foreground content, so
    we clamp it to z=0 and tag it with a background role.
    """
    if str(block.type or "").strip().lower() != "rectangle":
        return []
    area = float(block.w or 0.0) * float(block.h or 0.0)
    if area < _FULL_PAGE_BG_AREA:
        return []
    style = dict(block.style or {})
    if not (style.get("background") or style.get("background_color")):
        return []
    current_z = int(block.z_index or 0)
    role = str(block.role or "").strip().lower()
    if current_z <= 0 and role in {"background", "surface"}:
        return []
    block.z_index = 0
    if role not in {"background", "surface"}:
        block.role = "background"
    return ["full_page_background_z_reset"]


def _parse_color_to_rgb(color_str: str) -> tuple[int, int, int] | None:
    """Best-effort RGB extraction from a CSS color string.

    Handles ``#rgb``, ``#rrggbb``, ``#rrggbbaa``, and ``rgb(...)`` /
    ``rgba(...)``. For complex inputs like ``linear-gradient(...)``, returns
    the FIRST hex/rgb token found, which is usually the dominant stop. We
    use a hint table downstream to handle the gradient case more carefully.
    """
    if not color_str or not isinstance(color_str, str):
        return None
    s = color_str.strip().lower()
    m = _HEX_RE.search(s)
    if m:
        hex_val = m.group(1)
        if len(hex_val) == 3:
            r = int(hex_val[0] * 2, 16)
            g = int(hex_val[1] * 2, 16)
            b = int(hex_val[2] * 2, 16)
            return (r, g, b)
        if len(hex_val) >= 6:
            r = int(hex_val[0:2], 16)
            g = int(hex_val[2:4], 16)
            b = int(hex_val[4:6], 16)
            return (r, g, b)
    m = _RGB_RE.search(s)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG relative luminance for an sRGB triple."""
    def channel(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast_ratio(rgb_a: tuple[int, int, int], rgb_b: tuple[int, int, int]) -> float:
    la = _relative_luminance(rgb_a)
    lb = _relative_luminance(rgb_b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def _classify_background_brightness(bg_str: str) -> str:
    """Return 'dark', 'light', or 'unknown' for a background style string.

    First tries to parse a concrete RGB and use luminance. Falls back to
    substring hints for gradient strings the parser can't fully decode.
    """
    if not bg_str:
        return "unknown"
    rgb = _parse_color_to_rgb(bg_str)
    if rgb is not None:
        lum = _relative_luminance(rgb)
        if lum < 0.4:
            return "dark"
        if lum > 0.7:
            return "light"
        # mid-range — fall through to hint check
    s = str(bg_str).lower()
    for hint in _DARK_BG_HINTS:
        if hint in s:
            return "dark"
    for hint in _LIGHT_BG_HINTS:
        if hint in s:
            return "light"
    return "unknown"


def _flatten_all_blocks_absolute(
    blocks: List[FreeformBlock],
    parent_rect: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
) -> List[tuple[FreeformBlock, tuple[float, float, float, float]]]:
    """Recursively flatten all blocks into (block, absolute_rect) pairs.

    Children with ``coordinate_space=parent`` have their coordinates
    translated to page-absolute using ``parent_rect``. This gives us a
    single flat list where every block's rect is in the same coordinate
    space, enabling correct geometric containment checks regardless of
    nesting depth.
    """
    result: List[tuple[FreeformBlock, tuple[float, float, float, float]]] = []
    px, py, pw, ph = parent_rect
    for b in blocks:
        cs = str(b.coordinate_space or "page").strip().lower()
        if cs == "parent":
            bx = px + float(b.x or 0.0) * pw
            by = py + float(b.y or 0.0) * ph
            bw = float(b.w or 0.0) * pw
            bh = float(b.h or 0.0) * ph
        else:
            bx = float(b.x or 0.0)
            by = float(b.y or 0.0)
            bw = float(b.w or 0.0)
            bh = float(b.h or 0.0)
        abs_rect = (bx, by, bw, bh)
        result.append((b, abs_rect))
        if b.children:
            result.extend(_flatten_all_blocks_absolute(
                list(b.children), parent_rect=abs_rect,
            ))
    return result


def _find_text_background(
    text: FreeformBlock,
    siblings: List[FreeformBlock],
) -> FreeformBlock | None:
    """Return the most likely background block beneath ``text``.

    Searches ALL blocks on the page (recursively flattened with absolute
    coordinates) to find the one that:
      1. geometrically contains the text's center
      2. has a non-empty ``style.background``
      3. is not the text itself
      4. has the smallest area among candidates (most specific container)

    By flattening recursively, this correctly finds a ``hero_panel``
    nested inside a ``bg_base`` rectangle — the previous version only
    searched top-level siblings and missed nested backgrounds entirely,
    causing the sanitizer to treat the text as if it were on the page
    default white background and flip its color backwards.

    The ``container_id`` shortcut is checked first but only trusted when
    the declared parent geometrically contains the text AND has a bg
    style. Otherwise falls through to the geometric search.
    """
    text_id = str(text.id or "").strip()
    text_cid = str(text.container_id or "").strip()
    text_cx = float(text.x or 0.0) + float(text.w or 0.0) / 2.0
    text_cy = float(text.y or 0.0) + float(text.h or 0.0) / 2.0

    def _rect_contains_point(rect: tuple[float, float, float, float]) -> bool:
        rx, ry, rw, rh = rect
        if rw <= 0 or rh <= 0:
            return False
        return rx <= text_cx <= rx + rw and ry <= text_cy <= ry + rh

    # Flatten the entire page block tree into absolute coordinates.
    all_blocks = _flatten_all_blocks_absolute(siblings)

    # Step 1: container_id shortcut with geometric sanity check.
    # Skip if the declared container is a full-page background — we want
    # the most specific overlaying panel, not the page-level bg rect.
    if text_cid:
        for b, abs_rect in all_blocks:
            if str(b.id or "").strip() != text_cid:
                continue
            # Skip background-role blocks — they're never the "interesting"
            # background for contrast. The geometric search (step 2) will
            # find the overlaying panel instead.
            if str(b.role or "").strip().lower() in ("background", "surface", "bg"):
                break
            # Skip if the declared container covers >= 80% of the canvas
            # (a nearly-full-page rect is functionally a background even
            # without the background role label).
            carea = abs_rect[2] * abs_rect[3]
            if carea >= 0.80:
                break
            style = dict(b.style or {})
            bg = style.get("background") or style.get("background_color") or ""
            if not bg:
                break
            if _rect_contains_point(abs_rect):
                return b
            break

    # Step 2: geometric search across all flattened blocks.
    candidates: List[tuple[float, int, FreeformBlock]] = []
    for b, abs_rect in all_blocks:
        if str(b.id or "").strip() == text_id:
            continue
        if not _rect_contains_point(abs_rect):
            continue
        style = dict(b.style or {})
        bg = style.get("background") or style.get("background_color") or ""
        if not bg:
            continue
        z = int(b.z_index or 0)
        area = abs_rect[2] * abs_rect[3]
        candidates.append((area, -z, str(b.id or ""), b))

    if not candidates:
        return None
    # Smallest area first (most specific), then highest z.
    candidates.sort(key=lambda t: (t[0], t[1], t[2]))
    return candidates[0][3]


def _sanitize_text_contrast(
    page: Any,
    page_id: str,
    edits: List[SanitizeEdit],
) -> None:
    """Recolor text whose color is unreadable against its background.

    Only fires when ALL of the following hold:
      - the text_box has non-empty content (we don't repair invisible text)
      - we can identify a sibling/container block beneath it with a
        non-empty ``style.background``
      - the text's current color (or default #000000) yields contrast < 4.0
        against the background

    Repair: replace ``text.style.color`` with ``#ffffff`` for dark
    backgrounds or ``#1a1a1a`` for light backgrounds. The original color is
    recorded in the edit log so the change is auditable.

    The rule walks ALL text_box descendants of the page, not just top-level,
    so it catches text inside group cards (e.g. card_contact label inside
    contact_card on a hero page).
    """
    siblings: List[FreeformBlock] = list(getattr(page, "blocks", None) or [])
    if not siblings:
        return

    def _process_text(
        block: FreeformBlock,
        bg_block: FreeformBlock | None,
        bg_source: str,
    ) -> None:
        text_style = dict(block.style or {})
        current_color = str(text_style.get("color") or "#000000")

        # Alpha-boost: if text uses rgba with very low alpha (< 0.40),
        # the text is practically invisible regardless of hue. Boost
        # alpha to 0.85 so the text becomes readable as a "faded but
        # visible" element rather than decoration dust.
        alpha_match = _RGBA_ALPHA_RE.search(current_color)
        if alpha_match:
            try:
                alpha = float(alpha_match.group(1))
            except ValueError:
                alpha = 1.0
            if alpha < _MIN_TEXT_ALPHA:
                boosted = current_color[:alpha_match.start(1)] + "0.85" + current_color[alpha_match.end(1):]
                edits.append(SanitizeEdit(
                    page_id=page_id,
                    block_id=str(block.id or ""),
                    rule="text_alpha_boost",
                    before=f"color={current_color} alpha={alpha:.2f}",
                    after=f"color={boosted}",
                ))
                current_color = boosted
                text_style["color"] = current_color
                block.style = text_style

        text_rgb = _parse_color_to_rgb(current_color) or (0, 0, 0)
        text_lum = _relative_luminance(text_rgb)

        if bg_block is not None:
            style_bg = dict(bg_block.style or {})
            bg_str = str(style_bg.get("background") or style_bg.get("background_color") or "")
            bg_class = _classify_background_brightness(bg_str)
            bg_rgb = _parse_color_to_rgb(bg_str)
        else:
            # Page default background is white. The renderer renders the
            # page on a #ffffff canvas unless something covers it.
            bg_str = "#ffffff"
            bg_class = "light"
            bg_rgb = (255, 255, 255)

        if bg_class == "unknown":
            return

        contrast: float | None = None
        if bg_rgb is not None:
            contrast = _contrast_ratio(text_rgb, bg_rgb)
        needs_fix = False
        if contrast is not None and contrast < _TEXT_CONTRAST_THRESHOLD:
            needs_fix = True
        elif contrast is None:
            if bg_class == "dark" and text_lum < 0.5:
                needs_fix = True
            elif bg_class == "light" and text_lum > 0.5:
                needs_fix = True
        if not needs_fix:
            return
        new_color = _DEFAULT_LIGHT_TEXT if bg_class == "dark" else _DEFAULT_DARK_TEXT
        if new_color.lower() == current_color.lower():
            return
        text_style["color"] = new_color
        block.style = text_style
        edits.append(SanitizeEdit(
            page_id=page_id,
            block_id=str(block.id or ""),
            rule="text_contrast_repair",
            before=f"color={current_color} bg={bg_source} bg_class={bg_class}",
            after=f"color={new_color}",
        ))

    def _walk_top_level(block: FreeformBlock) -> None:
        """Process a top-level block of the page.

        Top-level text blocks are page-absolute and use the page-level
        sibling pool for background lookup. Group children are handled by
        a separate walker that treats the group as their background frame
        (not the page) — because their coordinates are parent-relative and
        comparing them against page-level siblings produces nonsense.
        """
        btype = str(block.type or "").strip().lower()
        if btype == "text_box" and str(block.content or "").strip():
            bg_block = _find_text_background(block, siblings)
            bg_source = str(bg_block.id or "") if bg_block is not None else "page_default_white"
            _process_text(block, bg_block, bg_source)
        if btype == "group":
            for child in list(block.children or []):
                _walk_inside_group(child, parent_group=block)

    def _find_sibling_bg_in_group(
        text: FreeformBlock,
        sibling_children: List[FreeformBlock],
    ) -> FreeformBlock | None:
        """Find a sibling rectangle/card within the same group that is the
        visual backdrop for ``text``.

        This handles the common LLM pattern where a group contains:
          - rectangle (z=2, background=#ffffff)  ← visual card
          - text_box  (z=5, color=#ffffff)        ← label on the card

        The text's actual visual bg is the sibling rectangle, NOT the
        parent group's background. We search siblings that:
          1. are rectangle/group type (not text/icon/line)
          2. have a non-empty background style
          3. geometrically contain the text's center (in parent-relative coords)
          4. have z_index < text's z_index (sitting behind the text)

        Returns the best match (smallest area), or None if no sibling qualifies.
        """
        text_cx = float(text.x or 0.0) + float(text.w or 0.0) / 2.0
        text_cy = float(text.y or 0.0) + float(text.h or 0.0) / 2.0
        text_z = int(text.z_index or 0)
        candidates: List[tuple[float, FreeformBlock]] = []
        for sib in sibling_children:
            if id(sib) == id(text):
                continue
            sib_type = str(sib.type or "").strip().lower()
            if sib_type not in ("rectangle", "group", "image", "circle"):
                continue
            sib_style = dict(sib.style or {})
            sib_bg = sib_style.get("background") or sib_style.get("background_color") or ""
            if not sib_bg:
                continue
            if int(sib.z_index or 0) >= text_z:
                continue
            sx = float(sib.x or 0.0)
            sy = float(sib.y or 0.0)
            sw = float(sib.w or 0.0)
            sh = float(sib.h or 0.0)
            if sw <= 0 or sh <= 0:
                continue
            if sx <= text_cx <= sx + sw and sy <= text_cy <= sy + sh:
                candidates.append((sw * sh, sib))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][1]

    def _walk_inside_group(block: FreeformBlock, parent_group: FreeformBlock) -> None:
        """Process a block that lives inside a group.

        For contrast, we first check whether a sibling rectangle/card
        within the same group serves as the text's visual backdrop (the
        common "white card + white label" pattern). If found, that sibling
        is the background. Otherwise, we walk outward to the nearest
        ancestor group with a background style, and finally fall back to
        page default white.
        """
        btype = str(block.type or "").strip().lower()
        if btype == "text_box" and str(block.content or "").strip():
            sibling_bg = _find_sibling_bg_in_group(
                block, list(parent_group.children or []),
            )
            if sibling_bg is not None:
                bg_source = str(sibling_bg.id or "")
                _process_text(block, sibling_bg, bg_source)
            else:
                # Walk outward through ancestors looking for a non-empty,
                # non-transparent background. Skip ancestors whose bg is
                # effectively transparent (rgba with alpha < 0.40) — they
                # don't visually change what's beneath them.
                bg_block: FreeformBlock | None = None
                ancestor: FreeformBlock | None = parent_group
                while ancestor is not None:
                    anc_style = dict(ancestor.style or {})
                    anc_bg = anc_style.get("background") or anc_style.get("background_color") or ""
                    if anc_bg:
                        # Check if the bg is effectively transparent
                        alpha_m = _RGBA_ALPHA_RE.search(str(anc_bg))
                        if alpha_m:
                            try:
                                alpha_val = float(alpha_m.group(1))
                            except ValueError:
                                alpha_val = 1.0
                            if alpha_val < _MIN_TEXT_ALPHA:
                                # Transparent overlay — skip, keep searching
                                ancestor = ancestor_map.get(id(ancestor))
                                continue
                        bg_block = ancestor
                        break
                    ancestor = ancestor_map.get(id(ancestor))
                if bg_block is None:
                    # No ancestor had a real bg. Fall back to page-level
                    # search using the flattened block pool — this finds
                    # nested backgrounds like hero_panel inside bg_base.
                    # We use parent_group as the proxy for the text's
                    # position because the text itself has parent-relative
                    # coordinates that _find_text_background can't use.
                    bg_block = _find_text_background(parent_group, siblings)
                bg_source = str(bg_block.id or "") if bg_block is not None else "page_default_white"
                _process_text(block, bg_block, bg_source)
        if btype == "group":
            for child in list(block.children or []):
                ancestor_map[id(child)] = block
                _walk_inside_group(child, parent_group=block)

    # Map from id(child) → its parent group, used to walk outward to find
    # the nearest ancestor with a background style.
    ancestor_map: dict[int, FreeformBlock] = {}
    for top in siblings:
        if str(top.type or "").strip().lower() == "group":
            for child in list(top.children or []):
                ancestor_map[id(child)] = top
        _walk_top_level(top)


def _vert_overlap(a: FreeformBlock, b: FreeformBlock) -> float:
    a_top = float(a.y or 0.0)
    a_bot = a_top + float(a.h or 0.0)
    b_top = float(b.y or 0.0)
    b_bot = b_top + float(b.h or 0.0)
    return max(0.0, min(a_bot, b_bot) - max(a_top, b_top))


def _horiz_overlap(a: FreeformBlock, b: FreeformBlock) -> float:
    a_left = float(a.x or 0.0)
    a_right = a_left + float(a.w or 0.0)
    b_left = float(b.x or 0.0)
    b_right = b_left + float(b.w or 0.0)
    return max(0.0, min(a_right, b_right) - max(a_left, b_left))


def _has_real_overlap(
    candidate: FreeformBlock,
    other: FreeformBlock,
) -> bool:
    """True iff ``candidate`` and ``other`` overlap by a non-trivial area."""
    v = _vert_overlap(candidate, other)
    if v <= 0:
        return False
    h = _horiz_overlap(candidate, other)
    return h > 0


def _sanitize_text_over_container_collision(
    page: Any,
    page_id: str,
    edits: List[SanitizeEdit],
) -> None:
    """Push a top-level text_box out of an overlapping content container.

    Trigger conditions (ALL must hold) — chosen to fire only when the LLM
    almost certainly made a structural mistake, so the rule never edits a
    well-formed page:

      1. ``text`` is a top-level block on the page (not nested in a group),
         type=text_box, role in {title, subtitle, label, body, ""}.
      2. ``container`` is a top-level block on the page (sibling of ``text``),
         type in {rectangle, group}, role in {panel, band, card, hero, group}.
         Backgrounds (role=background/surface) are explicitly excluded
         because text on a background is the WHOLE point of a hero page.
      3. ``text.container_id`` does NOT point to ``container`` (no declared
         "this text belongs inside that container" relationship).
      4. Vertical overlap is at least 30% of the text height.
      5. Horizontal overlap is at least 30% of the text width.
         (Both 4 and 5 are required so we only fire when text is genuinely
         buried inside the container, not merely brushing its edge.)
      6. ``text.z_index >= container.z_index`` — text is rendered on top.

    Action: try to push the text just above the container; if there's no
    clean slot above, try just below; if neither works without creating a
    NEW collision against another content container or text_box, leave the
    text alone. The "no new collision" check is the load-bearing safety net
    that makes this rule safe to run on already-good pages.

    The rule does NOT recurse into group children — it only operates on the
    page's top-level block list. Cross-level cases would need parent-frame
    coordinate translation and have far more failure modes; the failing
    pages we observed (page_17, page_03) are all top-level vs top-level.
    """
    siblings: List[FreeformBlock] = list(getattr(page, "blocks", None) or [])
    if len(siblings) < 2:
        return

    text_blocks = [
        b for b in siblings
        if str(b.type or "").strip().lower() == "text_box"
        and str(b.role or "").strip().lower() in _TEXT_RULE_TEXT_ROLES
        and float(b.h or 0.0) > 0
        and float(b.w or 0.0) > 0
    ]
    if not text_blocks:
        return

    container_blocks = [
        b for b in siblings
        if str(b.type or "").strip().lower() in _TEXT_RULE_CONTAINER_TYPES
        and str(b.role or "").strip().lower() in _TEXT_RULE_CONTAINER_ROLES
        and float(b.w or 0.0) * float(b.h or 0.0) > 0.0
    ]
    if not container_blocks:
        return

    for text in text_blocks:
        text_h = float(text.h or 0.0)
        text_w = float(text.w or 0.0)
        text_z = int(text.z_index or 0)
        text_id = str(text.id or "").strip()
        for cont in container_blocks:
            if id(cont) == id(text):
                continue
            cont_id = str(cont.id or "").strip()
            if str(text.container_id or "").strip() == cont_id and cont_id:
                continue
            if int(cont.z_index or 0) > text_z:
                continue
            if _vert_overlap(text, cont) < _TEXT_VS_CONTAINER_VERT_OVERLAP_RATIO * text_h:
                continue
            if _horiz_overlap(text, cont) < _TEXT_VS_CONTAINER_HORIZ_OVERLAP_RATIO * text_w:
                continue

            cont_top = float(cont.y or 0.0)
            cont_bot = cont_top + float(cont.h or 0.0)
            candidate_above = cont_top - text_h - _TEXT_VS_CONTAINER_PUSH_GAP
            candidate_below = cont_bot + _TEXT_VS_CONTAINER_PUSH_GAP

            chosen_y: float | None = None
            for cand in (candidate_above, candidate_below):
                if cand < 0.0 or cand + text_h > 1.0:
                    continue
                trial = text.model_copy(deep=True)
                trial.y = cand
                collides = False
                for other in siblings:
                    if id(other) == id(text):
                        continue
                    if id(other) == id(cont):
                        # By construction the trial position is outside cont.
                        continue
                    other_role = str(other.role or "").strip().lower()
                    if other_role in {"background", "surface"}:
                        continue
                    if not _has_real_overlap(trial, other):
                        continue
                    other_type = str(other.type or "").strip().lower()
                    if other_type == "text_box":
                        collides = True
                        break
                    if (
                        other_type in _TEXT_RULE_CONTAINER_TYPES
                        and other_role in _TEXT_RULE_CONTAINER_ROLES
                    ):
                        collides = True
                        break
                if not collides:
                    chosen_y = cand
                    break

            if chosen_y is None:
                continue

            old_rect = _rect_str(text)
            text.y = chosen_y
            edits.append(SanitizeEdit(
                page_id=page_id,
                block_id=text_id,
                rule="text_over_container_collision",
                before=f"{old_rect} container={cont_id}",
                after=_rect_str(text),
            ))
            break


def _sanitize_block_recursive(
    block: FreeformBlock,
    page_id: str,
    edits: List[SanitizeEdit],
) -> None:
    before_rect = _rect_str(block)
    before_content = str(block.content or "")
    before_z = int(block.z_index or 0)
    applied: List[str] = []
    applied.extend(_sanitize_line_zero_geometry(block))
    applied.extend(_sanitize_text_html_leak(block))
    applied.extend(_sanitize_evidence_id_leak(block))
    applied.extend(_sanitize_decoration_zero_geometry(block))
    applied.extend(_sanitize_full_page_background_z(block))
    applied.extend(_sanitize_line_z_order(block))
    for rule in applied:
        if rule in {"text_html_leak", "evidence_id_leak"}:
            edits.append(SanitizeEdit(
                page_id=page_id,
                block_id=str(block.id or ""),
                rule=rule,
                before=f"content_len={len(before_content)}",
                after=f"content_len={len(str(block.content or ''))}",
            ))
        elif rule == "line_z_order_clamp":
            edits.append(SanitizeEdit(
                page_id=page_id,
                block_id=str(block.id or ""),
                rule=rule,
                before=f"z={before_z}",
                after=f"z={int(block.z_index or 0)}",
            ))
        elif rule == "full_page_background_z_reset":
            edits.append(SanitizeEdit(
                page_id=page_id,
                block_id=str(block.id or ""),
                rule=rule,
                before=f"z={before_z} role={str(block.role or '').strip() or 'none'} area={float(block.w or 0.0) * float(block.h or 0.0):.3f}",
                after=f"z={int(block.z_index or 0)} role={str(block.role or '').strip() or 'none'}",
            ))
        else:
            edits.append(SanitizeEdit(
                page_id=page_id,
                block_id=str(block.id or ""),
                rule=rule,
                before=before_rect,
                after=_rect_str(block),
            ))
    for child in list(block.children or []):
        _sanitize_block_recursive(child, page_id, edits)


def sanitize_deck(blueprint: FreeformDeckBlueprint) -> FreeformDeckBlueprint:
    """Return a new blueprint with structural sanitation applied.

    Writes one WARNING per edit. Never raises on sanitize logic errors — each
    rule is wrapped so a bug in one rule cannot take down the pipeline.
    """
    prepared = blueprint.model_copy(deep=True)
    all_edits: List[SanitizeEdit] = []
    for page in list(prepared.pages or []):
        page_id = str(page.page_id or "").strip()
        for block in list(page.blocks or []):
            try:
                _sanitize_block_recursive(block, page_id, all_edits)
            except Exception:
                logger.warning(
                    "presentation_sanitizer_block_failed page_id=%s block_id=%s",
                    page_id,
                    str(block.id or ""),
                    exc_info=True,
                )
        # Page-level rules run AFTER per-block fixes so they see the
        # geometry post-cleanup (e.g., a connector line that just got
        # rescued from zero-geometry now has its real bbox).
        try:
            _sanitize_text_over_container_collision(page, page_id, all_edits)
        except Exception:
            logger.warning(
                "presentation_sanitizer_page_rule_failed page_id=%s rule=text_over_container_collision",
                page_id,
                exc_info=True,
            )
        try:
            _sanitize_text_contrast(page, page_id, all_edits)
        except Exception:
            logger.warning(
                "presentation_sanitizer_page_rule_failed page_id=%s rule=text_contrast_repair",
                page_id,
                exc_info=True,
            )
    if all_edits:
        logger.warning(
            "presentation_structural_sanitize deck_id=%s edit_count=%s edits=%s",
            str(prepared.deck_id or "").strip(),
            len(all_edits),
            [
                {
                    "page_id": e.page_id,
                    "block_id": e.block_id,
                    "rule": e.rule,
                    "before": e.before,
                    "after": e.after,
                }
                for e in all_edits
            ],
        )
    else:
        logger.warning(
            "presentation_structural_sanitize deck_id=%s edit_count=0 (clean)",
            str(prepared.deck_id or "").strip(),
        )
    return prepared


def sanitize_page_blocks(blocks: List[Any]) -> tuple[List[SanitizeEdit], List[Any]]:
    """Offline replay entrypoint — operate on a list of plain dict blocks or
    FreeformBlock objects, return the edits and the mutated copies. Used by
    the offline replay test to verify sanitizer idempotence on clean pages."""
    edits: List[SanitizeEdit] = []
    out: List[Any] = []
    for b in list(blocks or []):
        if isinstance(b, FreeformBlock):
            block = b.model_copy(deep=True)
        elif isinstance(b, dict):
            block = FreeformBlock.model_validate(b)
        else:
            out.append(b)
            continue
        _sanitize_block_recursive(block, page_id="replay", edits=edits)
        out.append(block)
    return edits, out
