from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List
from urllib.parse import parse_qsl, quote, quote_plus, urlsplit

from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation, StepRecord

from .contracts import CachedParameterBinding, CachedRequestTemplate, CachedWorkflowStep
from .page_state import url_shape
from .parameters import ParameterCatalog, build_parameter_catalog
from .preconditions import recorded_precondition_category
from .semantics import locator_semantic_hint
from .action_policy import action_disposition, stable_locator_required
from .stability import add_readiness_barriers
from .terminal_semantics import locator_has_terminal_intent
from .locator_portability import portable_locator
from .url_portability import portable_navigation_url


_LOCATOR_FIELDS = (
    "selector", "role", "name", "text", "description", "placeholder",
    "semanticPurpose", "scopeName", "scopeRole", "contentContextId",
    "hasPopup", "frameDepth",
    "type", "accept",
)
_DYNAMIC_LOCATOR_ROLES = {
    "link", "listitem", "row", "option", "treeitem", "article",
    "radio", "checkbox", "menuitemradio", "menuitemcheckbox",
}


@dataclass(frozen=True)
class CompiledWorkflow:
    steps: List[CachedWorkflowStep]
    request_template: CachedRequestTemplate | None
    complete: bool = True
    skipped_actions: int = 0


def compile_parameterized_workflow(
    history: Iterable[StepRecord],
    context: BrowserInputContext,
) -> CompiledWorkflow:
    records = [record for record in history if record.ok]
    request_values: List[str] = []
    for record in records:
        request_values.extend(_request_parameter_values(record, context))
    catalog = build_parameter_catalog(context=context, request_values=request_values)
    steps: List[CachedWorkflowStep] = []
    skipped_actions = 0
    for record in records:
        tool = str(record.decision.tool or "")
        disposition = action_disposition(tool)
        if disposition == "ignore":
            continue
        if disposition == "unsupported":
            skipped_actions += 1
            continue
        step = _compile_step(record, context=context, catalog=catalog)
        if step is None:
            skipped_actions += 1
            continue
        if steps and _same_step(steps[-1], step):
            continue
        steps.append(step)
    return CompiledWorkflow(
        steps=add_readiness_barriers(steps),
        request_template=catalog.request_template,
        complete=skipped_actions == 0,
        skipped_actions=skipped_actions,
    )


