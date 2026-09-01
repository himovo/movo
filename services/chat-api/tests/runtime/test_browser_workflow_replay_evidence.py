from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.enterprise_capabilities.browser.engine.drivers.base import BrowserDriver
from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext
from app.enterprise_capabilities.browser.engine.workflow_cache.contracts import (
    CachedBrowserWorkflow,
    CachedCompletionContract,
    CachedWorkflowStep,
    WorkflowIdentity,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.action_policy import REPLAYABLE_ACTION_TOOLS
from app.enterprise_capabilities.browser.engine.workflow_cache.driver import LearnedWorkflowDriver
from app.enterprise_capabilities.browser.engine.workflow_cache.replay_evidence import (
    SUPPORTED_REPLAY_EVIDENCE_TOOLS,
    replay_postcondition_satisfied,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.stability import readiness_probe
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def _obs(
    *,
    text: str = "",
    fingerprint: str = "same",
    url: str = "https://example.test/home",
    elements=None,
    dom_diff=None,
    diagnostics=None,
) -> Observation:
    return Observation(
        url=url,
        title="Page",
        elements=list(elements or []),
        revision=fingerprint,
        state_fingerprint=fingerprint,
        page_text=text,
        dom_diff=dom_diff,
        diagnostics=diagnostics,
    )


def _resolve(_binding):
    return None


def test_every_replayable_action_has_an_explicit_evidence_policy() -> None:
    assert SUPPORTED_REPLAY_EVIDENCE_TOOLS == REPLAYABLE_ACTION_TOOLS


def test_disclosure_uses_successor_text_instead_of_whole_page_fingerprint() -> None:
    step = CachedWorkflowStep(
        tool="browser_click",
        locator={
            "selector": "#menu",
            "role": "button",
            "semanticPurpose": "navigation-expand",
            "hasPopup": "menu",
        },
        source_url_shape="example.test/home",
        target_url_shape="example.test/home",
        expect_state_change=True,
    )
    successor = CachedWorkflowStep(
        tool="browser_wait_for",
        args={"text": "内容管理", "timeout": 5000},
    )

    assert replay_postcondition_satisfied(
        step,
        before=_obs(text="首页"),
        after=_obs(text="首页 内容管理"),
        resolve=_resolve,
        successor=successor,
    )


def test_disclosure_accepts_expanded_dom_diff_without_fingerprint_change() -> None:
    step = CachedWorkflowStep(
        tool="browser_click",
        locator={"selector": "#menu", "hasPopup": "menu"},
        expect_state_change=True,
    )
    after = _obs(dom_diff={
        "transition": "changed_then_stable",
        "changed_elements": [{"selector": "#menu", "expanded": True}],
    })

    assert replay_postcondition_satisfied(
        step, before=_obs(), after=after, resolve=_resolve,
    )


def test_popup_or_list_click_uses_visible_successor_control_as_evidence() -> None:
    step = CachedWorkflowStep(
        tool="browser_click",
        locator={"role": "button", "name": "新的创作", "hasPopup": "menu"},
        expect_state_change=True,
    )
    successor = CachedWorkflowStep(
        tool="browser_click",
        locator={"role": "menuitem", "name": "文章"},
    )
    after = _obs(elements=[{
        "ref": "article-item", "role": "menuitem", "name": "文章", "visible": True,
    }])

    assert replay_postcondition_satisfied(
        step,
        before=_obs(),
        after=after,
        resolve=_resolve,
        successor=successor,
    )


def test_interaction_with_no_effect_and_no_successor_evidence_is_rejected() -> None:
    step = CachedWorkflowStep(
        tool="browser_click",
        locator={"selector": "#menu", "hasPopup": "menu"},
        expect_state_change=True,
    )

    assert not replay_postcondition_satisfied(
        step,
        before=_obs(),
        after=_obs(dom_diff={"transition": "no_effect_timeout"}),
        resolve=_resolve,
    )


def test_terminal_delivery_defers_to_business_effect_guard_without_retrying() -> None:
    step = CachedWorkflowStep(
        tool="browser_click",
        locator={"role": "button", "name": "保存为草稿", "semanticPurpose": "save"},
        expect_state_change=True,
    )
    before = _obs()
    after = _obs(dom_diff={"transition": "no_effect_timeout"})

    assert replay_postcondition_satisfied(
        step,
        before=before,
        after=after,
        resolve=_resolve,
        allow_deferred_completion=True,
    )
    assert not replay_postcondition_satisfied(
        step,
        before=before,
        after=after,
        resolve=_resolve,
        allow_deferred_completion=False,
    )


def test_failed_terminal_click_is_not_rescued_by_successful_observe() -> None:
    workflow = CachedBrowserWorkflow(
        workflow_id="terminal-failed",
        identity=WorkflowIdentity(
            user_id="u1", site_id="example.test", operation_id="save",
            capability_id="browser.submit", signature_hash="terminal-failed",
        ),
        steps=[CachedWorkflowStep(
            tool="browser_click",
            locator={"role": "button", "name": "保存为草稿", "semanticPurpose": "save"},
            expect_state_change=True,
        )],
        completion=CachedCompletionContract(capability_id="browser.submit"),
    )
    driver = LearnedWorkflowDriver(
        workflow=workflow,
        fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="保存草稿"),
    )
    before = _obs(elements=[{
        "ref": "save", "role": "button", "name": "保存为草稿",
        "semanticPurpose": "save", "visible": True,
        "inViewport": True, "hitTestable": True,
    }])
    click = asyncio.run(driver.next_step("保存草稿", [], before))
    driver.on_step_completed(click, False, before, {"clicked": False})

    observe = asyncio.run(driver.next_step("保存草稿", [], before))
    assert observe.tool == "browser_observe"
    driver.on_step_completed(observe, True, before, {"observed": True})

    fallback = asyncio.run(driver.next_step("保存草稿", [], before))
    assert fallback.tool == "browser_done"
    assert fallback.args["summary"] == "fallback"
    assert driver.replay_failed


def test_cached_write_is_complete_only_after_confirmed_effect_receipt() -> None:
    workflow = CachedBrowserWorkflow(
        workflow_id="terminal-confirmed",
        identity=WorkflowIdentity(
            user_id="u1", site_id="example.test", operation_id="save",
            capability_id="browser.submit", signature_hash="terminal-confirmed",
        ),
        steps=[CachedWorkflowStep(
            tool="browser_click",
            locator={"role": "button", "name": "保存为草稿", "semanticPurpose": "save"},
            expect_state_change=True,
        )],
        completion=CachedCompletionContract(capability_id="browser.submit"),
    )
    driver = LearnedWorkflowDriver(
        workflow=workflow, fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="保存草稿"),
    )
    before = _obs(elements=[{
        "ref": "save", "role": "button", "name": "保存为草稿",
        "semanticPurpose": "save", "visible": True,
        "inViewport": True, "hitTestable": True,
    }])
    click = asyncio.run(driver.next_step("保存草稿", [], before))
    driver.on_step_completed(click, True, before, {"clicked": True})

    assert not driver.replay_completed
    driver.on_effect_receipt(SimpleNamespace(status="unknown", action_name="保存为草稿"))
    assert not driver.replay_completed
    driver.on_effect_receipt(SimpleNamespace(status="confirmed_success", action_name="保存为草稿"))
    assert driver.replay_completed


