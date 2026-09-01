from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from app.enterprise_capabilities.browser.engine.drivers.base import BrowserDriver
from app.enterprise_capabilities.browser.engine.drivers.form_input import FormInputDriver
from app.enterprise_capabilities.browser.engine.form_input import BrowserInputContext, FieldBinding, discover_fields
from app.enterprise_capabilities.browser.engine.form_input.transaction_identity import (
    FormResourceIdentityTracker,
    resolve_form_resource_identity,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord


class _Fallback(BrowserDriver):
    def __init__(self) -> None:
        self.decision = Decision(tool="browser_observe", args={}, rationale="fallback")

    @property
    def kind(self) -> str:
        return "fake"

    async def next_step(
        self,
        goal: str,
        history: List[StepRecord],
        observation: Observation,
        state_ledger: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        del goal, history, observation, state_ledger
        return self.decision


class _Resolver:
    def __init__(self, field_key: str) -> None:
        self.field_key = field_key

    async def resolve(self, **kwargs: Any) -> List[FieldBinding]:
        del kwargs
        return [FieldBinding(
            field_key=self.field_key,
            action="fill",
            source_kind="transform",
            value="当前内容对应的评论",
            confidence=0.95,
            rationale="generate a concise comment for the current record",
        )]


def _comment_observation(
    *,
    url: str,
    value: str,
    disabled: bool,
    content_id: str = "",
    suffix: str = "",
) -> Observation:
    scope = "0:body > dialog > footer"
    common = {
        "scopeId": scope,
        "scopeSelector": "body > dialog > footer",
        "scopeLockable": True,
        "scopeText": "发表评论 发送",
        "frameDepth": 0,
        "visible": True,
        "hitTestable": True,
    }
    if content_id:
        common.update({
            "contentContextId": content_id,
            "contentContextSource": "dom_attribute",
        })
    return Observation(
        url=url,
        title="Detail",
        auth={"state": "authenticated"},
        elements=[
            {
                **common,
                "ref": f"comment{suffix}",
                "role": "textbox",
                "name": "评论",
                "tag": "textarea",
                "selector": "#comment",
                "editable": True,
                "multiline": True,
                "focused": True,
                "value": value,
            },
            {
                **common,
                "ref": f"send{suffix}",
                "role": "button",
                "name": "发送",
                "tag": "button",
                "selector": "#send",
                "disabled": disabled,
                "hitTestable": not disabled,
            },
        ],
    )


def _driver(initial: Observation) -> FormInputDriver:
    field_key = discover_fields(initial)[0].field_key
    return FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="在多条内容下分别发表评论", candidates=[]),
        capability_id="browser.publish",
        model_resolver=_Resolver(field_key),
    )


def _fill_refresh_commit(
    driver: FormInputDriver,
    *,
    url: str,
    content_id: str = "",
    suffix: str = "",
) -> Decision:
    empty = _comment_observation(
        url=url, value="", disabled=True, content_id=content_id, suffix=suffix,
    )
    fill = asyncio.run(driver.next_step("发表评论", [], empty))
    assert fill.tool == "browser_fill"
    filled = _comment_observation(
        url=url,
        value="当前内容对应的评论",
        disabled=True,
        content_id=content_id,
        suffix=suffix,
    )
    driver.on_step_completed(fill, True, filled)
    refresh = asyncio.run(driver.next_step("发表评论", [], filled))
    assert refresh.tool == "browser_observe"
    refreshed = _comment_observation(
        url=url,
        value="当前内容对应的评论",
        disabled=False,
        content_id=content_id,
        suffix=f"{suffix}-fresh",
    )
    driver.on_step_completed(refresh, True, refreshed)
    commit = asyncio.run(driver.next_step("发表评论", [], refreshed))
    assert commit.tool == "browser_click"
    driver.on_step_completed(commit, True, refreshed)
    return commit


def _open_another_record(driver: FormInputDriver, *, url: str) -> None:
    fallback = driver._fallback
    assert isinstance(fallback, _Fallback)
    fallback.decision = Decision(
        tool="browser_click",
        args={"ref": "next-record"},
        rationale="open another content record",
    )
    collection = Observation(
        url=url,
        title="Results",
        auth={"state": "authenticated"},
        elements=[{
            "ref": "next-record",
            "role": "link",
            "name": "下一条内容",
            "href": url,
            "visible": True,
            "hitTestable": True,
        }],
    )
    decision = asyncio.run(driver.next_step("选择下一条内容", [], collection))
    assert decision.tool == "browser_click"
    driver.on_step_completed(decision, True, collection)
    fallback.decision = Decision(tool="browser_observe", args={}, rationale="fallback")


