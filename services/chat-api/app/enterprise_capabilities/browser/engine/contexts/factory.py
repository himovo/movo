"""Dispatcher — routes a browser task to the right context.

Reads ``schema.category`` from the content_task_spec and picks the
matching context class. Categories we recognise:

    form_submission  → FormContext (single-shot fill + submit)
    scrape_extract   → ScrapeContext (paginated extraction)
    anything else    → GeneralBrowserContext (stateful planner fallback)

Each context's own ``maybe_init`` also does a category check and
returns NullContext when it doesn't apply — the factory just saves the
executor from having to chain them manually.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask

from ._logging import emit as _emit
from .base import BrowserTaskContext
from .form import FormContext
from .general import GeneralBrowserContext
from .scrape import ScrapeContext
from .upstream_coverage import fulfilled_general_requirements


def _extract_category(output_spec: Dict[str, Any]) -> str:
    cts = output_spec.get("content_task_spec") if isinstance(output_spec, dict) else None
    if not isinstance(cts, dict):
        return ""
    schema = cts.get("schema") if isinstance(cts.get("schema"), dict) else {}
    return str(schema.get("category") or "").strip().lower()


def maybe_init(
    *, node: CapabilityTask, output_spec: Dict[str, Any],
    original_user_request: str, goal: str, lang: str,
    input_context: Optional[BrowserInputContext] = None,
) -> BrowserTaskContext:
    """Return a specialised context or the stateful general fallback."""
    category = _extract_category(output_spec)
    kwargs = dict(
        node=node, output_spec=output_spec,
        original_user_request=original_user_request,
        goal=goal, lang=lang,
    )
    if category == "form_submission":
        ctx = FormContext.maybe_init(**kwargs)
    elif category == "scrape_extract":
        ctx = ScrapeContext.maybe_init(**kwargs)
    else:
        ctx = GeneralBrowserContext(
            node=node,
            original_user_request=original_user_request,
            goal=goal,
            lang=lang,
            prefulfilled_requirements=fulfilled_general_requirements(
                goal,
                input_context,
            ) if input_context is not None else set(),
        )
    _emit(
        type(ctx).__name__, "ctx_init",
        category=category or "(none)",
        lang=lang,
        goal=str(goal or "")[:80],
        active=ctx.active,
    )
    return ctx
