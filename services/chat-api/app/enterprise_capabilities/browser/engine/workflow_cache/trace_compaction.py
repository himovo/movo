from __future__ import annotations

from typing import Any, Iterable


_EDIT_TOOLS = {"browser_fill", "browser_type_at", "browser_select"}
_TRANSIENT_URLS = {"", "about:blank", "about:srcdoc"}


def compact_causal_actions(events: Iterable[Any]) -> list[Any]:
    """Fold browser implementation events into portable business actions."""
    output: list[Any] = []
    for current in events:
        previous = output[-1] if output else None
        if previous is not None and _merge_navigation(previous, current):
            output[-1] = previous.model_copy(update={
                "after_url": str(getattr(current, "after_url", "") or ""),
                "after_fingerprint": str(getattr(current, "after_fingerprint", "") or ""),
                "after_state_key": str(getattr(current, "after_state_key", "") or ""),
                "after_tab_id": str(getattr(current, "after_tab_id", "") or ""),
            })
            continue
        if previous is not None and _preparatory_click(previous, current):
            if str(getattr(current, "tool", "")) in _EDIT_TOOLS:
                output[-1] = current.model_copy(update={
                    "locator": _merge_edit_locator(previous, current),
                })
            else:
                output[-1] = current
            continue
        output.append(current)
    return output


def _merge_navigation(previous: Any, current: Any) -> bool:
    if str(getattr(current, "tool", "")) != "browser_navigate":
        return False
    if str(getattr(previous, "tool", "")) not in {"browser_click", "browser_press"}:
        return False
    before = str(getattr(current, "before_url", "") or "")
    previous_after = str(getattr(previous, "after_url", "") or "")
    after = str(getattr(current, "after_url", "") or "")
    return bool(
        after.casefold() not in _TRANSIENT_URLS
        and before == previous_after
    )


def _preparatory_click(previous: Any, current: Any) -> bool:
    if str(getattr(previous, "tool", "")) != "browser_click":
        return False
    current_tool = str(getattr(current, "tool", ""))
    if current_tool not in {*_EDIT_TOOLS, "browser_upload_file", "browser_paste_image"}:
        return False
    if str(getattr(previous, "after_url", "") or "") != str(getattr(current, "before_url", "") or ""):
        return False
    previous_locator = dict(getattr(previous, "locator", {}) or {})
    current_locator = dict(getattr(current, "locator", {}) or {})
    if current_tool in _EDIT_TOOLS:
        return str(previous_locator.get("role") or "").casefold() in {
            "textbox", "searchbox", "combobox",
        }
    previous_selector = str(previous_locator.get("selector") or "")
    current_selector = str(current_locator.get("selector") or "")
    return bool(
        (previous_selector and previous_selector == current_selector)
        or str(previous_locator.get("type") or "").casefold() == "file"
    )


def _merge_edit_locator(previous: Any, current: Any) -> dict[str, Any]:
    prepared = dict(getattr(previous, "locator", {}) or {})
    locator = dict(getattr(current, "locator", {}) or {})
    value = " ".join(str((getattr(current, "args", {}) or {}).get("value") or "").split()).casefold()
    for key in ("name", "text", "placeholder", "semanticPurpose", "scopeName", "scopeRole"):
        stable = str(prepared.get(key) or "").strip()
        if stable and " ".join(stable.split()).casefold() != value:
            locator[key] = stable
    return locator


__all__ = ["compact_causal_actions"]
