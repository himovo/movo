from __future__ import annotations

from app.enterprise_capabilities.browser.engine.contexts.action_transition import BrowserActionTransition
from app.enterprise_capabilities.browser.engine.contexts.general import GeneralBrowserContext
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


SCOPE = "body > header > form"
GOAL = "搜索员工服务台并打开一个结果"


def _context() -> GeneralBrowserContext:
    node = CapabilityTask(node_id="browser", goal=GOAL, assigned_agent="agent.browser")
    return GeneralBrowserContext(
        lang="zh",
        node=node,
        goal=GOAL,
        original_user_request=GOAL,
    )


def _page(*, old_ref: bool = False) -> Observation:
    return Observation(
        url="https://example.test/explore",
        title="Explore",
        elements=[
            {
                "ref": "old-field" if old_ref else "live-field",
                "role": "searchbox",
                "editable": True,
                "semanticPurpose": "search",
                "selector": "#query",
                "scopeId": f"0:{SCOPE}",
                "scopeSelector": SCOPE,
                "frameDepth": 0,
                "value": "" if old_ref else "员工服务台",
            },
            {
                "ref": "search-submit",
                "role": "button",
                "semanticPurpose": "search",
                "selector": "#submit",
                "scopeId": f"0:{SCOPE}",
                "scopeSelector": SCOPE,
                "frameDepth": 0,
            },
            {
                "ref": "suggestion",
                "role": "option",
                "name": "员工服务台是什么",
                "selector": "#suggestion",
                "scopeId": "0:#search-popup",
                "scopeSelector": "#search-popup",
                "frameDepth": 0,
            },
        ],
    )


def _transition(
    context: GeneralBrowserContext,
    decision: Decision,
    before: Observation,
    after: Observation,
    *,
    ok: bool = True,
) -> None:
    context.after_transition(
        BrowserActionTransition.capture(
            decision,
            before=before,
            after=after,
        ),
        {},
        ok,
        error=None if ok else "no observable progress",
    )


def _fill(context: GeneralBrowserContext) -> Observation:
    before = _page(old_ref=True)
    after = _page()
    _transition(
        context,
        Decision(
            tool="browser_fill",
            args={"ref": "old-field", "value": "员工服务台"},
        ),
        before,
        after,
    )
    return after


def test_confirmed_fill_prefers_enter_then_current_related_search_button() -> None:
    context = _context()
    page = _fill(context)

    enter = context.suggest_next_action(page)
    assert enter is not None
    assert enter.tool == "browser_press"
    assert enter.args["ref"] == "live-field"
    _transition(context, enter, page, page, ok=False)

    observe = context.suggest_next_action(page)
    assert observe is not None
    assert observe.tool == "browser_observe"
    _transition(context, observe, page, page)

    click = context.suggest_next_action(page)
    assert click is not None
    assert click.tool == "browser_click"
    assert click.args["ref"] == "search-submit"


def test_policy_stops_after_one_enter_and_one_search_button_attempt() -> None:
    context = _context()
    page = _fill(context)

    for expected_tool, ok in (
        ("browser_press", False),
        ("browser_observe", True),
        ("browser_click", False),
        ("browser_observe", True),
    ):
        decision = context.suggest_next_action(page)
        assert decision is not None
        assert decision.tool == expected_tool
        _transition(context, decision, page, page, ok=ok)

    assert context.suggest_next_action(page) is None
    assert context.search_submission.phase == "exhausted"
    assert context.search_submission.enter_attempts == 1
    assert context.search_submission.button_attempts == 1


def test_unique_semantic_search_button_is_safe_fallback_without_form_metadata() -> None:
    context = _context()
    page = _fill(context)
    page.elements[1].pop("scopeId", None)
    page.elements[1].pop("scopeSelector", None)

    enter = context.suggest_next_action(page)
    assert enter is not None
    _transition(context, enter, page, page, ok=False)
    observe = context.suggest_next_action(page)
    assert observe is not None
    _transition(context, observe, page, page)

    click = context.suggest_next_action(page)
    assert click is not None
    assert click.tool == "browser_click"
    assert click.args["ref"] == "search-submit"


def test_search_submission_phase_survives_context_checkpoint() -> None:
    context = _context()
    page = _fill(context)
    enter = context.suggest_next_action(page)
    assert enter is not None
    _transition(context, enter, page, page, ok=False)

    restored = _context()
    restored.restore_checkpoint_state(context.export_checkpoint_state())

    next_action = restored.suggest_next_action(page)
    assert next_action is not None
    assert next_action.tool == "browser_observe"
    assert restored.search_submission.enter_attempts == 1