def test_unrelated_effect_receipt_cannot_complete_cached_terminal() -> None:
    workflow = CachedBrowserWorkflow(
        workflow_id="terminal-unrelated",
        identity=WorkflowIdentity(
            user_id="u1", site_id="example.test", operation_id="save",
            capability_id="browser.submit", signature_hash="terminal-unrelated",
        ),
        steps=[CachedWorkflowStep(
            tool="browser_click", locator={"role": "button", "name": "保存为草稿"},
            expect_state_change=True,
        )],
        completion=CachedCompletionContract(capability_id="browser.submit"),
    )
    driver = LearnedWorkflowDriver(
        workflow=workflow, fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="保存草稿"),
    )
    before = _obs(elements=[{
        "ref": "save", "role": "button", "name": "保存为草稿",
        "visible": True, "inViewport": True, "hitTestable": True,
    }])
    click = asyncio.run(driver.next_step("保存草稿", [], before))
    driver.on_step_completed(click, True, before, {"clicked": True})

    driver.on_effect_receipt(SimpleNamespace(
        status="confirmed_success", action_name="打开编辑器",
    ))

    assert not driver.replay_completed


def test_readiness_probe_reuses_explicit_wait_text_and_timeout() -> None:
    successor = CachedWorkflowStep(
        tool="browser_wait_for",
        args={"text": "内容管理", "timeout": 12000},
    )

    probe = readiness_probe(successor, _resolve)

    assert probe is not None
    assert probe.tool == "browser_wait_for"
    assert probe.args == {"text": "内容管理", "probe_only": True, "timeout": 12000}


