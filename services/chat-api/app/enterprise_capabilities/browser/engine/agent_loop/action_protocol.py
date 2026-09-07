"""Compact output protocol shared by browser planner turns."""

from __future__ import annotations

from pydantic import ValidationError


ACTION_PROTOCOL = """OUTPUT PROTOCOL (exact JSON):
- Act: {"kind":"actions","actions":[{"tool":"browser_observe","args":{}}],"summary":"...","target_history":{"policy":"unspecified","operation":"","reason":""}}
- Finish: {"kind":"done","actions":[],"summary":"...","data":{"result":{...}},"target_history":{"policy":"unspecified","operation":"","reason":""}}
- Ask/fail: {"kind":"ask_user","actions":[],"question":"...","reason":"...","target_history":{"policy":"unspecified","operation":"","reason":""}} or {"kind":"fail","actions":[],"reason":"...","target_history":{"policy":"unspecified","operation":"","reason":""}}
Every item in actions MUST contain tool and args. Never put kind inside an action.
Allowed tools: browser_fill, browser_press, browser_click, browser_select, browser_scroll, browser_wait_for, browser_observe, browser_read_text, browser_screenshot, browser_navigate, browser_tab_new, browser_back, browser_forward.
browser_observe, browser_read_text, and browser_screenshot are turn boundaries: return them as the only action. Never append them after scroll, click, press, navigate, select, fill, or wait; the next planner turn receives a fresh observation automatically.
DOM actions must use an observed ref. If the target ref is absent, use browser_observe once. Never use browser_type, browser_keypress, address-bar shortcuts, or invented tools."""


class PlannerContractError(RuntimeError):
    """The provider returned invalid planner JSON twice."""


def contract_repair_message(error: ValidationError) -> str:
    issues = []
    for item in error.errors(include_url=False)[:4]:
        location = ".".join(str(part) for part in item.get("loc", ())) or "output"
        issues.append(f"{location}: {item.get('msg', 'invalid')}")
    details = "; ".join(issues) or "output did not match the protocol"
    return (
        "Your previous JSON was rejected by the browser action contract: "
        f"{details}. Correct the response once.\n{ACTION_PROTOCOL}"
    )


__all__ = ["ACTION_PROTOCOL", "PlannerContractError", "contract_repair_message"]
