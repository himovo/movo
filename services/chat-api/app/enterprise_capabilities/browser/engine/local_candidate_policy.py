"""Conservative local selection for text-located browser action candidates.

This module deliberately handles only the case that does not need semantic
reasoning: one current, actionable element has a label exactly equal to the
requested text.  Ambiguous, partial, hidden, disabled, or unverified matches
remain model decisions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
import unicodedata
from typing import Any, Optional

from app.enterprise_capabilities.browser.engine.interaction_semantics import is_mutation_label
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


_ACTION_ROLES = {
    "button",
    "link",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "option",
    "tab",
    "treeitem",
}


def unique_exact_action_ref(
    *,
    query: str,
    candidates: Sequence[Mapping[str, str]],
    observation: Observation,
) -> Optional[str]:
    """Return a ref only for a unique, exact, currently actionable match."""

    wanted = _normalise_label(query)
    if not wanted or is_mutation_label(query):
        return None

    elements_by_ref = {
        str(item.get("ref") or "").strip(): item
        for item in list(observation.elements or [])
        if isinstance(item, Mapping) and str(item.get("ref") or "").strip()
    }
    exact_refs: list[str] = []
    for candidate in candidates:
        ref = str(candidate.get("ref") or "").strip()
        if not ref or _normalise_label(candidate.get("name")) != wanted:
            continue
        element = elements_by_ref.get(ref)
        if element is not None and is_actionable_candidate(element, candidate):
            exact_refs.append(ref)

    if len(set(exact_refs)) != 1:
        return None

    selected_ref = exact_refs[0]
    # Do not trust a truncated candidate list when the current snapshot exposes
    # another actionable element with the same exact accessible label.
    snapshot_matches = {
        ref
        for ref, element in elements_by_ref.items()
        if _normalise_label(element.get("name") or element.get("text")) == wanted
        and is_actionable_candidate(element, None)
    }
    return selected_ref if snapshot_matches == {selected_ref} else None


def _normalise_label(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip().casefold()


def is_actionable_candidate(
    element: Mapping[str, Any],
    candidate: Optional[Mapping[str, str]] = None,
) -> bool:
    role = str(element.get("role") or (candidate or {}).get("role") or "").strip().lower()
    if role not in _ACTION_ROLES:
        return False
    if element.get("visible") is False or element.get("disabled") is True:
        return False
    if element.get("inViewport") is False or element.get("hitTestable") is False:
        return False
    if element.get("activationVerified") is False:
        return False
    return True


__all__ = ["is_actionable_candidate", "unique_exact_action_ref"]