@pytest.mark.parametrize("tool", [
    "browser_fill",
    "browser_upload_file",
    "browser_paste_image",
])
def test_sidecar_verified_actions_do_not_require_page_fingerprint_changes(tool: str) -> None:
    step = CachedWorkflowStep(tool=tool, expect_state_change=True)

    assert replay_postcondition_satisfied(
        step, before=_obs(), after=_obs(), resolve=_resolve,
    )


@pytest.mark.parametrize(
    ("tool", "result", "diagnostics", "expected"),
    [
        ("browser_wait_for", {"matched": True}, None, True),
        ("browser_wait_for", {"matched": False, "model_required": True}, None, False),
        ("browser_wait_for", {"waited": True, "mode": "delay"}, None, True),
        ("browser_select", {}, {"select": {"confirmed": True}}, True),
        ("browser_select", {}, {"select": {"confirmed": False}}, False),
        ("browser_scroll", {}, {"scroll": {"progressed": True}}, True),
        ("browser_scroll", {}, {"scroll": {"progressed": False}}, False),
    ],
)
def test_result_verified_actions_require_their_logical_receipt(
    tool: str,
    result: dict,
    diagnostics: dict | None,
    expected: bool,
) -> None:
    assert replay_postcondition_satisfied(
        CachedWorkflowStep(tool=tool, expect_state_change=True),
        before=_obs(),
        after=_obs(diagnostics=diagnostics),
        resolve=_resolve,
        result=result,
    ) is expected


def test_offscreen_successor_does_not_validate_a_disclosure() -> None:
    step = CachedWorkflowStep(
        tool="browser_click",
        locator={"selector": "#menu", "semanticPurpose": "navigation-expand"},
        expect_state_change=True,
    )
    successor = CachedWorkflowStep(
        tool="browser_click",
        locator={"role": "menuitem", "name": "内容管理"},
    )
    after = _obs(text="首页 内容管理", elements=[{
        "ref": "hidden-item", "role": "menuitem", "name": "内容管理",
        "visible": True, "inViewport": False, "hitTestable": False,
    }])

    assert not replay_postcondition_satisfied(
        step,
        before=_obs(text="首页 内容管理"),
        after=after,
        resolve=_resolve,
        successor=successor,
    )


def test_stability_timeout_is_not_positive_click_evidence() -> None:
    step = CachedWorkflowStep(tool="browser_click", expect_state_change=True)
    assert not replay_postcondition_satisfied(
        step,
        before=_obs(),
        after=_obs(dom_diff={"transition": "stability_timeout"}),
        resolve=_resolve,
    )


@pytest.mark.parametrize("tool", [
    "browser_navigate",
    "browser_tab_new",
    "browser_back",
    "browser_forward",
])
def test_navigation_actions_use_route_shape_evidence(tool: str) -> None:
    step = CachedWorkflowStep(
        tool=tool,
        source_url_shape="example.test/home",
        target_url_shape="example.test/results?page",
        expect_state_change=True,
    )

    assert replay_postcondition_satisfied(
        step,
        before=_obs(url="https://example.test/home"),
        after=_obs(url="https://example.test/results?page=2"),
        resolve=_resolve,
    )


def test_hover_and_press_use_interaction_surface_or_successor_evidence() -> None:
    hover = CachedWorkflowStep(tool="browser_hover", expect_state_change=True)
    press = CachedWorkflowStep(tool="browser_press", expect_state_change=True)
    successor = CachedWorkflowStep(tool="browser_wait_for", args={"text": "搜索结果"})

    assert replay_postcondition_satisfied(
        hover,
        before=_obs(),
        after=_obs(
            elements=[{
                "ref": "menu", "role": "menuitem", "name": "Open",
                "visible": True, "inViewport": True, "hitTestable": True,
            }],
            dom_diff={"transition": "new_interaction_surface"},
        ),
        resolve=_resolve,
    )
    assert replay_postcondition_satisfied(
        press,
        before=_obs(text="搜索"),
        after=_obs(text="搜索 搜索结果"),
        resolve=_resolve,
        successor=successor,
    )


class _Fallback(BrowserDriver):
    kind = "fallback"

    async def next_step(self, goal, history, observation, state_ledger=None):
        return Decision(tool="browser_done", args={"summary": "fallback"})


