from __future__ import annotations

from dataclasses import dataclass

from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext

from .contracts import CachedBrowserWorkflow, CachedWorkflowStep


@dataclass(frozen=True)
class WorkflowReplayPlan:
    mode: str
    steps: tuple[CachedWorkflowStep, ...]
    covered_roles: tuple[str, ...] = ()
    missing_roles: tuple[str, ...] = ()
    terminal_deferred: bool = False


def normalize_semantic_replay_count(
    *,
    requested_count: int,
    total_steps: int,
    missing_input_roles: tuple[str, ...] | list[str] = (),
    missing_replay_action_prefixes: tuple[int, ...] | list[int] = (),
) -> int | None:
    """Validate the model-proposed replay boundary against its own evidence.

    ``-1`` means full replay. ``None`` rejects an invalid or useless plan.
    A same-operation selection with no declared browser gap cannot coherently
    request a partial prefix; normalize that output to a full replay.
    """

    count = int(requested_count)
    total = max(0, int(total_steps))
    if count < -1 or count > total:
        return None
    missing_roles = any(str(item or "").strip() for item in missing_input_roles)
    action_prefixes = [int(item) for item in missing_replay_action_prefixes]
    if any(item < 0 or item >= total for item in action_prefixes):
        return None
    has_gap = bool(missing_roles or action_prefixes)
    if not has_gap:
        return -1
    if count == -1 or count >= total:
        return None
    # A zero-length prefix is not cache reuse. Let normal exploration run
    # without constructing a misleading learned-workflow driver.
    if count == 0:
        return None
    if action_prefixes and count != min(action_prefixes):
        # The duplicated boundary and structured gap anchors must agree. A
        # disagreement is unsafe to guess locally, so use normal exploration.
        return None
    return count


def build_replay_plan(
    workflow: CachedBrowserWorkflow,
    context: BrowserInputContext,
) -> WorkflowReplayPlan:
    """Apply the request-scoped semantic replay boundary.

    This module intentionally contains no control-label or terminal-action
    vocabulary. The semantic selector chooses the safe prefix using the whole
    task and workflow outline; local code only validates and executes its
    structural boundary.
    """
    cached = {_role(item) for item in workflow.dynamic_input_roles if _role(item)}
    current = required_input_roles(context)
    covered = tuple(sorted(cached & current))
    missing = tuple(sorted({
        _role(item)
        for item in workflow.runtime_missing_input_roles
        if _role(item)
    }))
    count = int(workflow.runtime_replay_step_count)
    if 0 <= count < len(workflow.steps):
        return WorkflowReplayPlan(
            mode="partial",
            steps=tuple(workflow.steps[:count]),
            covered_roles=covered,
            missing_roles=missing,
            terminal_deferred=True,
        )
    return WorkflowReplayPlan(
        mode="full",
        steps=tuple(workflow.steps),
        covered_roles=covered,
    )


def required_input_roles(context: BrowserInputContext) -> set[str]:
    roles: set[str] = set()
    for item in context.candidates:
        authority = str(item.metadata.get("binding_authority") or "").casefold()
        if not (
            item.value_kind == "file"
            or item.source_kind in {"user_input", "request_semantic"}
            or authority == "publish_payload"
        ):
            continue
        role = _role(item.semantic_name or item.value_kind)
        if role:
            roles.add(role)
    return roles


def _role(value: object) -> str:
    return str(value or "").strip().casefold()


__all__ = [
    "WorkflowReplayPlan",
    "build_replay_plan",
    "normalize_semantic_replay_count",
    "required_input_roles",
]
