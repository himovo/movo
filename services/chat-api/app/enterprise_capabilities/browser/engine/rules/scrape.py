"""Scrape / extraction navigation rules.

Used by scrape_extract tasks that walk through a list of entities and
collect data. Responsibilities:
  - find the "next page" or "load more" control
  - detect that pagination has ended (no next control, same rows twice,
    or an empty-state marker)
  - identify row-level structure so the LLM can be told "extract these"
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import matchers as M
from .candidate_set import CandidateSet
from .tokens import NEXT, LOAD_MORE, PREV


def find_next_page(elements: List[Dict[str, Any]]) -> CandidateSet:
    """Prefer an explicit Next button; fall back to Load More. Returns
    AUTO_EXECUTE when exactly one matches."""
    for tokens, label in ((NEXT, "next"), (LOAD_MORE, "load_more")):
        named: List[Dict[str, Any]] = []
        icon: List[Dict[str, Any]] = []
        for el in elements:
            if not isinstance(el, dict) or not M.is_interactive(el):
                continue
            if M.has_any_token(el, tokens):
                (named if M.name_text(el) else icon).append(M.entry(el))
        if named:
            return CandidateSet(op=f"scrape:{label}", tier=1,
                                items=named[:4], reason=f"scrape:{label}:named")
        if icon:
            return CandidateSet(op=f"scrape:{label}", tier=2,
                                items=icon[:4], reason=f"scrape:{label}:icon")
    return CandidateSet(op="scrape:next", tier=3, items=[], reason="scrape:no_next")


def detect_list_end(
    elements: List[Dict[str, Any]],
    *, prev_row_fingerprint: Optional[int] = None,
) -> Dict[str, Any]:
    """Return {'ended': bool, 'reason': str}.

    End signals:
      - no NEXT/LOAD_MORE candidate present
      - NEXT candidate exists but is disabled (role=button + aria-disabled)
      - row fingerprint identical to previous page (stuck)
    """
    # 1) no next at all
    nxt = find_next_page(elements)
    if nxt.action == "fallback" or not nxt.items:
        return {"ended": True, "reason": "no_next_control"}

    # 2) next exists but looks disabled — the observer may or may not
    # surface aria-disabled; if we can see it, respect it.
    for el in elements:
        if not isinstance(el, dict):
            continue
        if el.get("ref") == nxt.items[0].get("ref"):
            desc = M.description_text(el).lower()
            if "disabled" in desc or "is-disabled" in desc:
                return {"ended": True, "reason": "next_disabled"}
            break

    # 3) same rows as last page
    if prev_row_fingerprint is not None:
        cur = _row_fingerprint(elements)
        if cur == prev_row_fingerprint:
            return {"ended": True, "reason": "rows_unchanged"}

    return {"ended": False, "reason": ""}


def _row_fingerprint(elements: List[Dict[str, Any]]) -> int:
    """Hash of visible row names, used to detect "clicked next but
    nothing changed" (common when we're on the last page)."""
    rows = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        role = str(el.get("role") or "").lower()
        if role in ("row", "listitem", "gridcell"):
            rows.append(str(el.get("name") or "")[:60])
    return hash(tuple(sorted(rows)))


def extract_row_candidates(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return the set of elements that look like data rows. The LLM
    uses this when it needs to decide "which columns / fields to
    extract". Rule can't do the extraction itself — only surface the
    row set."""
    out: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        role = str(el.get("role") or "").lower()
        if role in ("row", "listitem", "gridcell"):
            out.append(M.entry(el))
    return out