def test_driver_recovery_uses_successor_wait_as_completion_evidence() -> None:
    workflow = CachedBrowserWorkflow(
        workflow_id="menu-workflow",
        identity=WorkflowIdentity(
            user_id="u1",
            site_id="example.test",
            operation_id="navigation.open_menu",
            capability_id="browser.navigate",
            signature_hash="menu-signature",
        ),
        steps=[
            CachedWorkflowStep(
                tool="browser_click",
                locator={
                    "selector": "#menu",
                    "role": "button",
                    "name": "Expand navigation menu",
                    "hasPopup": "menu",
                },
                source_url_shape="example.test/home",
                target_url_shape="example.test/home",
                expect_state_change=True,
            ),
            CachedWorkflowStep(
                tool="browser_wait_for",
                args={"text": "内容管理", "timeout": 5000},
                source_url_shape="example.test/home",
                target_url_shape="example.test/home",
            ),
        ],
    )
    driver = LearnedWorkflowDriver(
        workflow=workflow,
        fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="打开内容管理"),
    )
    before = _obs(elements=[{
        "ref": "live-menu",
        "selector": "#menu",
        "role": "button",
        "name": "Expand navigation menu",
        "hasPopup": "menu",
    }])

    click = asyncio.run(driver.next_step("打开菜单", [], before))
    assert click.tool == "browser_click"
    driver.on_step_completed(
        click,
        True,
        _obs(dom_diff={"transition": "no_effect_timeout"}),
    )

    recovery = asyncio.run(driver.next_step("打开菜单", [], _obs()))
    assert recovery.tool == "browser_wait_for"
    assert recovery.args["text"] == "内容管理"
    driver.on_step_completed(
        recovery,
        True,
        _obs(text="内容管理 草稿箱"),
        {"matched": True},
    )

    assert not driver.replay_failed
    next_step = asyncio.run(driver.next_step("打开菜单", [], _obs(text="内容管理 草稿箱")))
    assert next_step.tool == "browser_wait_for"


def test_driver_recovery_does_not_advance_when_wait_transport_succeeds_without_match() -> None:
    workflow = CachedBrowserWorkflow(
        workflow_id="menu-workflow-failed-probe",
        identity=WorkflowIdentity(
            user_id="u1", site_id="example.test",
            operation_id="navigation.open_menu", capability_id="browser.navigate",
            signature_hash="menu-signature-failed-probe",
        ),
        steps=[
            CachedWorkflowStep(
                tool="browser_click",
                locator={"selector": "#menu", "role": "button", "name": "Menu"},
                source_url_shape="example.test/home",
                target_url_shape="example.test/home",
                expect_state_change=True,
            ),
            CachedWorkflowStep(
                tool="browser_wait_for",
                args={"text": "内容管理", "timeout": 5000},
                source_url_shape="example.test/home",
                target_url_shape="example.test/home",
            ),
        ],
    )
    driver = LearnedWorkflowDriver(
        workflow=workflow,
        fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="打开内容管理"),
    )
    before = _obs(elements=[{
        "ref": "menu", "selector": "#menu", "role": "button", "name": "Menu",
        "visible": True, "inViewport": True, "hitTestable": True,
    }])
    click = asyncio.run(driver.next_step("打开菜单", [], before))
    driver.on_step_completed(click, True, _obs(dom_diff={"transition": "no_effect_timeout"}))
    probe = asyncio.run(driver.next_step("打开菜单", [], _obs()))
    driver.on_step_completed(
        probe, True, _obs(text="内容管理"), {"matched": False, "model_required": True},
    )

    retry = asyncio.run(driver.next_step("打开菜单", [], before))
    assert retry.tool == "browser_click"


def _menu_to_content_workflow(workflow_id: str) -> CachedBrowserWorkflow:
    return CachedBrowserWorkflow(
        workflow_id=workflow_id,
        identity=WorkflowIdentity(
            user_id="u1", site_id="example.test",
            operation_id="navigation.open_content", capability_id="browser.navigate",
            signature_hash=workflow_id,
        ),
        steps=[
            CachedWorkflowStep(
                tool="browser_click",
                locator={
                    "selector": "#menu", "role": "button",
                    "name": "展开导航", "hasPopup": "menu",
                },
                expect_state_change=True,
            ),
            CachedWorkflowStep(
                tool="browser_click",
                locator={"role": "menuitem", "name": "内容管理", "text": "内容管理"},
                expect_state_change=True,
            ),
        ],
    )


