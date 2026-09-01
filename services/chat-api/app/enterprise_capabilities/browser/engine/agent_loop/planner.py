"""Turn (goal + history + current observation) into a single Decision.

Uses the project's standard LLM client. Output parsing is tolerant —
tries JSON in a fenced block first, falls back to regex extraction.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field

from app.llm.factory import get_request_scoped_llm_client
from app.llm.decision_turn import DecisionOutput, DecisionTurnSpec, invoke_structured_decision, invoke_text_decision
from app.llm.types import Message, Role

from .prompt import system_prompt
from .protocol import Decision, Observation, StepRecord
from .model_input import build_browser_model_input
from .observation_compactor import compact_observation, find_target_matches

logger = logging.getLogger(__name__)


class _DecisionSchema(DecisionOutput):
    """Schema handed to the LLM so it emits structurally-valid JSON."""

    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


_MAX_HISTORY_STEPS = 8
_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_balanced_json_object(text: str) -> str:
    """Return the first balanced top-level JSON object from noisy model text.

    Handles braces inside quoted strings so rationale text or snippets do not
    break the outer object extraction.
    """
    raw = str(text or "")
    start = raw.find("{")
    if start < 0:
        return raw.strip()
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(raw)):
        ch = raw[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw[start:idx + 1]
    return raw[start:].strip()


def _balance_brackets(text: str) -> str:
    """Append missing closers when the model truncates or miscounts nesting.

    Walks the string once, tracking expected closers for every unquoted
    `{` / `[`. An unterminated string is closed with a `"` first so the
    appended braces are not swallowed by it.
    """
    stack: List[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in ("}", "]") and stack and stack[-1] == ch:
            stack.pop()
    suffix = ('"' if in_string else "") + "".join(reversed(stack))
    return text + suffix if suffix else text


def _cleanup_common_json_issues(blob: str) -> str:
    text = str(blob or "").strip()
    # Remove trailing commas before } or ].
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # Replace full-width punctuation around object structure that models
    # sometimes emit in otherwise-valid JSON.
    text = (
        text.replace("，", ",")
        .replace("：", ":")
    )
    return text


def _find_target_matches(
    elements: List[Dict[str, Any]], target: str,
) -> List[Dict[str, Any]]:
    """Structural target lookup. When the ledger tells us 'operate on
    entity X', pre-resolve which observed elements match X by name or
    description substring. LLM no longer needs wait_for / observe loops
    to find the row — it reads `target_matches` and uses the top ref.

    Uses progressive fallback: try the full target first, then shorter
    distinctive substrings. This survives observers that truncate or
    abbreviate row names. Returns up to 5 matches in DOM order so the
    LLM can pick the right one, with the `matched_by` field recording
    which search term hit (full vs. a fallback token)."""
    return find_target_matches(elements, target)


def _compact_observation(
    obs: Observation,
    *,
    target: Optional[str] = None,
    goal: str = "",
    pinned_refs: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    return compact_observation(obs, goal=goal, target=target, pinned_refs=pinned_refs)


def _compact_history(history: List[StepRecord]) -> List[Dict[str, Any]]:
    recent = history[-_MAX_HISTORY_STEPS:]
    return [
        {
            "step": idx + 1,
            "action": {"tool": rec.decision.tool, "args": rec.decision.args},
            "ok": rec.ok,
            **({"error": rec.error} if rec.error else {}),
            **({"digest": rec.result_digest} if rec.result_digest else {}),
        }
        for idx, rec in enumerate(recent)
    ]


def _stable_element_identity(element: Dict[str, Any]) -> tuple[Any, ...] | None:
    """Return an observation-independent identity when one is available."""
    backend_node_id = str(element.get("backendNodeId") or element.get("backend_node_id") or "").strip()
    selector = str(element.get("selector") or "").strip()
    frame_depth = str(element.get("frameDepth") or element.get("frame_depth") or 0)
    role = str(element.get("role") or "").strip().casefold()
    label = str(element.get("name") or element.get("text") or "").strip().casefold()
    href = str(element.get("href") or "").strip()
    if backend_node_id:
        return ("backend", frame_depth, backend_node_id, role, label, href)
    if selector:
        return ("selector", frame_depth, selector, role, label, href)
    return None


def _current_ref_for_historical_action(
    record: StepRecord,
    current: Observation,
) -> str:
    """Migrate a historical ref only when its element identity still matches."""
    if not record.ok or not isinstance(record.decision.args, dict):
        return ""
    old_ref = str(record.decision.args.get("ref") or "").strip()
    if not old_ref:
        return ""
    source = record.decision_observation
    if source is None:
        return ""
    if source.revision and source.revision == current.revision:
        return old_ref
    historical = next(
        (
            item for item in source.elements
            if isinstance(item, dict) and str(item.get("ref") or "").strip() == old_ref
        ),
        None,
    )
    identity = _stable_element_identity(historical) if historical else None
    if identity is None:
        return ""
    matches = [
        str(item.get("ref") or "").strip()
        for item in current.elements
        if isinstance(item, dict) and _stable_element_identity(item) == identity
    ]
    return matches[0] if len(matches) == 1 else ""


def _detect_repetition(history: List[StepRecord]) -> str:
    """Return a warning string when the planner is spinning on the same
    tool + URL. Helps the LLM notice it's stuck and course-correct."""
    if len(history) < 3:
        return ""
    last3 = history[-3:]
    tools = [r.decision.tool for r in last3]
    urls = [r.observation.url for r in last3]
    if len(set(tools)) == 1 and len(set(urls)) == 1 and tools[0] in ("browser_read_text", "browser_observe", "browser_screenshot"):
        return (
            f"⚠️ 检测到循环：你刚在同一个页面 {urls[0]} 连续 3 次 {tools[0]}。"
            f"停止重复读同一页。如果数据已经够，立刻调 browser_done；"
            f"如果信息不足，换个动作：scroll / navigate 到别的页面 / 换个站。"
        )
    return ""


