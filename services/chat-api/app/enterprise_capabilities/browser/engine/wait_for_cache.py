"""Safety policy for reusing refs returned by ``browser_wait_for``.

DOM refs are observation-local. A ref may point at a different element after
an SPA render, so the executor may only reuse a rule-confirmed click target
while its URL, role and visible label still match the current observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional
import unicodedata


_INTERACTIVE_ROLES = {
    "button", "link", "menuitem", "tab", "option", "checkbox", "radio", "switch", "treeitem",
}


@dataclass(frozen=True)
class WaitForClickTarget:
    ref: str
    url: str
    label: str
    role: str
    backend_node_id: str = ""
    selector: str = ""
    scope_id: str = ""


def confirmed_click_target(result: Any) -> Optional[WaitForClickTarget]:
    if not isinstance(result, Mapping):
        return None
    if result.get("model_required") or result.get("resolution") != "action_rule":
        return None
    ref = str(result.get("clickable_ref") or "").strip()
    observation = result.get("observation")
    if not ref or not isinstance(observation, Mapping):
        return None
    element = _find_ref(observation.get("elements") or [], ref)
    if element is None:
        return None
    role = str(element.get("role") or "").strip().lower()
    label = _label(element)
    if role not in _INTERACTIVE_ROLES or not label:
        return None
    return WaitForClickTarget(
        ref=ref,
        url=str(observation.get("url") or "").strip(),
        label=label,
        role=role,
        backend_node_id=str(element.get("backendNodeId") or "").strip(),
        selector=str(element.get("selector") or "").strip(),
        scope_id=str(element.get("scopeId") or "").strip(),
    )


def can_reuse_click_target(target: WaitForClickTarget, observation: Any) -> bool:
    if target is None or observation is None:
        return False
    url = str(getattr(observation, "url", "") or "").strip()
    elements = getattr(observation, "elements", []) or []
    if not url or url != target.url:
        return False
    element = _find_ref(elements, target.ref)
    if element is None:
        return False
    if str(element.get("role") or "").strip().lower() != target.role or _label(element) != target.label:
        return False
    stable_pairs = (
        (target.backend_node_id, str(element.get("backendNodeId") or "").strip()),
        (target.selector, str(element.get("selector") or "").strip()),
        (target.scope_id, str(element.get("scopeId") or "").strip()),
    )
    return all(not expected or expected == actual for expected, actual in stable_pairs)


def _find_ref(elements: Iterable[Any], ref: str) -> Optional[Mapping[str, Any]]:
    for element in elements:
        if isinstance(element, Mapping) and str(element.get("ref") or "").strip() == ref:
            return element
    return None


def _label(element: Mapping[str, Any]) -> str:
    value = str(element.get("name") or element.get("text") or "")
    return " ".join(unicodedata.normalize("NFKC", value).lower().split())