def _compile_step(
    record: StepRecord,
    *,
    context: BrowserInputContext,
    catalog: ParameterCatalog,
) -> CachedWorkflowStep | None:
    decision = record.decision
    tool = str(decision.tool or "")
    args = dict(decision.args or {})
    before = record.decision_observation
    after = record.observation
    locator = _locator_for_decision(before, tool, args)
    semantic_hint = locator_semantic_hint(locator)
    if stable_locator_required(tool, args) and not locator:
        return None
    if tool == "browser_click_at":
        if not locator:
            return None
        tool = "browser_click"
    elif tool == "browser_type_at":
        if not locator:
            return None
        tool = "browser_fill"

    if tool in {"browser_click", "browser_hover"} and not locator:
        return None
    if tool in {"browser_fill", "browser_select", "browser_upload_file"} and not locator:
        return None
    if tool == "browser_paste_image" and not locator:
        return None
    made_progress = _made_progress(before, after)
    if tool in {"browser_click", "browser_hover"} and not made_progress:
        human_terminal_click = bool(
            tool == "browser_click"
            and "[human_recording]" in str(decision.rationale or "")
            and locator_has_terminal_intent(locator)
        )
        if not human_terminal_click:
            return None

    precondition_category = recorded_precondition_category(record)
    if precondition_category:
        # Credential values and one-time challenges must never become cached
        # parameters. Preserve only the route boundary required to resume on
        # the authenticated business page.
        return CachedWorkflowStep(
            tool=tool,
            locator={},
            args={},
            source_url="",
            source_url_shape=url_shape((before or after).url),
            target_url_shape=("" if _transient_document(after.url) else url_shape(after.url)),
            expect_state_change=made_progress,
            execution_kind="runtime_precondition",
            precondition_category=precondition_category,
        )

    static_args: Dict[str, Any] = {}
    arg_bindings: Dict[str, CachedParameterBinding] = {}
    dynamic_keys = _dynamic_keys(tool, args, context=context)
    for key, value in args.items():
        if key in {"ref", "editor_ref", "x", "y", "source_width", "source_height"}:
            continue
        if key in dynamic_keys:
            binding = (
                _url_argument_binding(str(value or ""), catalog, context)
                if key == "url"
                else catalog.binding_for(
                    value,
                    context,
                    projection_hint=key,
                    semantic_hint=semantic_hint,
                )
            )
            if binding is None:
                return None
            arg_bindings[key] = binding
        elif key in _safe_static_keys(tool):
            static_args[key] = value

    locator_bindings: Dict[str, CachedParameterBinding] = {}
    for key in ("name", "text", "description", "placeholder", "scopeName"):
        value = locator.get(key)
        if not isinstance(value, str):
            continue
        binding = catalog.binding_for(value, context)
        if binding is not None:
            locator_bindings[key] = binding
            locator.pop(key, None)
    for key, value in list(locator.items()):
        text = str(value or "")
        if key not in {
            "role", "semanticPurpose", "scopeRole", "contentContextId",
            "hasPopup", "frameDepth",
        } and any(
            sensitive and sensitive in text for sensitive in catalog.sensitive_values
        ):
            locator.pop(key, None)
    locator = portable_locator(locator, sensitive_values=catalog.sensitive_values)
    if tool in {"browser_navigate", "browser_tab_new"} and "url" in static_args:
        static_args["url"] = portable_navigation_url(str(static_args.get("url") or ""))

    return CachedWorkflowStep(
        tool=tool,
        locator=locator,
        locator_bindings=locator_bindings,
        args=static_args,
        arg_bindings=arg_bindings,
        source_url="",
        source_url_shape=url_shape((before or after).url),
        # Popup tabs commonly expose about:blank only for a few milliseconds.
        # It is evidence of a branch change, never a stable replay postcondition.
        target_url_shape=("" if _transient_document(after.url) else url_shape(after.url)),
        expect_state_change=made_progress,
    )


def _request_parameter_values(
    record: StepRecord,
    context: BrowserInputContext,
) -> List[str]:
    tool = str(record.decision.tool or "")
    args = dict(record.decision.args or {})
    values: List[str] = []
    for key in _dynamic_keys(tool, args, context=context):
        value = args.get(key)
        if isinstance(value, str) and value:
            if key == "url":
                if value in context.original_request:
                    values.append(value)
                else:
                    values.extend(_request_values_from_url(value, context.original_request))
            elif not _matches_input_candidate(value, context):
                values.append(value)
    target = _element_for_decision(record.decision_observation, tool, args)
    if isinstance(target, dict) and str(target.get("role") or "").casefold() in _DYNAMIC_LOCATOR_ROLES:
        for key in ("name", "text", "description"):
            value = str(target.get(key) or "").strip()
            if value and value in context.original_request:
                values.append(value)
    return values


def _matches_input_candidate(value: Any, context: BrowserInputContext) -> bool:
    if isinstance(value, list):
        normalized = tuple(str(item or "").strip() for item in value if str(item or "").strip())
        return any(
            item.value_kind == "file"
            and tuple(
                str(part or "").strip()
                for part in (item.value if isinstance(item.value, list) else [item.value])
                if str(part or "").strip()
            ) == normalized
            for item in context.candidates
        )
    actual = str(value or "")
    return any(
        item.value_kind != "file" and actual in {
            str(item.value or ""), str(item.plain_text or ""), str(item.rich_html or ""),
        }
        for item in context.candidates
    )


def _dynamic_keys(
    tool: str,
    args: Dict[str, Any],
    *,
    context: BrowserInputContext,
) -> set[str]:
    if tool in {"browser_fill", "browser_type_at", "browser_select"}:
        keys = {"value"}
        if "rich_html" in args:
            keys.add("rich_html")
        return keys
    if tool in {"browser_upload_file", "browser_paste_image"}:
        return {"sources"}
    if tool == "browser_wait_for":
        text = str(args.get("text") or "")
        return {"text"} if text and (
            text in context.original_request
            or catalog_candidate_exists(text, context)
        ) else set()
    if tool in {"browser_navigate", "browser_tab_new"}:
        url = str(args.get("url") or "")
        return {"url"} if url and (
            url in context.original_request
            or bool(_request_values_from_url(url, context.original_request))
        ) else set()
    return set()