def _render_state_ledger(ledger: Dict[str, Any]) -> str:
    """Explicit state ledger.

    LLMs are bad at inferring state from history. So the system (which
    IS good at tracking state machines) hands the LLM a structured card
    at the top of every turn: what phase, what goal, what signals are
    already verified, what's still required, the target reference to
    lock onto, and the remaining budget. The LLM's only job is to pick
    the next concrete element action consistent with the ledger.

    The card is deliberately at the TOP of the prompt (before history
    and observation) so it dominates attention."""
    lines = ["### CURRENT STATE — this is authoritative, do not contradict"]
    for k in (
        "phase", "phase_goal", "target",
        "completed_signals", "remaining_signals",
        "forbidden_actions",
        "action_constraints",
        "edit_affordance_candidates", "delete_affordance_candidates",
        "mission",
        "budget",
    ):
        if k in ledger:
            val = ledger[k]
            if isinstance(val, (list, dict)):
                val = json.dumps(val, ensure_ascii=False)
            lines.append(f"- {k}: {val}")
    notes = ledger.get("notes")
    if isinstance(notes, list) and notes:
        lines.append("- notes:")
        for n in notes[:6]:
            lines.append(f"    • {n}")
    return "\n".join(lines)


def _build_user_turn(
    goal: str,
    history: List[StepRecord],
    obs: Observation,
    state_ledger: Optional[Dict[str, Any]] = None,
) -> str:
    _target = None
    if state_ledger and isinstance(state_ledger.get("target"), str):
        raw = state_ledger["target"].strip()
        # Skip the placeholder "not locked" hints; only real names pre-resolve.
        if raw and "not_locked" not in raw and "未锁定" not in raw:
            _target = raw
    current_elements = {
        str(item.get("ref") or ""): item
        for item in (obs.elements or [])
        if isinstance(item, dict) and item.get("ref")
    }
    pinned_refs = set()
    if state_ledger:
        ledger_refs = state_ledger.get("pinned_refs")
        if isinstance(ledger_refs, list):
            for item in ledger_refs[:40]:
                ref = str(item or "").strip()
                element = current_elements.get(ref)
                if element and element.get("visible", True) is not False and not element.get("disabled"):
                    pinned_refs.add(ref)
    for record in history[-_MAX_HISTORY_STEPS:]:
        ref = _current_ref_for_historical_action(record, obs)
        element = current_elements.get(ref)
        if not element or element.get("visible", True) is False or element.get("disabled"):
            continue
        if element.get("inViewport") is False or element.get("hitTestable") is False:
            continue
        pinned_refs.add(ref)
    payload = {
        "goal": goal,
        "history": _compact_history(history),
        "observation": _compact_observation(obs, target=_target, goal=goal, pinned_refs=pinned_refs),
    }
    rep_warn = _detect_repetition(history)
    parts: List[str] = []
    if state_ledger:
        parts.append(_render_state_ledger(state_ledger))
        affordance_refs: List[str] = []
        for key in ("edit_affordance_candidates", "delete_affordance_candidates"):
            vals = state_ledger.get(key)
            if isinstance(vals, list):
                for item in vals[:8]:
                    if isinstance(item, dict):
                        ref = str(item.get("ref") or "").strip()
                        if ref:
                            affordance_refs.append(ref)
        if affordance_refs:
            refs = ", ".join(dict.fromkeys(affordance_refs))
            parts.append(
                "优先规则：若当前状态里给出了 affordance candidates，下一步应优先从这些 ref 中选择；"
                f"不要先返回列表、不要先重复 wait_for。候选 refs: {refs}"
            )
    if rep_warn:
        parts.append(rep_warn)
    parts.append(
        "以下是当前状态，请基于此决定下一步（仅返回 JSON: "
        '{"tool": "...", "args": {...}, "rationale": "..."}）\n\n'
        + json.dumps(payload, ensure_ascii=False)
    )
    return "\n\n".join(parts)


