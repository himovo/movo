from __future__ import annotations

import hashlib
import json
from typing import Iterable

from .contracts import CachedCompletionContract, CachedFieldBinding, CachedWorkflowStep
from .stability import fragile_selector


def workflow_plan_hash(
    steps: Iterable[CachedWorkflowStep],
    field_bindings: Iterable[CachedFieldBinding],
    completion: CachedCompletionContract | None,
) -> str:
    payload = {
        "steps": [item.model_dump(mode="json") for item in steps],
        "field_bindings": [item.model_dump(mode="json") for item in field_bindings],
        "completion": completion.model_dump(mode="json") if completion is not None else None,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def workflow_quality_score(
    steps: Iterable[CachedWorkflowStep],
    field_bindings: Iterable[CachedFieldBinding],
    *,
    complete: bool,
) -> int:
    action_steps = list(steps)
    bindings = list(field_bindings)
    if not complete or not action_steps:
        return 0
    locator_steps = [
        step for step in action_steps
        if step.tool not in {"browser_navigate", "browser_tab_new", "browser_back", "browser_forward"}
    ]
    stable_locators = sum(
        1 for step in locator_steps
        if step.locator.get("selector")
        or (step.locator.get("role") and (step.locator.get("name") or step.locator.get("text")))
    )
    mutation_steps = sum(
        1 for step in action_steps
        if step.tool in {
            "browser_fill", "browser_select", "browser_upload_file", "browser_paste_image",
        }
    )
    locator_score = 20 if not locator_steps else round(20 * stable_locators / len(locator_steps))
    binding_score = 20 if mutation_steps == 0 else min(20, round(20 * len(bindings) / mutation_steps))
    # Prefer concise paths only as a small tie-breaker; completeness and
    # stable targeting dominate so a short but partial workflow never wins.
    concise_score = max(0, 20 - 2 * max(0, len(action_steps) - 5))
    readiness_bonus = min(10, 5 * sum(
        1 for step in action_steps if step.tool == "browser_wait_for"
    ))
    race_penalty = 0
    for index, step in enumerate(action_steps):
        if fragile_selector(step.locator):
            race_penalty += 5
        if (
            index > 0
            and action_steps[index - 1].tool == "browser_scroll"
            and step.tool in {"browser_click", "browser_fill", "browser_select", "browser_press"}
        ):
            race_penalty += 10
    return max(0, min(
        100,
        40 + locator_score + binding_score + concise_score + readiness_bonus - race_penalty,
    ))


__all__ = ["workflow_plan_hash", "workflow_quality_score"]
