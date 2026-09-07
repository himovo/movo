"""Driver selection — single decision point for "which driver runs
this browser task?".

Decision rule is intentionally simple and explicit:

* If the upstream pipeline selected a composite_task skill AND that
  skill carries usable steps → return a :class:`SkillDriver` that
  replays them, with an :class:`ExplorationDriver` wired in as
  fallback.
* Otherwise → return a plain :class:`ExplorationDriver`.

Any task category (form / scrape / general) goes through this
function; the decision is task-type agnostic.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.skill_assets.composite_task import parse_composite_skill

from .base import BrowserDriver
from .exploration import ExplorationDriver
from .form_input import FormInputDriver
from .skill import SkillDriver
from app.enterprise_capabilities.browser.engine.form_input import BrowserInputContext


def _extract_composite_steps(output_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pull composite_task steps out of ``output_spec``.

    Skill data flows in under one of two keys depending on which stage
    of the orchestrator wrote it: ``selected_skill`` is set by the
    user-skill resolver; ``selected_user_skill`` is set by the graph
    orchestrator's hand-off. Either way the raw markdown lives at
    ``skill_markdown`` and is parsed with the canonical YAML reader.

    Returns ``[]`` when no skill is selected, the markdown has no
    frontmatter, or the frontmatter has zero usable steps. The caller
    treats an empty list as "no skill — go exploration".
    """
    if not isinstance(output_spec, dict):
        return []
    skill = (
        output_spec.get("selected_skill")
        or output_spec.get("selected_user_skill")
        or {}
    )
    if not isinstance(skill, dict):
        return []
    markdown = str(skill.get("skill_markdown") or "")
    if not markdown:
        return []
    parsed = parse_composite_skill(markdown)
    raw_steps = parsed.get("steps") if isinstance(parsed, dict) else None
    if not isinstance(raw_steps, list):
        return []
    # Only keep steps that carry at least one *executable* signal —
    # locator, fill_value, or navigate_url. Pure "instruction-only"
    # steps (e.g. advisory site profiles) can't be strictly replayed
    # and are filtered out so SkillDriver doesn't waste budget on them.
    actionable: List[Dict[str, Any]] = []
    for step in raw_steps:
        if not isinstance(step, dict):
            continue
        has_locator = isinstance(step.get("locators"), dict) or isinstance(step.get("locator"), dict)
        has_fill = "fill_value" in step
        has_nav = bool(str(step.get("navigate_url") or "").strip())
        if has_locator or has_fill or has_nav:
            actionable.append(step)
    return actionable


def select_driver(
    *,
    lang: str,
    enterprise_sites: Optional[Dict[str, str]],
    output_spec: Dict[str, Any],
    input_context: Optional[BrowserInputContext] = None,
    capability_id: str = "",
) -> BrowserDriver:
    """Return the appropriate :class:`BrowserDriver` for this task.

    See module docstring for the decision rule. The returned driver is
    ready to use — no further wiring required.
    """
    steps = _extract_composite_steps(output_spec)
    fallback: BrowserDriver = ExplorationDriver(
        lang=lang,
        enterprise_sites=enterprise_sites,
    )
    if input_context is not None:
        fallback = FormInputDriver(
            fallback=fallback,
            input_context=input_context,
            capability_id=capability_id,
            lang=lang,
        )
    if steps:
        return SkillDriver(steps=steps, fallback=fallback)
    return fallback