def _expanded_menu_elements(*, include_real_target: bool) -> list[dict]:
    elements = [{
        "ref": "e1", "selector": "#menu", "role": "button",
        "name": "展开导航 首页 内容管理 草稿箱",
        "text": "首页 内容管理 草稿箱", "hasPopup": "menu",
        "visible": True, "inViewport": True, "hitTestable": True,
    }]
    if include_real_target:
        elements.append({
            "ref": "e58", "role": "menuitem", "name": "内容管理",
            "text": "内容管理", "visible": True,
            "inViewport": True, "hitTestable": True,
        })
    return elements


def test_recovery_advances_only_when_the_real_successor_is_actionable() -> None:
    driver = LearnedWorkflowDriver(
        workflow=_menu_to_content_workflow("exact-successor"),
        fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="打开内容管理"),
    )
    before = _obs(elements=[{
        "ref": "e1", "selector": "#menu", "role": "button", "name": "展开导航",
        "hasPopup": "menu", "visible": True, "inViewport": True, "hitTestable": True,
    }])

    click = asyncio.run(driver.next_step("打开内容管理", [], before))
    driver.on_step_completed(click, True, _obs(dom_diff={"transition": "no_effect_timeout"}))
    probe = asyncio.run(driver.next_step("打开内容管理", [], _obs()))
    expanded = _obs(
        text="首页 内容管理 草稿箱",
        elements=_expanded_menu_elements(include_real_target=True),
    )
    driver.on_step_completed(probe, True, expanded, {"matched": True})

    content_click = asyncio.run(driver.next_step("打开内容管理", [], expanded))
    assert content_click.tool == "browser_click"
    assert content_click.args["ref"] == "e58"


def test_recovery_does_not_treat_ancestor_text_as_successor_readiness() -> None:
    driver = LearnedWorkflowDriver(
        workflow=_menu_to_content_workflow("ancestor-is-not-successor"),
        fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="打开内容管理"),
    )
    before = _obs(elements=[{
        "ref": "e1", "selector": "#menu", "role": "button", "name": "展开导航",
        "hasPopup": "menu", "visible": True, "inViewport": True, "hitTestable": True,
    }])

    click = asyncio.run(driver.next_step("打开内容管理", [], before))
    driver.on_step_completed(click, True, _obs(dom_diff={"transition": "no_effect_timeout"}))
    probe = asyncio.run(driver.next_step("打开内容管理", [], _obs()))
    misleading = _obs(
        text="首页 内容管理 草稿箱",
        elements=_expanded_menu_elements(include_real_target=False),
    )
    driver.on_step_completed(probe, True, misleading, {"matched": True})

    retry = asyncio.run(driver.next_step("打开内容管理", [], before))
    assert retry.tool == "browser_click"
    assert retry.args["ref"] == "e1"


def test_recovery_waits_for_present_successor_instead_of_reclicking_opener() -> None:
    driver = LearnedWorkflowDriver(
        workflow=_menu_to_content_workflow("successor-animating"),
        fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="打开内容管理"),
    )
    before = _obs(elements=[{
        "ref": "e1", "selector": "#menu", "role": "button", "name": "展开导航",
        "hasPopup": "menu", "visible": True, "inViewport": True, "hitTestable": True,
    }])
    click = asyncio.run(driver.next_step("打开内容管理", [], before))
    driver.on_step_completed(click, True, _obs(dom_diff={"transition": "no_effect_timeout"}))
    probe = asyncio.run(driver.next_step("打开内容管理", [], _obs()))
    animating = _obs(elements=[{
        "ref": "e58", "role": "menuitem", "name": "内容管理", "text": "内容管理",
        "visible": True, "inViewport": True, "hitTestable": False,
    }])
    driver.on_step_completed(probe, True, animating, {"matched": True})

    wait_again = asyncio.run(driver.next_step("打开内容管理", [], animating))

    assert wait_again.tool == "browser_wait_for"
    assert wait_again.args["text"] == "内容管理"

    ready = _obs(elements=[{
        "ref": "e58", "role": "menuitem", "name": "内容管理", "text": "内容管理",
        "visible": True, "inViewport": True, "hitTestable": True,
    }])
    driver.on_step_completed(wait_again, True, ready, {"matched": True})
    next_click = asyncio.run(driver.next_step("打开内容管理", [], ready))
    assert next_click.tool == "browser_click"
    assert next_click.args["ref"] == "e58"
