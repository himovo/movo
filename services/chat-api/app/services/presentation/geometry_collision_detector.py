"""Pure-geometry collision detector for presentation page blueprints.

Detects pairs of top-level page blocks whose normalized [0,1] rectangles
overlap in a way that is almost certainly a layout error — the kind of
defect that the multimodal QC inspector currently catches at huge time
and token cost. The detector takes 1-2 ms per page and is 100% accurate
on the things it inspects, freeing the multimodal QC to focus on
genuinely visual issues like contrast, text truncation, or semantic
mismatches.

Scope on purpose: only top-level page blocks. Recursive descent into
group children is intentionally NOT done because:
  1. Children of a group are by definition contained in their parent,
     so the most common failure mode (sibling-vs-sibling collision) is
     already captured at the top level.
  2. Children typically use parent-relative coordinates, requiring
     coordinate-space translation to compare meaningfully against any
     non-sibling. We can add this in a follow-up if the data shows we
     need it.

The output is a list of ``CollisionDefect`` records with enough detail
that a downstream repair LLM can fix each defect with a single targeted
edit, without re-examining a screenshot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from app.services.presentation.contracts import (
    FreeformBlock,
    FreeformDeckBlueprint,
    FreeformPageBlueprint,
)

logger = logging.getLogger(__name__)


# Tuning constants — chosen to fire on real defects but ignore touching/
# adjacent blocks. All values are normalized to the [0,1] canvas.
_MIN_OVERLAP_AREA = 0.0006        # ~0.06% of canvas, ~1245px² @1080p
_MIN_OVERLAP_RATIO = 0.08         # at least 8% of the smaller block must be eaten
_CONTAINMENT_SLACK = 0.01         # 1% slack when checking "A inside B"
_LINE_THROUGH_CARD_RATIO = 0.35   # line counts as crossing a card if >35% of its length is inside
_HARD_OVERLAP_RATIO = 0.30        # ≥30% of the smaller block eaten = always defect

# Roles
_BACKGROUND_ROLES = frozenset({"background", "surface", "bg", "backdrop"})
_CONTAINER_ROLES = frozenset({"panel", "band", "hero", "card", "group", "container"})
# Generic decorative shape roles whose owners function as containers when
# they geometrically contain other top-level blocks. These don't declare
# explicit container_id, so we infer "this is a container" from geometry.
_CONTAINER_LIKE_SHAPE_ROLES = frozenset({"shape", "matrix", "frame", "region", "panel"})
_TITLE_ROLES_STRICT = frozenset({"title", "headline", "heading"})
_BODY_ROLES = frozenset({"body", "subtitle", "label", "caption", "subline"})
_TITLE_ROLES = _TITLE_ROLES_STRICT | _BODY_ROLES
_TEXT_TYPES = frozenset({"text_box"})
_LINE_TYPES = frozenset({"line"})
_DECORATION_TYPES = frozenset({"rectangle", "image", "group", "icon", "circle"})

# A title-vs-body text pair is allowed to "overlap" by up to this fraction
# of the smaller block's area before being flagged. The LLM idiom is to
# place a subline immediately below a headline so that the headline's text
# bottom and the subline's text top brush against each other; the rendered
# text doesn't actually collide because each text_box has line-height
# padding around the visible glyphs. Anything below this threshold is
# treated as the intentional stack idiom, anything above is a true bug.
_TITLE_BODY_STACK_TOLERANCE_RATIO = 0.50


@dataclass
class CollisionDefect:
    """One pair of overlapping blocks worth reporting."""
    page_id: str
    block_a_id: str
    block_b_id: str
    block_a_type: str
    block_b_type: str
    block_a_role: str
    block_b_role: str
    overlap_area: float
    smaller_block_eaten_ratio: float
    severity: str  # high | medium | low
    kind: str      # one of: text_over_text, text_over_card, card_over_card,
                   # line_through_card, text_over_panel
    note: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_id": self.page_id,
            "block_ids": [self.block_a_id, self.block_b_id],
            "kind": self.kind,
            "severity": self.severity,
            "note": self.note,
            "overlap_area": round(self.overlap_area, 6),
            "smaller_block_eaten_ratio": round(self.smaller_block_eaten_ratio, 4),
            "meta": {
                "block_a": {"id": self.block_a_id, "type": self.block_a_type, "role": self.block_a_role},
                "block_b": {"id": self.block_b_id, "type": self.block_b_type, "role": self.block_b_role},
            },
        }


@dataclass
class PageCollisionReport:
    page_id: str
    defects: List[CollisionDefect] = field(default_factory=list)

    @property
    def has_issue(self) -> bool:
        return bool(self.defects)


@dataclass
class DeckCollisionReport:
    deck_id: str
    pages: List[PageCollisionReport] = field(default_factory=list)

    @property
    def failed_page_ids(self) -> List[str]:
        return [p.page_id for p in self.pages if p.has_issue]

    @property
    def total_defect_count(self) -> int:
        return sum(len(p.defects) for p in self.pages)


# ── Geometry primitives ──────────────────────────────────────────────────


def _rect(b: FreeformBlock) -> Tuple[float, float, float, float]:
    return (
        float(b.x or 0.0),
        float(b.y or 0.0),
        float(b.w or 0.0),
        float(b.h or 0.0),
    )


def _area(rect: Tuple[float, float, float, float]) -> float:
    return max(0.0, rect[2]) * max(0.0, rect[3])


def _overlap_area(a: FreeformBlock, b: FreeformBlock) -> float:
    ax, ay, aw, ah = _rect(a)
    bx, by, bw, bh = _rect(b)
    dx = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    dy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    return dx * dy


def _is_contained(inner: FreeformBlock, outer: FreeformBlock) -> bool:
    """True iff ``inner`` is geometrically inside ``outer`` (with slack)."""
    ix, iy, iw, ih = _rect(inner)
    ox, oy, ow, oh = _rect(outer)
    return (
        ix >= ox - _CONTAINMENT_SLACK
        and iy >= oy - _CONTAINMENT_SLACK
        and ix + iw <= ox + ow + _CONTAINMENT_SLACK
        and iy + ih <= oy + oh + _CONTAINMENT_SLACK
    )


def _line_endpoints(b: FreeformBlock) -> Tuple[float, float, float, float]:
    """Resolve a line block's (x1, y1, x2, y2) using either x2/y2 or w/h."""
    x1 = float(b.x or 0.0)
    y1 = float(b.y or 0.0)
    if b.x2 is not None and b.y2 is not None:
        return (x1, y1, float(b.x2), float(b.y2))
    return (x1, y1, x1 + float(b.w or 0.0), y1 + float(b.h or 0.0))