def _decision_from_mapping(data: Dict[str, Any]) -> Decision:
    tool = str(data.get("tool") or "").strip()
    if not tool:
        raise ValueError("decision missing 'tool'")
    args = data.get("args") or {}
    if not isinstance(args, dict):
        raise ValueError("decision 'args' must be an object")
    return Decision(
        tool=tool,
        args=args,
        rationale=str(data.get("rationale") or "")[:500],
        rationale_source="model",
        commentary=dict(data.get("commentary") or {}) if isinstance(data.get("commentary"), dict) else None,
    )


# ─── Shape-inference fallback parser ─────────────────────────────
# When the strict parser fails (truncation, prompt-injection noise,
# malformed wrapping around a JSON tool call),
# we recover by scanning the raw text for *any* valid JSON object and
# inferring the tool from its field shape. Zero site assumptions — only
# the fields we know our own tools accept.
_JSON_OBJ_RE = re.compile(r"\{.*?\}", re.S)


def _infer_tool_from_shape(obj: Dict[str, Any]) -> Optional[str]:
    """Infer the intended tool name from a JSON object's field shape.
    Returns None when the shape is ambiguous."""
    keys = {str(k).lower() for k in obj.keys()}
    # Priority order chosen so more specific shapes win over general ones.
    if "summary" in keys or "bugs" in keys or "published_url" in keys:
        return "browser_done"
    if "question" in keys:
        return "browser_ask_user"
    if "reason" in keys and "ref" not in keys and "url" not in keys:
        return "browser_fail"
    if "url" in keys and "ref" not in keys:
        return "browser_navigate"
    if "ref" in keys and "value" in keys:
        return "browser_fill"
    if "ref" in keys and ("key" in keys or "keys" in keys):
        return "browser_press"
    if "editor_ref" in keys and "sources" in keys and "ref" not in keys:
        return "browser_paste_image"
    if "ref" in keys and "sources" in keys:
        return "browser_upload_file"
    if "text" in keys or "timeout" in keys:
        return "browser_wait_for"
    if "direction" in keys:
        return "browser_scroll"
    # A bare ref is intentionally ambiguous: click, hover, read, screenshot,
    # and several form tools all accept one. Guessing click here can turn a
    # damaged non-mutating decision into an unintended mutation.
    if "ref" in keys:
        return None
    return None


