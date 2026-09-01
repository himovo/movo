"""Extract compact text inserted into an otherwise stable browser page."""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import List


def compact_insertions(
    before: str,
    after: str,
    *,
    max_chars: int = 240,
    minimum_retained_ratio: float = 0.55,
) -> List[str]:
    """Return a small newly inserted fragment from two flattened page texts.

    SPA observations often flatten the entire accessibility tree into one long
    line. A toast or inline validation message then becomes invisible to
    line-based status extraction. This function only returns a fragment when
    most of the prior page is retained, so full navigation changes are not
    mistaken for operation feedback.
    """
    old = _normalise(before)
    new = _normalise(after)
    if not old or not new or old == new:
        return []

    prefix = _common_prefix_length(old, new)
    suffix = _common_suffix_length(old, new, prefix)
    retained = prefix + suffix
    if retained / max(1, len(old)) >= minimum_retained_ratio:
        end = len(new) - suffix if suffix else len(new)
        inserted = _clean_fragment(new[prefix:end])
        if inserted and len(inserted) <= max_chars:
            return [inserted]

    # Dynamic counters or timestamps can invalidate a single prefix/suffix
    # comparison even though the page itself is stable. Sequence matching
    # isolates each newly inserted/replaced block without relying on site text.
    matcher = SequenceMatcher(a=old, b=new, autojunk=True)
    if matcher.quick_ratio() < minimum_retained_ratio:
        return []
    candidates: List[str] = []
    seen = set()
    for tag, _old_start, _old_end, new_start, new_end in matcher.get_opcodes():
        if tag not in {"insert", "replace"}:
            continue
        fragment = _clean_fragment(new[new_start:new_end])
        if (
            not fragment
            or len(fragment) > max_chars
            or fragment in seen
        ):
            continue
        seen.add(fragment)
        candidates.append(fragment)
        if len(candidates) >= 6:
            break
    return candidates


def _common_prefix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def _common_suffix_length(left: str, right: str, prefix: int) -> int:
    limit = min(len(left), len(right)) - prefix
    index = 0
    while index < limit and left[-(index + 1)] == right[-(index + 1)]:
        index += 1
    return index


def _normalise(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _clean_fragment(value: str) -> str:
    return str(value or "").strip(" \t\r\n|·•,，;；:：-—")


__all__ = ["compact_insertions"]
