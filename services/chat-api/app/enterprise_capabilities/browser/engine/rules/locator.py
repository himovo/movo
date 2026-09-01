"""User-authored locator matching — the fourth rule layer.

Both the manual "locator editor" (Line A) and the recording distiller
(Line B) emit the same ``Locator`` shape. At runtime this module is
called *before* the CRUD/form/scrape rule layers: if the user pre-bound
a step to a specific control, we skip rule inference and the LLM
entirely. When the locator matches zero or multiple elements we fall
through to the normal pipeline so a stale locator doesn't brick the
skill after a small UI change.

The schema is deliberately a *signal bag*, not a CSS selector. Every
field is optional and combined with AND. Callers pass in a variable
map (e.g. ``{"row_target": "张三"}``) so row-anchored locators can be
reused across rows.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional

from . import matchers as M
from .candidate_set import CandidateSet


_VAR_RE = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def interpolate(value: str, variables: Mapping[str, str] | None) -> str:
    """Replace ``${name}`` placeholders using ``variables``. Unknown
    names survive unchanged — callers can then decide to treat the
    locator as "no anchor provided" or to skip entirely."""
    if not value or not variables:
        return value
    def sub(m: re.Match[str]) -> str:
        key = m.group(1)
        return str(variables.get(key, m.group(0)))
    return _VAR_RE.sub(sub, value)


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _element_text(el: Dict[str, Any]) -> str:
    return f"{M.name_text(el)} {M.description_text(el)}".lower()


def _ancestor_haystack(
    el: Dict[str, Any], elements: List[Dict[str, Any]]
) -> str:
    """Best-effort ancestor text. The observer stamps each element with
    ``regionLabel`` (row / section / card text up to 6 ancestors); we
    use that as the ancestor signal. If the element also lives inside
    a dialog we include the dialog's accessible name too."""
    parts: List[str] = []
    desc = M.description_text(el)
    if desc:
        parts.append(desc)
    region = str(el.get("region_label") or el.get("regionLabel") or "")
    if region:
        parts.append(region)
    return " ".join(parts).lower()


def _match_one(
    locator: Dict[str, Any],
    el: Dict[str, Any],
    elements: List[Dict[str, Any]],
    variables: Mapping[str, str] | None,
) -> bool:
    if not isinstance(el, dict):
        return False

    role_want = _norm(locator.get("role"))
    if role_want and _norm(el.get("role")) != role_want:
        return False

    name_exact = str(locator.get("name") or "").strip()
    if name_exact and str(el.get("name") or "").strip() != name_exact:
        return False

    contains = str(locator.get("name_contains") or "").strip().lower()
    if contains and contains not in _element_text(el):
        return False

    aria = str(locator.get("aria_label") or "").strip().lower()
    if aria and aria not in _element_text(el):
        return False

    icon = str(locator.get("icon_class") or "").strip().lower()
    if icon:
        # Observer stamps iconfont / class info into description.
        if icon not in M.description_text(el).lower():
            return False

    text_want = str(locator.get("text") or "").strip().lower()
    if text_want and text_want not in _element_text(el):
        return False

    anc_role = _norm(locator.get("ancestor_role"))
    if anc_role:
        # Heuristic: observer's regionLabel includes the ancestor role
        # tag when one was found. Accept any haystack hit.
        if anc_role not in _ancestor_haystack(el, elements):
            return False

    anc_text = str(locator.get("ancestor_contains_text") or "").strip()
    if anc_text:
        resolved = interpolate(anc_text, variables).strip().lower()
        # Empty after interpolation ⇒ variable missing. Treat as "no
        # anchor", don't filter. Otherwise require it in the ancestor
        # haystack.
        if resolved and resolved not in _ancestor_haystack(el, elements):
            return False

    return True


def resolve(
    locator: Dict[str, Any] | None,
    elements: List[Dict[str, Any]],
    variables: Mapping[str, str] | None = None,
) -> CandidateSet:
    """Match ``locator`` against ``elements`` and return a CandidateSet.

    Matching AND-combines every non-empty locator field. ``nth`` (0-based)
    picks a specific hit when there are multiple structural matches — a
    last-resort position anchor emitted by the recorder when no stronger
    signal is available.
    """
    if not isinstance(locator, dict) or not locator:
        return CandidateSet(op="locator", tier=0, items=[], reason="locator:empty")
    hits: List[Dict[str, Any]] = []
    for el in elements or []:
        if _match_one(locator, el, list(elements or []), variables):
            hits.append(M.entry(el))

    nth = locator.get("nth")
    if isinstance(nth, int) and 0 <= nth < len(hits):
        picked = [hits[nth]]
        return CandidateSet(
            op="locator", tier=1, items=picked,
            reason=f"locator:nth={nth}/{len(hits)}",
        )

    if len(hits) == 1:
        return CandidateSet(op="locator", tier=1, items=hits, reason="locator:unique")
    if len(hits) > 1:
        # Surface to LLM picker rather than guessing.
        return CandidateSet(
            op="locator", tier=2, items=hits[:8],
            reason=f"locator:multi={len(hits)}",
        )
    return CandidateSet(op="locator", tier=3, items=[], reason="locator:no_match")


def extract_variables(goal_or_meta: Any) -> Dict[str, str]:
    """Best-effort pull of ``${vars}`` values from step meta / goal text.

    Today the only variable we care about is ``row_target`` (the row
    anchor for per-entity CRUD). Callers stash it into the step meta as
    ``locator_vars`` when they have it; otherwise an empty dict is fine
    — the interpolator will simply leave unknown placeholders alone and
    ``_match_one`` will treat them as "no anchor".
    """
    if isinstance(goal_or_meta, dict):
        vars_raw = goal_or_meta.get("locator_vars") or {}
        if isinstance(vars_raw, dict):
            return {str(k): str(v) for k, v in vars_raw.items()}
    return {}