def _line_segment_inside_rect_ratio(line: FreeformBlock, rect: FreeformBlock) -> float:
    """Approx fraction of a line segment that lies inside the given rect.

    Uses Liang-Barsky-style 1D parametric clipping. Returns 0 if disjoint,
    1.0 if fully inside, and a fractional value otherwise.
    """
    x1, y1, x2, y2 = _line_endpoints(line)
    rx, ry, rw, rh = _rect(rect)
    rx2, ry2 = rx + rw, ry + rh
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - rx), (dx, rx2 - x1), (-dy, y1 - ry), (dy, ry2 - y1)):
        if abs(p) < 1e-12:
            if q < 0:
                return 0.0
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return 0.0
            if t > t0:
                t0 = t
        else:
            if t < t0:
                return 0.0
            if t < t1:
                t1 = t
    return max(0.0, t1 - t0)


# ── Exemption rules ──────────────────────────────────────────────────────


def _is_background(b: FreeformBlock) -> bool:
    """Background-like block detection.

    A block is treated as a background (and exempt from overlap rules) when
    any of these is true:

      1. role is one of {background, surface, bg, backdrop}.
      2. z=0 AND covers ≥85% of canvas in BOTH dimensions — full-bleed
         background that the LLM mislabeled as panel/hero/etc.
      3. z=0 AND full-canvas-width (w ≥ 0.95) — a horizontal banner or hero
         strip used as background scenery for content that overlays it
         (page_06's hero_panel pattern: w=1.0 h=0.62 z=0). Width is the
         load-bearing part: a full-width strip that's not at z=0 would be
         a real card and we shouldn't exempt it.
    """
    if str(b.role or "").strip().lower() in _BACKGROUND_ROLES:
        return True
    if int(b.z_index or 0) == 0:
        w = float(b.w or 0.0)
        h = float(b.h or 0.0)
        if w >= 0.85 and h >= 0.85:
            return True
        if w >= 0.95:
            return True
    return False