def _recover_decision_from_contaminated_raw(raw: str) -> Optional[Decision]:
    """Last-ditch recovery: scan raw text for any valid JSON object whose
    fields match a known tool shape. Handles prompt-injection noise and
    malformed wrappers that the strict parser rejects."""
    if not raw:
        return None
    # Use balanced-brace scanning (nested objects) rather than non-greedy
    # regex, which breaks on nested braces.
    candidates: List[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidates.append(raw[start:i + 1])
                start = -1
    for cand in candidates:
        try:
            cleaned = _cleanup_common_json_issues(cand)
            obj = json.loads(cleaned)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        # Use top-level tool field if present.
        tool = str(obj.get("tool") or "").strip()
        if not tool:
            inferred = _infer_tool_from_shape(obj)
            if not inferred:
                continue
            tool = inferred
            # For shape-inferred tools, args are the object itself minus
            # the rationale field.
            args_obj = {k: v for k, v in obj.items() if k not in ("rationale", "tool")}
            return Decision(
                tool=tool,
                args=args_obj,
                rationale=str(obj.get("rationale") or "")[:500],
                rationale_source="model",
            )
        # Top-level tool explicit → normal path.
        try:
            return _decision_from_mapping(obj)
        except Exception:
            continue
    return None


def _parse_decision(raw: str) -> Decision:
    """Extract the first JSON object from the model reply."""
    text = (raw or "").strip()
    m = _FENCE_RE.search(text)
    blob = m.group(1) if m else text
    blob = _extract_balanced_json_object(blob)
    cleaned = _cleanup_common_json_issues(blob)
    data = None
    parse_errors: List[str] = []
    # Try the candidates in order of decreasing faithfulness: raw blob → light
    # cleanup → cleanup + auto-closed brackets (rescues truncated outputs).
    for candidate in (blob, cleaned, _balance_brackets(cleaned)):
        try:
            data = json.loads(candidate)
            break
        except Exception as exc:
            parse_errors.append(str(exc))
    if data is None:
        raise ValueError("; ".join(parse_errors[:2]) or "decision json parse failed")
    return _decision_from_mapping(data)


class Planner:
    def __init__(
        self,
        lang: str = "zh",
        enterprise_sites: Optional[Dict[str, str]] = None,
    ) -> None:
        self._lang = lang
        self._enterprise_sites = enterprise_sites
        self._llm = get_request_scoped_llm_client(streaming=False, intent="chat")

    async def next_step(
        self,
        goal: str,
        history: List[StepRecord],
        observation: Observation,
        state_ledger: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        user_turn = _build_user_turn(goal, history, observation, state_ledger=state_ledger)
        model_input = build_browser_model_input(user_turn, observation.screenshot)
        messages = [
            Message(role=Role.SYSTEM, content=system_prompt(self._lang, self._enterprise_sites)),
            Message(role=Role.USER, content=model_input.content),
        ]
        # Preferred path: let the LLM provider enforce the JSON schema so the
        # model can't truncate / miscount braces.
        try:
            parsed = await invoke_structured_decision(
                self._llm,
                _DecisionSchema,
                messages,
                spec=DecisionTurnSpec(locale=self._lang, turn_id=f"browser.decide.{len(history) + 1}"),
            )
            return _decision_from_mapping(parsed.model_dump())
        except Exception as struct_exc:
            logger.info(
                "[browser_task.planner] structured_output_failed exc=%s; falling back to text parse",
                struct_exc,
            )

        # Fallback: plain completion + tolerant manual parse (handles providers
        # or deployments that don't support structured output).
        try:
            resp = await invoke_text_decision(
                self._llm,
                messages,
                spec=DecisionTurnSpec(locale=self._lang, turn_id=f"browser.decide.{len(history) + 1}.fallback"),
                commentary_parser=lambda value: vars(_parse_decision(str(value or ""))),
            )
        except Exception as multimodal_exc:
            if not model_input.includes_screenshot:
                raise
            logger.warning(
                "[browser_task.planner] multimodal_input_rejected exc=%s; "
                "retrying with compact DOM text",
                multimodal_exc,
            )
            messages = [
                Message(role=Role.SYSTEM, content=system_prompt(self._lang, self._enterprise_sites)),
                Message(role=Role.USER, content=model_input.text_content),
            ]
            resp = await invoke_text_decision(
                self._llm,
                messages,
                spec=DecisionTurnSpec(locale=self._lang, turn_id=f"browser.decide.{len(history) + 1}.text"),
                commentary_parser=lambda value: vars(_parse_decision(str(value or ""))),
            )
        raw = (resp.message.content or "").strip()
        try:
            return _parse_decision(raw)
        except Exception as exc:
            # Shape-inference recovery for contaminated / malformed
            # output. Observed failure: LLM emits the correct JSON but
            # with prompt-injection noise (e.g. spam tokens) mixed in,
            # tripping the strict `tool` field check. We scan for any
            # JSON object whose shape matches a known tool and rebuild
            # a Decision from it. Zero site/keyword assumptions.
            recovered = _recover_decision_from_contaminated_raw(raw)
            if recovered is not None:
                logger.warning(
                    "[browser_task.planner] parse_recovered "
                    "original_error=%s recovered_tool=%s raw_len=%d",
                    exc, recovered.tool, len(raw),
                )
                return recovered
            # Last-chance retry on structured output. Observed failure:
            # LLM returns an empty string mid-task ("Expecting value:
            # line 1 column 1 (char 0)") — usually a transient provider
            # hiccup / rate limit / network blip. One extra structured
            # attempt almost always succeeds, and is far cheaper than
            # losing the whole multi-case run to browser_fail.
            try:
                parsed2 = await invoke_structured_decision(
                    self._llm,
                    _DecisionSchema,
                    messages,
                    spec=DecisionTurnSpec(locale=self._lang, turn_id=f"browser.decide.{len(history) + 1}.retry"),
                )
                logger.warning(
                    "[browser_task.planner] parse_retry_recovered "
                    "original_error=%s raw_len=%d",
                    exc, len(raw),
                )
                return _decision_from_mapping(parsed2.model_dump())
            except Exception as retry_exc:
                logger.info(
                    "[browser_task.planner] parse_retry_failed exc=%s",
                    retry_exc,
                )
            logger.warning(
                "[browser_task.planner] parse_error=%s raw_len=%d raw=%r",
                exc,
                len(raw),
                raw,
            )
            # Soft recovery: issue a no-op `browser_observe` instead of
            # a terminal `browser_fail`. This gives the planner another
            # turn with a fresh observation. A single transient empty
            # response should not terminate the whole browser node. The
            # executor's stagnation detector will still catch genuine
            # LLM lockups (repeated no-op observes with no progress).
            return Decision(
                tool="browser_observe",
                args={},
                rationale=f"planner-parse-recovery: {exc}",
            )
