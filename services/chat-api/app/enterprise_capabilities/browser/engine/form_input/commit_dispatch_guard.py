from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .commit_resolver import (
    commit_control_relation_for_fields,
    is_semantic_commit_control,
)
from .commit_binding import commit_control_key
from .contracts import FieldDescriptor


@dataclass(frozen=True)
class CommitDispatchGuard:
    decision: Optional[Decision] = None
    reason: str = ""


def guard_dirty_form_commit(
    *,
    decision: Decision,
    observation: Observation,
    fields: Iterable[FieldDescriptor],
    mutated_field_keys: Iterable[str],
    bound_action_keys: Iterable[str] = (),
) -> CommitDispatchGuard:
    """Keep commit-looking actions inside the active mutated form.

    Publishing UIs often expose a navigation item and a final submit control
    with the same visible label. Once this transaction has changed a field,
    an out-of-scope publish/send/submit control must not consume or discard the
    editor state.
    """

    if decision.tool != "browser_click" or not set(mutated_field_keys):
        return CommitDispatchGuard()
    ref = str((decision.args or {}).get("ref") or "").strip()
    if not ref:
        return CommitDispatchGuard()
    target = next((
        item for item in list(observation.elements or [])
        if isinstance(item, dict)
        and str(item.get("ref") or "").strip() == ref
    ), None)
    if target is None or not is_semantic_commit_control(
        target,
        require_hit_testable=False,
    ):
        return CommitDispatchGuard()
    field_list = list(fields)
    relation = commit_control_relation_for_fields(
        target,
        fields=field_list,
        require_hit_testable=False,
    )
    if (
        relation.related
        or commit_control_key(target) in set(bound_action_keys)
    ):
        return CommitDispatchGuard()
    return CommitDispatchGuard(
        decision=Decision(
            tool="browser_observe",
            args={},
            rationale=(
                "[form_commit_dispatch] commit-looking control is not bound to "
                "the active mutated form; refresh and resolve the form-owned action"
            ),
        ),
        reason=(
            "commit-looking control does not belong to the active form"
            if relation.status == "unrelated"
            else "commit-looking control has no confirmed form binding"
        ),
    )


__all__ = ["CommitDispatchGuard", "guard_dirty_form_commit"]