def _is_title_body_stack(a: FreeformBlock, b: FreeformBlock, eaten_ratio: float) -> bool:
    """The standard "heading above body, body brushes the bottom of heading" idiom.

    Returns True iff:
      - both blocks are text_box,
      - both have a heading-family role (title/heading/subtitle/label/body/caption/subline),
      - the visible text rectangles overlap by less than the stack tolerance.

    The pairing used to require a strict title role on one side and a body role
    on the other, but the LLM also routinely emits headline+subtitle where BOTH
    are tagged ``role=title``. Those are visually identical stacks and must also
    be exempted, or page_03-style false positives creep in.
    """
    if str(a.type or "").strip().lower() != "text_box":
        return False
    if str(b.type or "").strip().lower() != "text_box":
        return False
    role_a = str(a.role or "").strip().lower()
    role_b = str(b.role or "").strip().lower()
    if role_a not in _TITLE_ROLES or role_b not in _TITLE_ROLES:
        return False
    return eaten_ratio < _TITLE_BODY_STACK_TOLERANCE_RATIO


def _is_container_role(b: FreeformBlock) -> bool:
    return str(b.role or "").strip().lower() in _CONTAINER_ROLES


def _declared_parent_of(child: FreeformBlock, parent: FreeformBlock) -> bool:
    """Did the LLM declare ``child.container_id`` to point at ``parent.id``?"""
    cid = str(child.container_id or "").strip()
    pid = str(parent.id or "").strip()
    return bool(cid and pid and cid == pid)


def _is_container_like_shape(b: FreeformBlock) -> bool:
    """A rectangle/group that's clearly used as a "container shape".

    LLMs sometimes label a wrapping rectangle with role=shape/matrix/region
    instead of role=panel. Treat it as a container as long as it's a
    rectangle or group at low z-order. We require the block to be a
    decoration type (rectangle/group) to avoid accidentally exempting a
    text or icon that happens to bear one of these roles.
    """
    btype = str(b.type or "").strip().lower()
    if btype not in {"rectangle", "group"}:
        return False
    return str(b.role or "").strip().lower() in _CONTAINER_LIKE_SHAPE_ROLES


def _is_legal_containment(a: FreeformBlock, b: FreeformBlock) -> bool:
    """True if A and B's overlap is a legal containment relationship.

    Cases handled:
      1. Either side is a full-page background.
      2. Either side declared the other as its container_id AND is
         geometrically inside it.
      3. One side is a panel/band/hero/card-role container and the other
         is geometrically inside it (declarative containment without an
         explicit container_id link — common LLM idiom).
      4. Either side is a container-like decorative shape (role=shape/
         matrix/region/panel rectangle) and the other is geometrically
         inside it.
    """
    if _is_background(a) or _is_background(b):
        return True
    if _declared_parent_of(a, b) and _is_contained(a, b):
        return True
    if _declared_parent_of(b, a) and _is_contained(b, a):
        return True
    if _is_container_role(b) and _is_contained(a, b):
        return True
    if _is_container_role(a) and _is_contained(b, a):
        return True
    if _is_container_like_shape(b) and _is_contained(a, b):
        return True
    if _is_container_like_shape(a) and _is_contained(b, a):
        return True
    return False


# ── Pair classification ──────────────────────────────────────────────────


