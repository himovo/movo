from __future__ import annotations

from app.enterprise_capabilities.browser.engine.contexts.action_transition import BrowserActionTransition
from app.enterprise_capabilities.browser.engine.contexts.detail_progress import (
    DetailTargetFingerprint,
    capture_detail_baseline,
)
from app.enterprise_capabilities.browser.engine.contexts.general import GeneralBrowserContext
from app.enterprise_capabilities.browser.engine.contexts.inline_target_editor import (
    inline_target_editor_observed,
)
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


_RESULT_SCOPE = "body > main > article:nth-of-type(1)"


def _result_action() -> dict:
    return {
        "ref": "comment-action",
        "role": "button",
        "name": "添加评论",
        "scopeId": f"0:{_RESULT_SCOPE}",
        "scopeSelector": _RESULT_SCOPE,
        "scopeRole": "article",
        "scopeLockable": True,
        "frameDepth": 0,
    }


def _results(*, extra_elements: list[dict] | None = None, auth=None) -> Observation:
    return Observation(
        url="https://example.test/search?q=assistant",
        title="Search results",
        page_text="高赞问题的摘要内容",
        elements=[_result_action(), *(extra_elements or [])],
        auth=auth,
    )


def _target() -> DetailTargetFingerprint:
    return DetailTargetFingerprint(
        source_url="https://example.test/search?q=assistant",
        target_url="",
        labels=("添加评论", "高赞问题"),
        scope_id=f"0:{_RESULT_SCOPE}",
    )


def _comment_field(*, scope: str | None = None) -> dict:
    field_scope = scope or f"{_RESULT_SCOPE} > div.comment-editor"
    return {
        "ref": "comment-input",
        "selector": "#comment-input",
        "role": "textbox",
        "name": "评论内容",
        "editable": True,
        "scopeId": f"0:{field_scope}",
        "scopeSelector": field_scope,
        "scopeRole": "form",
        "scopeLockable": True,
        "frameDepth": 0,
    }


def test_target_owned_inline_editor_is_detail_evidence() -> None:
    before = _results()
    after = _results(extra_elements=[_comment_field()])

    evidence = inline_target_editor_observed(
        Decision(tool="browser_click", args={"ref": "comment-action"}),
        before,
        after,
        target=_target(),
    )

    assert evidence.confirmed is True
    assert evidence.field_ref == "comment-input"
    assert evidence.relation_source == "interaction_scope"


def test_unrelated_inline_editor_is_not_detail_evidence() -> None:
    before = _results()
    after = _results(extra_elements=[
        _comment_field(scope="body > aside > div.feedback-editor"),
    ])

    evidence = inline_target_editor_observed(
        Decision(tool="browser_click", args={"ref": "comment-action"}),
        before,
        after,
        target=_target(),
    )

    assert evidence.confirmed is False
    assert evidence.reason == "editor_not_owned_by_target"


def test_search_or_auth_editor_is_not_detail_evidence() -> None:
    before = _results()
    search_after = _results(extra_elements=[{
        **_comment_field(),
        "role": "searchbox",
        "semanticPurpose": "search",
    }])
    login_after = _results(
        extra_elements=[{
            **_comment_field(),
            "type": "password",
        }],
        auth={"state": "required"},
    )
    decision = Decision(tool="browser_click", args={"ref": "comment-action"})

    assert inline_target_editor_observed(
        decision, before, search_after, target=_target(),
    ).confirmed is False
    assert inline_target_editor_observed(
        decision, before, login_after, target=_target(),
    ).confirmed is False


def test_general_ledger_accepts_target_owned_inline_editor_and_releases_lock() -> None:
    goal = "搜索员工AI助手，选择一个高赞问题，点击添加评论并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(
        lang="zh",
        node=node,
        goal=goal,
        original_user_request=goal,
    )
    before = _results()
    after = _results(extra_elements=[_comment_field()])
    context.completed.update({"navigate", "search"})
    context.detail_baseline = capture_detail_baseline(before)

    decision = Decision(tool="browser_click", args={"ref": "comment-action"})
    verdict, prepared, hint = context.validate_action(decision, before)
    assert verdict == "allow", hint

    context.after_transition(
        BrowserActionTransition.capture(
            prepared,
            before=before,
            after=after,
        ),
        {},
        True,
    )

    assert "open_result" in context.completed
    assert context.detail_target_lock.target is None
    assert context.suggest_next_action(after) is None
    assert "commit" not in context.completed
