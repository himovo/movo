"""Element-level predicates. Composable, site-agnostic.

Every function takes a single observed element dict (or a list of
them) and returns a bool / string. No class regex specific to any
component library — matching is on semantic role + verb tokens.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

# Observer emits this literal when it recognises an element as
# interactive but can't derive any accessible name. Treat it as empty
# for classification — useful info, if any, is in `description`.
UNLABELED_PLACEHOLDER = "<unlabeled icon>"

_INTERACTIVE_ROLES = ("button", "link", "menuitem")
_FIELD_ROLES = ("textbox", "combobox", "checkbox", "radio", "switch", "spinbutton", "searchbox")


def name_text(el: Dict[str, Any]) -> str:
    n = str(el.get("name") or "").strip()
    return "" if n == UNLABELED_PLACEHOLDER else n


def description_text(el: Dict[str, Any]) -> str:
    return str(el.get("description") or "").strip()


def haystack(el: Dict[str, Any]) -> str:
    """Lowercased combined text used for token matching."""
    return f"{name_text(el)} {description_text(el)}".lower()


def is_interactive(el: Dict[str, Any]) -> bool:
    return str(el.get("role") or "").lower() in _INTERACTIVE_ROLES


def is_field(el: Dict[str, Any]) -> bool:
    """True for form-input-like elements (textbox, select, switch, …)."""
    return str(el.get("role") or "").lower() in _FIELD_ROLES


def has_any_token(el: Dict[str, Any], tokens: Iterable[str]) -> bool:
    hay = haystack(el)
    return any(t in hay for t in tokens)


def is_unlabeled_icon(el: Dict[str, Any]) -> bool:
    """Interactive element with no accessible name. Callers decide
    whether to require a non-empty description."""
    return is_interactive(el) and not name_text(el)


def dialog_open(elements: List[Dict[str, Any]]) -> bool:
    return any(
        isinstance(e, dict)
        and str(e.get("role") or "").lower() in ("dialog", "alertdialog", "drawer")
        for e in elements
    )


def loading_signal(elements: List[Dict[str, Any]]) -> bool:
    """True when the page is advertising a busy / pending state.
    Callers (e.g. before_decision hooks) may choose to wait instead
    of submitting a click into a half-rendered page."""
    from .tokens import LOADING
    for e in elements:
        if not isinstance(e, dict):
            continue
        role = str(e.get("role") or "").lower()
        if role == "progressbar":
            return True
        if has_any_token(e, LOADING):
            return True
    return False


def entry(el: Dict[str, Any]) -> Dict[str, Any]:
    """Projection of an element into the candidate-list schema (ref +
    role + name + truncated description) seen by the LLM and the
    auto-execute path."""
    desc = description_text(el)[:80]
    return {
        "ref": el.get("ref"),
        "role": el.get("role"),
        "name": el.get("name"),
        "description": desc or None,
    }