def _classify(
    a: FreeformBlock,
    b: FreeformBlock,
    overlap_area: float,
    smaller_eaten: float,
    *,
    page_line_count: int = 0,
) -> Tuple[str, str, str] | None:
    """Return (kind, severity, note) for a non-exempt overlap, or None to skip.

    ``page_line_count`` is the number of top-level ``type=line`` blocks on
    the same page as ``a`` and ``b``. It is used by the line-vs-card
    decoration cluster exemption — see the comment near the line branch
    below.
    """
    a_type = str(a.type or "").strip().lower()
    b_type = str(b.type or "").strip().lower()
    a_role = str(a.role or "").strip().lower()
    b_role = str(b.role or "").strip().lower()

    a_is_text = a_type in _TEXT_TYPES
    b_is_text = b_type in _TEXT_TYPES
    a_is_line = a_type in _LINE_TYPES
    b_is_line = b_type in _LINE_TYPES
    a_is_decor = a_type in _DECORATION_TYPES
    b_is_decor = b_type in _DECORATION_TYPES

    if a_is_text and b_is_text:
        return (
            "text_over_text",
            "high",
            f"Two text boxes overlap by {smaller_eaten*100:.0f}% of the smaller block.",
        )

    if (a_is_text and b_is_decor) or (b_is_text and a_is_decor):
        text_block = a if a_is_text else b
        other = b if a_is_text else a
        text_role = str(text_block.role or "").strip().lower()
        other_role = str(other.role or "").strip().lower()
        if text_role in _TITLE_ROLES:
            return (
                "text_over_card" if other_role not in _CONTAINER_ROLES else "text_over_panel",
                "high",
                f"Title-role text '{text_block.id}' overlaps {other_role or other.type} '{other.id}' "
                f"by {smaller_eaten*100:.0f}% of the smaller block.",
            )
        return (
            "text_over_card",
            "high",
            f"Text '{text_block.id}' overlaps {other_role or other.type} '{other.id}' "
            f"by {smaller_eaten*100:.0f}% of the smaller block.",
        )

    if a_is_decor and b_is_decor:
        # Image / chart underlay exemption: a decorative image or chart that
        # sits behind a content block (lower z) is a deliberate layered
        # composition (hero with title overlay, infographic with caption,
        # etc.). Skip light overlaps; only flag if the eaten ratio is large
        # enough to look like a real positioning bug.
        a_is_pictorial = a_type in {"image", "chart"}
        b_is_pictorial = b_type in {"image", "chart"}
        if a_is_pictorial or b_is_pictorial:
            pictorial = a if a_is_pictorial else b
            other = b if a_is_pictorial else a
            if int(pictorial.z_index or 0) <= int(other.z_index or 0):
                if smaller_eaten < _HARD_OVERLAP_RATIO:
                    return None
        a_is_container = a_role in _CONTAINER_ROLES
        b_is_container = b_role in _CONTAINER_ROLES
        if a_is_container and b_is_container:
            severity = "high" if smaller_eaten >= _HARD_OVERLAP_RATIO else "medium"
            return (
                "card_over_card",
                severity,
                f"Two container blocks overlap by {smaller_eaten*100:.0f}% of the smaller block.",
            )
        return (
            "card_over_card",
            "medium",
            f"Two decoration blocks overlap by {smaller_eaten*100:.0f}% of the smaller block.",
        )

    if a_is_line or b_is_line:
        # Two lines crossing each other are decoration art, not a defect.
        if a_is_line and b_is_line:
            return None
        line = a if a_is_line else b
        other = b if a_is_line else a
        # A line passing through a container-like shape (network overlay,
        # frame rectangle, etc.) is intentional decoration. The container-
        # like exemption above already drops lines fully inside such a
        # shape, but partial-cross cases need this guard.
        if _is_container_like_shape(other):
            return None
        # Decorative line cluster exemption: when the page has 3+ lines AND
        # the offending line sits BEHIND the card it crosses (line.z < other.z),
        # the line is part of a hero / network-art composition rather than a
        # mispositioned connector. Real connector defects almost always
        # involve 1-2 lines on a structured page; decorative line clusters
        # are typically 3+ lines on a hero / opening / closing slide. This
        # combination of "≥3 lines on the page" + "rendered behind the card"
        # is a tight enough trigger to exempt page_01-style hero art without
        # falsely exempting page_03-style real connectors.
        if (
            page_line_count >= 3
            and int(line.z_index or 0) < int(other.z_index or 0)
        ):
            return None
        ratio = _line_segment_inside_rect_ratio(line, other)
        if ratio >= _LINE_THROUGH_CARD_RATIO:
            return (
                "line_through_card",
                "high",
                f"Line '{line.id}' passes through {other.type} '{other.id}' "
                f"({ratio*100:.0f}% of the line is inside).",
            )
        return None

    return None


# Empty-group detector tunables
_EMPTY_GROUP_MIN_AREA = 0.06   # group must cover ≥6% of canvas to count as carrier
_EMPTY_GROUP_MIN_W = 0.20      # group must be wider than this to be a real region
_EMPTY_GROUP_MIN_H = 0.10      # group must be taller than this


def _has_substantive_descendant(block: FreeformBlock) -> bool:
    """True if ``block`` or any descendant carries actual visible content.

    Substantive = anything a viewer would perceive as information:
      - text_box with non-empty content
      - icon (always — an icon is a meaningful visual)
      - image
      - chart
    Lines, empty rectangles, and bare groups don't count.
    """
    btype = str(block.type or "").strip().lower()
    if btype == "text_box":
        if str(block.content or "").strip():
            return True
    elif btype == "icon":
        return True
    elif btype == "image":
        return True
    elif btype == "chart":
        return True
    for child in list(block.children or []):
        if _has_substantive_descendant(child):
            return True
    return False


