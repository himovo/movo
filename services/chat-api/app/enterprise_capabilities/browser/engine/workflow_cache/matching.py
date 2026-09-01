from __future__ import annotations

import hashlib
import re
from typing import Iterable

from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext

from .contracts import CachedBrowserWorkflow
from .parameters import RuntimeParameterResolver, resolve_request_slots


def request_fingerprint(request: str) -> str:
    normalized = " ".join(str(request or "").casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def select_matching_workflow(
    workflows: Iterable[CachedBrowserWorkflow],
    *,
    context: BrowserInputContext,
    capability_id: str,
) -> CachedBrowserWorkflow | None:
    ranked = []
    for workflow in workflows:
        score = workflow_match_score(
            workflow,
            context=context,
            capability_id=capability_id,
        )
        if score >= 0:
            ranked.append((score, workflow.updated_at, workflow))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[0][2]


def workflow_match_score(
    workflow: CachedBrowserWorkflow,
    *,
    context: BrowserInputContext,
    capability_id: str,
) -> int:
    cached_family = _capability_family(workflow.identity.capability_id)
    current_family = _capability_family(capability_id)
    if not workflow_runtime_compatible(workflow, context=context):
        return -1
    family_score = 20 if cached_family and cached_family == current_family else -10
    request_score = _request_match_score(workflow, context=context)
    if request_score < 0:
        return -1
    status_score = {"active": 5, "candidate": 2, "degraded": -20}.get(workflow.status, -100)
    quality_score = min(max(int(workflow.quality_score or 0), 0), 100) // 2
    return request_score + status_score + family_score + min(workflow.replay_success_count, 5) + quality_score


def workflow_runtime_compatible(
    workflow: CachedBrowserWorkflow,
    *,
    context: BrowserInputContext,
) -> bool:
    """Return whether the cached route can resolve all inputs for this run.

    Planner capability labels are intentionally excluded: they are useful
    ranking evidence but are not stable enough to make an otherwise reusable
    route ineligible.
    """
    if _request_match_score(workflow, context=context) < 0:
        return False
    resolver = RuntimeParameterResolver(
        context=context,
        request_template=workflow.request_template,
    )
    return not any(
        resolver.resolve(binding) is None
        for step in workflow.steps
        for binding in (*step.arg_bindings.values(), *step.locator_bindings.values())
    )


def _request_match_score(
    workflow: CachedBrowserWorkflow,
    *,
    context: BrowserInputContext,
) -> int:
    if workflow.request_template is not None:
        slots = resolve_request_slots(workflow.request_template, context.original_request)
        if len(slots) != workflow.request_template.slot_count or any(not item for item in slots):
            return -1
        return 40
    elif _candidate_parameterized(workflow):
        cached_roles = {str(item).strip().casefold() for item in workflow.dynamic_input_roles if str(item).strip()}
        current_roles = {
            str(item.semantic_name or item.value_kind or "").strip().casefold()
            for item in context.candidates
            if str(item.semantic_name or item.value_kind or "").strip()
        }
        if cached_roles and not cached_roles.issubset(current_roles):
            return -1
        return 35
    elif workflow.request_fingerprint:
        if workflow.request_fingerprint != request_fingerprint(context.original_request):
            return -1
        return 50
    return -1


def _candidate_parameterized(workflow: CachedBrowserWorkflow) -> bool:
    return bool(
        workflow.field_bindings
        or any(
            binding.source == "candidate"
            for step in workflow.steps
            for binding in (*step.arg_bindings.values(), *step.locator_bindings.values())
        )
    )


def _capability_family(capability_id: str) -> str:
    value = str(capability_id or "").strip().lower()
    if value in {"browser.read", "browser.navigate_and_extract", "browser.search"}:
        return "read"
    if value in {"browser.publish", "browser.publish_or_submit"}:
        return "publish"
    if value.startswith("browser."):
        return re.sub(r"^browser\.", "", value)
    return ""


__all__ = [
    "request_fingerprint",
    "select_matching_workflow",
    "workflow_match_score",
    "workflow_runtime_compatible",
]
