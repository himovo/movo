from __future__ import annotations

from collections.abc import Mapping
from typing import Any


CLICK_ROLES = frozenset({
    "button", "link", "menuitem", "menuitemcheckbox", "menuitemradio",
    "option", "tab", "treeitem", "checkbox", "radio", "switch",
})
EDIT_ROLES = frozenset({"textbox", "searchbox", "combobox", "listbox", "spinbutton"})


def element_can_receive(tool: str, element: object) -> bool:
    """Conservative, site-independent eligibility for browser actions."""
    if not isinstance(element, Mapping):
        return False
    tool = str(tool or "")
    input_type = normalize_target_text(element.get("type"))
    hidden_file_input = tool == "browser_upload_file" and input_type == "file"
    if element.get("disabled") is True:
        return False
    if element.get("visible") is False and not hidden_file_input:
        return False
    if tool in {"browser_click", "browser_hover", "browser_select"}:
        if element.get("inViewport", element.get("in_viewport")) is False:
            return False
        if element.get(
            "hitTestable", element.get("hit_testable"),
        ) is False:
            return False
    role = normalize_target_text(element.get("role"))
    tag = normalize_target_text(element.get("tag"))
    verified = element.get("activationVerified") is True
    if tool in {"browser_click", "browser_hover"}:
        return bool(
            verified
            or role in CLICK_ROLES
            or tag in {"a", "button", "summary"}
            or input_type in {"button", "submit", "reset", "checkbox", "radio"}
        )
    if tool in {"browser_fill", "browser_type_at"}:
        return bool(
            role in EDIT_ROLES
            or element.get("editable") is True
            or element.get("contentEditable") is True
            or tag in {"input", "textarea"}
        )
    if tool == "browser_select":
        return role in {"combobox", "listbox", "option"} or tag == "select"
    if tool == "browser_upload_file":
        return input_type == "file" or verified
    if tool == "browser_paste_image":
        return bool(role in EDIT_ROLES or element.get("contentEditable") is True)
    return True


def locator_match_score(locator: Mapping[str, Any], element: Mapping[str, Any]) -> int:
    """Score exact semantic identity; never promote ancestor text containment."""
    selector = str(locator.get("selector") or "").strip()
    selector_matches = bool(selector and selector == str(element.get("selector") or "").strip())
    score = 100 if selector_matches else 0
    compared = selector_matches

    # Accessible name and rendered text are alternate representations of the
    # same label. Recorders commonly persist both, while a later snapshot may
    # expose only one of them. Require an exact label intersection instead of
    # requiring both fields or accepting ancestor substring containment.
    wanted_labels = {
        value for value in (
            normalize_target_text(locator.get("name")),
            normalize_target_text(locator.get("text")),
        ) if value
    }
    if wanted_labels:
        compared = True
        actual_name = normalize_target_text(element.get("name"))
        actual_text = normalize_target_text(element.get("text"))
        actual_labels = {value for value in (actual_name, actual_text) if value}
        common_labels = wanted_labels.intersection(actual_labels)
        if not common_labels:
            return 0
        score += 30 if normalize_target_text(locator.get("name")) == actual_name else 18

    wanted_role = normalize_target_text(locator.get("role"))
    if wanted_role:
        compared = True
        actual_role = normalize_target_text(element.get("role"))
        if wanted_role == actual_role:
            score += 12
        elif (
            wanted_role in CLICK_ROLES and actual_role in CLICK_ROLES
        ) or (
            wanted_role in EDIT_ROLES and actual_role in EDIT_ROLES
        ):
            # Native tags and ARIA wrappers often change the exposed role
            # across renders. Keep the exact label as identity and treat role
            # family agreement as compatible, but less specific.
            score += 5
        else:
            return 0

    for key, weight in (
        ("placeholder", 14),
        ("semanticPurpose", 24), ("scopeName", 10), ("scopeRole", 8),
        ("type", 18), ("accept", 8), ("hasPopup", 8),
    ):
        wanted = normalize_target_text(locator.get(key))
        if not wanted:
            continue
        compared = True
        actual = normalize_target_text(element.get(key))
        if not actual or wanted != actual:
            return 0
        score += weight
    return score if compared else 0


def locator_matches(
    locator: Mapping[str, Any],
    element: object,
    *,
    tool: str,
) -> bool:
    return bool(
        isinstance(element, Mapping)
        and element_can_receive(tool, element)
        and locator_match_score(locator, element) > 0
    )


def normalize_target_text(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


__all__ = [
    "CLICK_ROLES", "EDIT_ROLES", "element_can_receive",
    "locator_match_score", "locator_matches", "normalize_target_text",
]