def _scan_empty_group_carriers(
    page_id: str,
    blocks: List[FreeformBlock],
) -> List[CollisionDefect]:
    """Find groups that take up real estate but carry no visible content.

    A group is flagged when ALL of these are true:
      1. ``type=group``
      2. covers ≥6% of canvas area AND ≥0.20 wide AND ≥0.10 tall
      3. has no substantive descendants (no text/icon/image/chart anywhere
         in its subtree, regardless of nesting depth)

    The walk is recursive — a deeply nested empty group still flags. The
    minimum-area gate prevents flagging tiny decorative groups (e.g. a
    custom badge made of pure rectangles).
    """
    defects: List[CollisionDefect] = []

    def _walk(block: FreeformBlock) -> None:
        btype = str(block.type or "").strip().lower()
        if btype == "group":
            w = float(block.w or 0.0)
            h = float(block.h or 0.0)
            area = w * h
            big_enough = (
                area >= _EMPTY_GROUP_MIN_AREA
                and w >= _EMPTY_GROUP_MIN_W
                and h >= _EMPTY_GROUP_MIN_H
            )
            if big_enough and not _has_substantive_descendant(block):
                bid = str(block.id or "").strip()
                defects.append(CollisionDefect(
                    page_id=page_id,
                    block_a_id=bid,
                    block_b_id="",
                    block_a_type="group",
                    block_b_type="",
                    block_a_role=str(block.role or "").strip(),
                    block_b_role="",
                    overlap_area=area,
                    smaller_block_eaten_ratio=0.0,
                    severity="high",
                    kind="empty_group_carrier",
                    note=(
                        f"Group '{bid}' covers {area*100:.0f}% of the canvas "
                        f"({w*100:.0f}% × {h*100:.0f}%) but has no text, icons, "
                        f"images, or charts inside. The page region is visually empty."
                    ),
                ))
        for child in list(block.children or []):
            _walk(child)

    for top in blocks:
        _walk(top)
    return defects


# ── Top-level entry points ───────────────────────────────────────────────


def detect_page_collisions(
    page: FreeformPageBlueprint,
) -> PageCollisionReport:
    """Scan one page for top-level block collisions."""
    page_id = str(page.page_id or "").strip()
    report = PageCollisionReport(page_id=page_id)
    blocks = list(page.blocks or [])

    # Empty-group carrier scan runs even on single-block pages, so it sits
    # before the early return below.
    report.defects.extend(_scan_empty_group_carriers(page_id, blocks))

    if len(blocks) < 2:
        return report

    page_line_count = sum(
        1 for b in blocks
        if str(b.type or "").strip().lower() in _LINE_TYPES
    )

    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            a, b = blocks[i], blocks[j]
            if _is_legal_containment(a, b):
                continue
            area = _overlap_area(a, b)
            if area < _MIN_OVERLAP_AREA:
                continue
            area_a = _area(_rect(a))
            area_b = _area(_rect(b))
            smaller = min(area_a, area_b)
            if smaller <= 0:
                continue
            ratio = area / smaller
            # Title-vs-body stack idiom (subline brushing the bottom of a
            # headline) is the LLM's standard way of placing a two-line
            # heading. Skip these unless the overlap is severe.
            if _is_title_body_stack(a, b, ratio):
                continue
            # Lines need their own threshold based on segment-inside-rect,
            # not bbox overlap, so let _classify handle them via line ratio
            # without an early ratio gate.
            a_is_line = str(a.type or "").strip().lower() in _LINE_TYPES
            b_is_line = str(b.type or "").strip().lower() in _LINE_TYPES
            if not (a_is_line or b_is_line) and ratio < _MIN_OVERLAP_RATIO:
                continue
            classification = _classify(a, b, area, ratio, page_line_count=page_line_count)
            if classification is None:
                continue
            kind, severity, note = classification
            report.defects.append(CollisionDefect(
                page_id=page_id,
                block_a_id=str(a.id or "").strip(),
                block_b_id=str(b.id or "").strip(),
                block_a_type=str(a.type or "").strip(),
                block_b_type=str(b.type or "").strip(),
                block_a_role=str(a.role or "").strip(),
                block_b_role=str(b.role or "").strip(),
                overlap_area=area,
                smaller_block_eaten_ratio=ratio,
                severity=severity,
                kind=kind,
                note=note,
            ))
    return report


def detect_deck_collisions(
    blueprint: FreeformDeckBlueprint,
) -> DeckCollisionReport:
    """Scan every page in a deck for top-level block collisions."""
    deck_id = str(blueprint.deck_id or "").strip()
    deck_report = DeckCollisionReport(deck_id=deck_id)
    for page in list(blueprint.pages or []):
        page_report = detect_page_collisions(page)
        deck_report.pages.append(page_report)
    return deck_report