def _safe_static_keys(tool: str) -> set[str]:
    if tool in {"browser_navigate", "browser_tab_new"}:
        return {"url"}
    if tool == "browser_press":
        return {"key"}
    if tool == "browser_scroll":
        return {"direction"}
    if tool in {"browser_upload_file", "browser_paste_image"}:
        return {"anchor"}
    if tool == "browser_wait_for":
        return {"text", "timeout"}
    return set()


def catalog_candidate_exists(value: str, context: BrowserInputContext) -> bool:
    return any(
        item.value_kind != "file" and value in {
            str(item.value or ""), str(item.plain_text or ""), str(item.rich_html or ""),
        }
        for item in context.candidates
    )


def _request_values_from_url(url: str, request: str) -> List[str]:
    try:
        values = [str(value) for _, value in parse_qsl(urlsplit(url).query, keep_blank_values=False)]
    except ValueError:
        return []
    return [value for value in values if value and value in request]


def _url_argument_binding(
    url: str,
    catalog: ParameterCatalog,
    context: BrowserInputContext,
) -> CachedParameterBinding | None:
    direct = catalog.binding_for(url, context)
    if direct is not None:
        return direct
    for value in _request_values_from_url(url, context.original_request):
        base = catalog.binding_for(value, context)
        if base is None:
            continue
        encoded_candidates = [quote_plus(value), quote(value), value]
        encoded = next((item for item in encoded_candidates if item and item in url), "")
        if not encoded:
            continue
        prefix, _, suffix = url.partition(encoded)
        return base.model_copy(update={
            "prefix": prefix,
            "suffix": suffix,
            "encoding": "url_query",
        })
    return None


def _locator_for_decision(
    observation: Observation | None,
    tool: str,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    target = _element_for_decision(observation, tool, args)
    if target is None:
        return {}
    return {
        key: target[key]
        for key in _LOCATOR_FIELDS
        if target.get(key) not in (None, "", False)
    }


def _element_for_decision(
    observation: Observation | None,
    tool: str,
    args: Dict[str, Any],
) -> Dict[str, Any] | None:
    if observation is None:
        return None
    ref = str(args.get("editor_ref") if tool == "browser_paste_image" else args.get("ref") or "")
    if ref:
        return next((
            item for item in observation.elements
            if isinstance(item, dict) and str(item.get("ref") or "") == ref
        ), None)
    if tool not in {"browser_click_at", "browser_type_at"}:
        return None
    try:
        x, y = float(args.get("x")), float(args.get("y"))
    except (TypeError, ValueError):
        return None
    matches = []
    for item in observation.elements:
        if not isinstance(item, dict):
            continue
        try:
            cx, cy = float(item.get("x")), float(item.get("y"))
            width, height = float(item.get("width")), float(item.get("height"))
        except (TypeError, ValueError):
            continue
        if cx - width / 2 <= x <= cx + width / 2 and cy - height / 2 <= y <= cy + height / 2:
            matches.append(item)
    return matches[0] if len(matches) == 1 else None


def _made_progress(before: Observation | None, after: Observation) -> bool:
    if before is None or before.url != after.url:
        return True
    if before.state_fingerprint and after.state_fingerprint:
        return before.state_fingerprint != after.state_fingerprint
    return before.page_text != after.page_text or before.elements != after.elements


def _transient_document(url: str) -> bool:
    return str(url or "").strip().casefold() in {"", "about:blank", "about:srcdoc"}


def _same_step(left: CachedWorkflowStep, right: CachedWorkflowStep) -> bool:
    return (
        left.tool == right.tool
        and left.args == right.args
        and left.locator == right.locator
        and left.arg_bindings == right.arg_bindings
        and left.locator_bindings == right.locator_bindings
    )


__all__ = ["CompiledWorkflow", "compile_parameterized_workflow"]
