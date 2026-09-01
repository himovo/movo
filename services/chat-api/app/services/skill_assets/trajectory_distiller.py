"""Turn a recorded browser trajectory into composite_task steps.

The agent's recorder streams a sequence of semantic events (click /
fill / navigate) with each target's signal bag. This module converts
that sequence into the YAML-backed CompositeStep shape that
``composite_task.parse_composite_skill`` already understands, so the
recording path produces the exact same artifact as the manual editor.

No LLM is required for the happy path — the recorder only captures
real user actions, so there's no "test noise" to strip. The optional
``llm_refine`` hook is reserved for later (variable extraction,
step-merging, title polishing) and is a no-op today."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional


_LOCATOR_KEYS = (
    "role", "name", "name_contains", "aria_label",
    "icon_class", "text", "ancestor_role", "ancestor_contains_text", "nth",
)


def _pick_locator(target: Dict[str, Any]) -> Dict[str, Any]:
    """Strip the signal bag emitted by the agent recorder down to the
    locator subset. Empty strings are dropped so the matcher treats the
    field as "no constraint" rather than "must be empty".
    """
    out: Dict[str, Any] = {}
    for key in _LOCATOR_KEYS:
        if key not in target:
            continue
        val = target.get(key)
        if key == "nth":
            if isinstance(val, int):
                out[key] = val
            continue
        s = str(val or "").strip()
        if s:
            out[key] = s
    return out


def _instruction_for(event: Dict[str, Any]) -> str:
    """Human-readable one-liner for an event. Used as the step's
    ``instruction`` text so a human editor / the planner LLM can still
    reason about what the step is supposed to do, even without the
    locator."""
    kind = str(event.get("type") or "").lower()
    target = event.get("target") or {}
    name = str(target.get("name") or target.get("text") or target.get("aria_label") or "").strip()
    if kind == "click":
        return f"点击 {name}" if name else "点击目标控件"
    if kind == "fill":
        value = str(event.get("value") or "")
        preview = value if len(value) <= 40 else value[:40] + "…"
        return f"在 {name or '输入框'} 输入 {preview}" if value else f"聚焦 {name or '输入框'}"
    if kind == "navigate":
        return f"打开 {event.get('url') or '页面'}"
    if kind == "select":
        return f"选择 {name}" if name else "选择下拉项"
    return str(event.get("instruction") or kind or "操作")


def _coerce_variables(vars_in: Any) -> Dict[str, str]:
    if not isinstance(vars_in, dict):
        return {}
    out: Dict[str, str] = {}
    for k, v in vars_in.items():
        key = str(k or "").strip()
        val = str(v or "")
        if key:
            out[key] = val
    return out


def distill_trajectory(
    events: Iterable[Dict[str, Any]],
    *,
    site_profile_id: str = "",
    variables: Mapping[str, str] | None = None,
) -> List[Dict[str, Any]]:
    """Convert recorded events into CompositeStep dicts.

    Input event shape (from agent/src/browser/recorder.ts):
        {
          "type": "click" | "fill" | "navigate" | "select",
          "url": "...",
          "value": "...",                 # fill only
          "target": {                     # click / fill / select
            "role": ..., "name": ...,
            "aria_label": ..., "icon_class": ...,
            "ancestor_role": ..., "ancestor_contains_text": ...,
          },
          "instruction": "optional override"
        }

    Output: list of dicts shaped like ``compositeSkill.CompositeStep``
    (``instruction`` + optional ``locator``, ``kind``, ``title``,
    ``site_profile_id``). The caller persists this list via the YAML
    encoder (backend-side duplicate of the frontend encoder lives in
    ``skills.py::_encode_composite_yaml``).
    """
    out: List[Dict[str, Any]] = []
    variables = dict(variables or {})
    for ev in events:
        if not isinstance(ev, dict):
            continue
        kind = str(ev.get("type") or "").lower()
        if kind not in ("click", "fill", "navigate", "select"):
            continue

        step: Dict[str, Any] = {
            "kind": "browser",
            "instruction": _instruction_for(ev),
        }
        if site_profile_id:
            step["site_profile_id"] = site_profile_id

        target = ev.get("target") if isinstance(ev.get("target"), dict) else {}
        loc = _pick_locator(target)
        if loc:
            # Per-op bag: click maps to ``primary``; fill/select also ride under primary
            # since they don't collide with CRUD op dispatch.
            step["locators"] = {"primary": loc}
        if kind == "fill" and ev.get("value") is not None:
            step["fill_value"] = str(ev.get("value") or "")
        if kind == "navigate" and ev.get("url"):
            step["navigate_url"] = str(ev.get("url"))

        out.append(step)
    if variables:
        for step in out:
            step["locator_vars"] = dict(variables)
    return out


def refine_steps(
    steps: List[Dict[str, Any]],
    *,
    edits: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Apply front-end edits (delete step, rename, variable-ize a value)
    to the raw distilled list.

    ``edits`` entries:
        {"op": "delete", "index": N}
        {"op": "set_instruction", "index": N, "value": "..."}
        {"op": "set_variable", "index": N, "field": "fill_value", "var": "name"}
    """
    if not edits:
        return list(steps)
    out = list(steps)
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        op = str(edit.get("op") or "")
        idx = int(edit.get("index") or -1)
        if idx < 0 or idx >= len(out):
            continue
        if op == "delete":
            out[idx] = None  # tombstone; compacted below
        elif op == "set_instruction":
            out[idx]["instruction"] = str(edit.get("value") or "")
        elif op == "set_variable":
            field = str(edit.get("field") or "")
            var = str(edit.get("var") or "").strip()
            if field and var:
                # Replace the concrete value with a ${var} placeholder.
                out[idx][field] = f"${{{var}}}"
                vars_map = dict(out[idx].get("locator_vars") or {})
                vars_map.setdefault(var, "")
                out[idx]["locator_vars"] = vars_map
    return [s for s in out if s is not None]