def test_different_detail_urls_get_independent_form_transactions() -> None:
    first_url = "https://example.test/explore/note-100001?token=first"
    second_url = "https://example.test/explore/note-200002?token=second"
    first = _comment_observation(url=first_url, value="", disabled=True)
    driver = _driver(first)

    first_commit = _fill_refresh_commit(driver, url=first_url, suffix="-one")
    _open_another_record(driver, url=first_url)
    second_commit = _fill_refresh_commit(driver, url=second_url, suffix="-two")

    assert first_commit.args == {"ref": "send-one-fresh"}
    assert second_commit.args == {"ref": "send-two-fresh"}


def test_same_url_dom_content_identity_separates_reused_spa_form() -> None:
    url = "https://example.test/detail"
    first = _comment_observation(
        url=url, value="", disabled=True, content_id="post:record-100001",
    )
    driver = _driver(first)

    first_commit = _fill_refresh_commit(
        driver, url=url, content_id="post:record-100001", suffix="-one",
    )
    _open_another_record(driver, url=url)
    second_commit = _fill_refresh_commit(
        driver, url=url, content_id="post:record-200002", suffix="-two",
    )

    assert first_commit.args == {"ref": "send-one-fresh"}
    assert second_commit.args == {"ref": "send-two-fresh"}


def test_token_change_on_same_record_does_not_reopen_commit_transaction() -> None:
    first_url = "https://example.test/explore/note-100001?access_token=old"
    refreshed_url = "https://example.test/explore/note-100001?access_token=new"
    first = _comment_observation(url=first_url, value="", disabled=True)
    driver = _driver(first)
    _fill_refresh_commit(driver, url=first_url)

    same_record = _comment_observation(
        url=refreshed_url,
        value="",
        disabled=False,
        suffix="-same",
    )
    decision = asyncio.run(driver.next_step("发表评论", [], same_record))

    assert decision.tool != "browser_click"


def test_returning_to_prior_record_preserves_duplicate_commit_guard() -> None:
    first_url = "https://example.test/explore/note-100001"
    second_url = "https://example.test/explore/note-200002"
    driver = _driver(_comment_observation(url=first_url, value="", disabled=True))
    _fill_refresh_commit(driver, url=first_url, suffix="-one")
    _open_another_record(driver, url=first_url)
    _fill_refresh_commit(driver, url=second_url, suffix="-two")
    _open_another_record(driver, url=second_url)

    revisited = _comment_observation(
        url=first_url, value="", disabled=False, suffix="-again",
    )
    decision = asyncio.run(driver.next_step("发表评论", [], revisited))

    assert decision.tool != "browser_click"


def test_post_commit_redirect_does_not_reopen_the_same_form() -> None:
    create_url = "https://example.test/create"
    saved_url = "https://example.test/drafts/record-100001"
    driver = _driver(_comment_observation(url=create_url, value="", disabled=True))
    _fill_refresh_commit(driver, url=create_url)

    redirected = _comment_observation(
        url=saved_url,
        value="",
        disabled=False,
        suffix="-redirected",
    )
    decision = asyncio.run(driver.next_step("发表评论", [], redirected))

    assert decision.tool != "browser_click"


def test_missing_dom_identity_during_rerender_does_not_rotate_strong_context() -> None:
    url = "https://example.test/detail"
    strong = _comment_observation(
        url=url, value="", disabled=True, content_id="post:record-100001",
    )
    weak = _comment_observation(url=url, value="", disabled=True)
    tracker = FormResourceIdentityTracker()

    initial = tracker.observe(resolve_form_resource_identity(strong, discover_fields(strong)))
    transient = tracker.observe(resolve_form_resource_identity(weak, discover_fields(weak)))

    assert initial.changed is False
    assert transient.changed is False
    assert transient.identity.key == initial.identity.key


def test_late_spa_url_upgrades_fallback_identity_without_resetting_state() -> None:
    initial = _comment_observation(
        url="about:blank", value="", disabled=True,
    )
    loaded = _comment_observation(
        url="https://example.test/explore/note-100001",
        value="",
        disabled=True,
    )
    tracker = FormResourceIdentityTracker()

    fallback = tracker.observe(
        resolve_form_resource_identity(initial, discover_fields(initial))
    )
    upgraded = tracker.observe(
        resolve_form_resource_identity(loaded, discover_fields(loaded))
    )

    assert fallback.identity.source == "fallback"
    assert upgraded.identity.source == "url"
    assert upgraded.upgraded is True
    assert upgraded.changed is False
