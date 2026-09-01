from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation, StepRecord

from .contracts import CachedFieldBinding, CachedWorkflowStep
from .semantics import candidate_semantic_score, locator_semantic_hint
from .action_policy import DYNAMIC_MUTATION_TOOLS, action_disposition


_LOCATOR_FIELDS = (
    "selector", "role", "name", "text", "description", "placeholder",
    "semanticPurpose", "scopeName", "scopeRole", "hasPopup", "frameDepth",
    "type", "accept",
)


def distill_successful_prefix(history: Iterable[StepRecord]) -> List[CachedWorkflowStep]:
    """Keep only the verified navigation prefix before dynamic business data.

    Form values and files are intentionally not copied.  Once replay reaches
    the form, the existing FormInputDriver binds the current run's title,
    body and media from BrowserInputContext.
    """
    steps: List[CachedWorkflowStep] = []
    for record in history:
        tool = str(record.decision.tool or "")
        if tool in DYNAMIC_MUTATION_TOOLS:
            break
        if not record.ok or action_disposition(tool) == "ignore":
            continue
        if action_disposition(tool) != "replay":
            continue
        before = record.decision_observation
        after = record.observation
        step = _project_step(record, before=before, after=after)
        if step is None:
            continue
        if steps and _same_step(steps[-1], step):
            continue
        steps.append(step)
    return steps


def dynamic_input_roles(context: BrowserInputContext) -> List[str]:
    return sorted({
        str(item.semantic_name or item.value_kind or "input").strip().lower()
        for item in context.candidates
        if str(item.semantic_name or item.value_kind or "").strip()
    })


def distill_field_bindings(
    history: Iterable[StepRecord],
    context: BrowserInputContext,
) -> List[CachedFieldBinding]:
    """Learn field-to-input mappings without retaining any business values."""
    learned: List[CachedFieldBinding] = []
    seen: set[tuple[str, str, str]] = set()
    for record in history:
        if not record.ok or record.decision.tool not in {
            "browser_fill", "browser_type_at", "browser_select", "browser_upload_file",
            "browser_paste_image",
        }:
            continue
        args = dict(record.decision.args or {})
        ref = str(
            args.get("editor_ref")
            if record.decision.tool == "browser_paste_image"
            else args.get("ref") or ""
        )
        locator = _locator_for_ref(record.decision_observation, ref)
        if not locator:
            continue
        candidate = _candidate_for_mutation(args, context, locator=locator)
        if candidate is None:
            continue
        action = {
            "browser_select": "select",
            "browser_upload_file": "upload",
            "browser_paste_image": "upload",
        }.get(record.decision.tool, "fill")
        control_kind = ""
        if record.decision_observation is not None:
            target = next((
                item for item in record.decision_observation.elements
                if isinstance(item, dict) and str(item.get("ref") or "") == ref
            ), None)
            if isinstance(target, dict):
                control_kind = str(target.get("type") or target.get("role") or "")
        key = (str(locator), candidate.semantic_name, action)
        if key in seen:
            continue
        seen.add(key)
        learned.append(CachedFieldBinding(
            locator=locator,
            semantic_name=str(candidate.semantic_name or candidate.value_kind or "input"),
            source_path=str(candidate.source_path or ""),
            action=action,
            control_kind=control_kind,
        ))
    return learned


def _candidate_for_mutation(
    args: Dict[str, Any],
    context: BrowserInputContext,
    *,
    locator: Dict[str, Any],
):
    if "sources" in args:
        actual = _normalized_files(args.get("sources"))
        matches = [item for item in context.candidates if _normalized_files(item.value) == actual]
    else:
        actual = str(args.get("value") or args.get("text") or "")
        matches = [
            item for item in context.candidates
            if item.value_kind != "file" and actual in {
                str(item.value or ""), str(item.plain_text or ""), str(item.rich_html or ""),
            }
        ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) <= 1:
        return None
    hint = locator_semantic_hint(locator)
    ranked = []
    for item in matches:
        ranked.append((candidate_semantic_score(item, hint), item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    if ranked[0][0] <= 0 or ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0][1]


def _normalized_files(value: Any) -> tuple[str, ...]:
    values = value if isinstance(value, list) else [value]
    return tuple(str(item or "").strip() for item in values if str(item or "").strip())


def _project_step(
    record: StepRecord,
    *,
    before: Observation | None,
    after: Observation,
) -> CachedWorkflowStep | None:
    decision = record.decision
    tool = str(decision.tool or "")
    args = dict(decision.args or {})
    source_url = str((before or after).url or "")
    if tool in {"browser_navigate", "browser_tab_new"}:
        url = str(args.get("url") or "").strip()
        if not url:
            return None
        return CachedWorkflowStep(tool=tool, args={"url": url}, source_url=source_url)
    if tool in {"browser_back", "browser_forward"}:
        return CachedWorkflowStep(tool=tool, source_url=source_url)
    if tool == "browser_scroll":
        return CachedWorkflowStep(
            tool=tool,
            args={"direction": str(args.get("direction") or "down")},
            locator=_locator_for_ref(before, str(args.get("ref") or "")),
            source_url=source_url,
        )
    if tool == "browser_press":
        return CachedWorkflowStep(
            tool=tool,
            args={"key": str(args.get("key") or "")},
            locator=_locator_for_ref(before, str(args.get("ref") or "")),
            source_url=source_url,
        )
    if tool == "browser_wait_for":
        text = str(args.get("text") or "").strip()
        timeout = args.get("timeout")
        static_args: Dict[str, Any] = {}
        if text:
            static_args["text"] = text
        if timeout is not None:
            static_args["timeout"] = timeout
        locator = _locator_for_ref(before, str(args.get("ref") or ""))
        if str(args.get("ref") or "").strip() and not text and not locator:
            return None
        return CachedWorkflowStep(
            tool=tool,
            args=static_args,
            locator=locator,
            source_url=source_url,
        )
    locator = _locator_for_ref(before, str(args.get("ref") or ""))
    if not locator:
        return None
    if not _made_progress(before, after):
        return None
    return CachedWorkflowStep(tool=tool, locator=locator, source_url=source_url)


def _locator_for_ref(observation: Observation | None, ref: str) -> Dict[str, Any]:
    if observation is None or not ref:
        return {}
    target = next((
        item for item in observation.elements
        if isinstance(item, dict) and str(item.get("ref") or "") == ref
    ), None)
    if target is None:
        return {}
    locator: Dict[str, Any] = {}
    for key in _LOCATOR_FIELDS:
        value = target.get(key)
        if value not in (None, "", False):
            locator[key] = value
    return locator


def _made_progress(before: Observation | None, after: Observation) -> bool:
    if before is None:
        return True
    if before.url != after.url:
        return True
    if before.state_fingerprint and after.state_fingerprint:
        return before.state_fingerprint != after.state_fingerprint
    return before.page_text != after.page_text or before.elements != after.elements


def _same_step(left: CachedWorkflowStep, right: CachedWorkflowStep) -> bool:
    return left.tool == right.tool and left.args == right.args and left.locator == right.locator


__all__ = ["distill_field_bindings", "distill_successful_prefix", "dynamic_input_roles"]
