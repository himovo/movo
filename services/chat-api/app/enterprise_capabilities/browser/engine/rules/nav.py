"""Cross-cutting navigation primitives.

Tab switching, search boxes, modal closing, loading-spinner detection —
helpers any task context may consume in its before_decision hook so
the LLM doesn't have to fiddle with them.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import matchers as M
from .candidate_set import CandidateSet
from .tokens import SEARCH, CANCEL


def find_close_modal(elements: List[Dict[str, Any]]) -> CandidateSet:
    """Find the close button of any currently-open modal / dialog.
    Returns empty when no dialog is open."""
    if not M.dialog_open(elements):
        return CandidateSet(op="close_modal", tier=0, items=[], reason="no_dialog")
    named: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict) or not M.is_interactive(el):
            continue
        if M.has_any_token(el, CANCEL) and M.name_text(el):
            named.append(M.entry(el))
    if named:
        return CandidateSet(op="close_modal", tier=1, items=named[:4], reason="close_modal:named")
    return CandidateSet(op="close_modal", tier=3, items=[], reason="close_modal:no_match")


def find_search_box(elements: List[Dict[str, Any]]) -> CandidateSet:
    """Locate a searchbox / search-input. Works on searchbox role AND
    textbox role with name/description matching search tokens."""
    hits: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        role = str(el.get("role") or "").lower()
        if role == "searchbox":
            hits.append(M.entry(el))
        elif role == "textbox" and M.has_any_token(el, SEARCH):
            hits.append(M.entry(el))
    if hits:
        return CandidateSet(op="search", tier=1, items=hits[:4], reason="search:matched")
    return CandidateSet(op="search", tier=3, items=[], reason="search:no_match")


def find_tab(elements: List[Dict[str, Any]], label: str) -> CandidateSet:
    """Find a tab whose name contains ``label``. Simple substring match
    because tabs tend to have short, unambiguous names."""
    needle = (label or "").strip().lower()
    if not needle:
        return CandidateSet(op="tab", tier=3, items=[], reason="tab:no_label")
    hits: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        role = str(el.get("role") or "").lower()
        if role == "tab" and needle in str(el.get("name") or "").lower():
            hits.append(M.entry(el))
    if hits:
        return CandidateSet(op="tab", tier=1, items=hits[:4], reason=f"tab:{label}")
    return CandidateSet(op="tab", tier=3, items=[], reason="tab:no_match")


def is_page_busy(elements: List[Dict[str, Any]]) -> bool:
    """True when a loading spinner is visible. Callers typically hold
    off on new clicks for one turn so the spinner clears."""
    return M.loading_signal(elements)
