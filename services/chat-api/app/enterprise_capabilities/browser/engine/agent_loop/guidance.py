from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .action_protocol import ACTION_PROTOCOL


_BASE = """You control a browser through typed native-CDP actions.
Choose the shortest grounded next segment. Use only refs present in the observation.
Return 1 action when page state must be checked before continuing; return 2-6 actions only for a deterministic segment.
Never batch publish, send, submit, save, create, delete, payment, upload, authentication, or an uncertain button.
Do not invent URLs. Stop after a navigation/state transition except for browser_wait_for.
If a visible editor placeholder is not editable, click that observed control once to activate it, then stop for a fresh observation. Fill only a ref marked editable.
Use kind=done only when the requested evidence or verified effect is already present.
For kind=done, copy the observed deliverables into data using the capability contract in the goal; summary alone is not result data.
TARGET HISTORY: describe the terminal business action in target_history.operation using a short stable semantic id such as comment, reply, approve, update_ticket, or collect; leave it empty for read-only work. Set policy=exclude_completed only when the user asks to choose an unprocessed/different/new target. Set policy=allow_completed when the user explicitly requests a known target or asks to repeat/revisit it. Otherwise use unspecified. Preserve the same interpretation throughout the task. This is semantic classification, not keyword matching.
""" + ACTION_PROTOCOL


def build_guidance(elements: Iterable[Dict[str, Any]], *, lang: str) -> str:
    roles = {str(item.get("role") or "").lower() for item in elements if isinstance(item, dict)}
    purposes = {str(item.get("semanticPurpose") or "") for item in elements if isinstance(item, dict)}
    sections: List[str] = [_BASE]
    if "searchbox" in roles or "search" in purposes:
        sections.append(
            "SEARCH: a confirmed search field may be one segment: browser_fill(ref,value), "
            "browser_press(ref,key=Enter), optionally browser_wait_for."
        )
    if roles & {"combobox", "listbox", "option"}:
        sections.append("SELECT: use browser_select only with an observed control and exact visible option value.")
    if roles & {"link", "tab"}:
        sections.append("NAVIGATION: click an observed link/tab; do not guess a route from its label.")
    if any(purpose in {"send", "submit", "publish", "save", "create", "delete"} for purpose in purposes):
        sections.append("COMMIT: return the final commit as exactly one browser_click action so the outer safety gate can inspect it.")
    if str(lang).startswith("zh"):
        sections.append("summary/question/reason 使用中文，工具名和参数名保持英文。")
    return "\n".join(sections)
