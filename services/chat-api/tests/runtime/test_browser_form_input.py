from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from app.enterprise_capabilities.browser.engine.drivers.base import BrowserDriver
from app.enterprise_capabilities.browser.engine.drivers.form_input import FormInputDriver
from app.enterprise_capabilities.browser.engine.drivers.skill import SkillDriver
from app.enterprise_capabilities.browser.engine.form_input import (
    BrowserInputContext,
    FieldBinding,
    InputCandidate,
    discover_fields,
    is_ready_business_form,
    resolve_deterministic,
)
from app.enterprise_capabilities.browser.engine.form_input.contracts import FieldDescriptor
from app.enterprise_capabilities.browser.engine.form_input.media_activation import resolve_media_activation
from app.enterprise_capabilities.browser.engine.form_input.media_editor import (
    media_editor_candidate_payload,
    resolve_media_editor_ref,
)
from app.enterprise_capabilities.browser.engine.form_input.media_paste import (
    normalize_media_paste_decision,
    resolve_requested_media_paste,
)
from app.enterprise_capabilities.browser.engine.form_input.media_upload_normalization import (
    normalize_media_upload_decision,
)
from app.enterprise_capabilities.browser.engine.form_input.model_fallback import _ModelBinding, _validated_bindings
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord


class _Fallback(BrowserDriver):
    def __init__(self, decision: Optional[Decision] = None) -> None:
        self.completed = 0
        self.decision = decision or Decision(tool="browser_observe", rationale="fallback")
        self.last_state_ledger: Optional[Dict[str, Any]] = None

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
        del goal, history, observation
        self.last_state_ledger = state_ledger
        return self.decision

    def on_step_completed(self, decision, ok, observation_after) -> None:
        del decision, ok, observation_after
        self.completed += 1


class _SequenceFallback(_Fallback):
    def __init__(self, decisions: List[Decision]) -> None:
        super().__init__()
        self.decisions = list(decisions)
        self.state_ledgers: List[Optional[Dict[str, Any]]] = []
        self.histories: List[List[StepRecord]] = []

    async def next_step(
        self,
        goal: str,
        history: List[StepRecord],
        observation: Observation,
        state_ledger: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        del goal, observation
        self.last_state_ledger = state_ledger
        self.state_ledgers.append(state_ledger)
        self.histories.append(list(history))
        if not self.decisions:
            return Decision(tool="browser_observe", rationale="sequence exhausted")
        return self.decisions.pop(0)


class _Resolver:
    def __init__(self, bindings: List[FieldBinding]) -> None:
        self.bindings = bindings
        self.calls = 0
        self.fields = []

    async def resolve(self, **kwargs) -> List[FieldBinding]:
        self.calls += 1
        self.fields = list(kwargs.get("fields") or [])
        return self.bindings


def _observation(*elements: Dict[str, Any]) -> Observation:
    return Observation(
        url="https://example.test/create",
        title="Create",
        elements=list(elements),
        auth={"state": "authenticated"},
    )


def _confirmed_upload(observation: Observation) -> Observation:
    observation.diagnostics = {
        "upload": {
            "status": "confirmed",
            "mediaCountBefore": 0,
            "mediaCountAfter": 1,
            "pendingCountAfter": 0,
        },
    }
    return observation


def _confirmed_paste(observation: Observation) -> Observation:
    observation.diagnostics = {
        "mediaInsert": {
            "status": "confirmed",
            "method": "paste",
            "mediaCountBefore": 0,
            "mediaCountAfter": 1,
            "pendingCountAfter": 0,
        },
    }
    return observation


def test_discovers_generic_form_metadata() -> None:
    fields = discover_fields(_observation(
        {
            "ref": "e1", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "required": True, "value": "",
        },
        {
            "ref": "e2", "role": "textbox", "name": "附件", "tag": "input",
            "type": "file", "accept": ".pdf", "visible": False,
        },
    ))

    assert [field.control_kind for field in fields] == ["rich_text", "file"]
    assert fields[0].required is True


def test_dynamic_placeholder_and_value_do_not_change_field_identity() -> None:
    before = discover_fields(_observation({
        "ref": "e11", "role": "combobox", "name": "\u200b", "tag": "input",
        "type": "text", "selector": "#search", "placeholder": "今日热榜一",
        "editable": True, "searchContext": True, "value": "",
    }))[0]
    after = discover_fields(_observation({
        "ref": "e4", "role": "combobox", "name": "员工服务台", "tag": "input",
        "type": "text", "selector": "#search", "placeholder": "今日热榜二",
        "editable": True, "searchContext": True, "value": "员工服务台",
    }))[0]

    assert before.field_key == after.field_key == "selector:0:#search"
    assert before.label == "input"
    assert before.placeholder == "今日热榜一"
    assert before.control_kind == "text"


def test_editable_combobox_in_search_context_is_not_a_business_form() -> None:
    observation = _observation({
        "ref": "e1", "role": "combobox", "name": "", "tag": "input",
        "type": "text", "selector": "#search", "placeholder": "动态热点",
        "editable": True, "searchContext": True, "value": "",
    })
    fields = discover_fields(observation)

    assert fields[0].control_kind == "text"
    assert is_ready_business_form(observation, fields) is False


def test_deterministic_binding_uses_semantics_not_longest_string() -> None:
    fields = discover_fields(_observation(
        {"ref": "e1", "role": "textbox", "name": "收件人", "tag": "input", "value": ""},
        {"ref": "e2", "role": "textbox", "name": "正文", "tag": "textarea", "value": ""},
    ))
    context = BrowserInputContext(
        original_request="发送报告给 owner@example.com",
        candidates=[
            InputCandidate("email", "user_input", "request.email", "recipient_email", "owner@example.com"),
            InputCandidate("report", "upstream", "artifacts.report.article_markdown", "article_markdown", "短报告"),
            InputCandidate("irrelevant", "upstream", "artifacts.search.raw_dump", "raw_dump", "无关" * 5000),
        ],
    )

    resolved, unresolved = resolve_deterministic(fields, context)

    assert not unresolved
    assert resolved[fields[0].field_key].value == "owner@example.com"
    assert resolved[fields[1].field_key].value == "短报告"


def test_publish_input_context_resolves_payload_from_transitive_ancestor() -> None:
    article_payload = {
        "schema_version": "1.0",
        "title": "权威标题",
        "body_plain_text": "权威正文",
        "body_html": "<p>权威正文</p>",
        "media": [],
    }
    unrelated_payload = {
        "schema_version": "1.0",
        "title": "其他分支标题",
        "body_plain_text": "其他分支正文",
        "media": [],
    }
    node = SimpleNamespace(
        node_id="N_PUBLISH",
        depends_on=["N_VISUALS"],
        meta={"capability_id": "browser.publish"},
    )

    context = BrowserInputContext.from_runtime(
        original_request="发布文章",
        node=node,
        output_spec={
            "current_task_node_id": "N_PUBLISH",
            "current_task_node_meta": {"capability_id": "browser.publish"},
            "graph_topology": [
                {
                    "node_id": "N_ARTICLE",
                    "capability_id": "generation.compose_article",
                    "depends_on": [],
                },
                {
                    "node_id": "N_VISUALS",
                    "capability_id": "planning.visual_semantics",
                    "depends_on": ["N_ARTICLE"],
                },
                {
                    "node_id": "N_PUBLISH",
                    "capability_id": "browser.publish",
                    "depends_on": ["N_VISUALS"],
                },
                {
                    "node_id": "N_UNRELATED",
                    "capability_id": "generation.compose_article",
                    "depends_on": [],
                },
            ],
            "graph_artifacts": {
                "N_ARTICLE": {"publish_payload": article_payload},
                "N_VISUALS": {"visual_semantics": {"count": 2}},
                "N_UNRELATED": {"publish_payload": unrelated_payload},
            },
            "predecessor_artifacts": {
                "N_VISUALS": {"visual_semantics": {"count": 2}},
            },
        },
    )

    candidates = {item.semantic_name: item for item in context.candidates}
    assert candidates["title"].value == "权威标题"
    assert candidates["body"].value == "权威正文"
    assert candidates["body"].rich_html == "<p>权威正文</p>"
    assert all("N_UNRELATED" not in item.source_path for item in context.candidates)


def test_non_publish_input_context_does_not_pull_transitive_publish_payload() -> None:
    node = SimpleNamespace(
        node_id="N_BROWSE",
        depends_on=["N_VISUALS"],
        meta={"capability_id": "browser.browse"},
    )

    context = BrowserInputContext.from_runtime(
        original_request="浏览页面",
        node=node,
        output_spec={
            "graph_topology": [
                {"node_id": "N_ARTICLE", "depends_on": []},
                {"node_id": "N_VISUALS", "depends_on": ["N_ARTICLE"]},
                {"node_id": "N_BROWSE", "depends_on": ["N_VISUALS"]},
            ],
            "graph_artifacts": {
                "N_ARTICLE": {
                    "publish_payload": {
                        "schema_version": "1.0",
                        "title": "不应注入",
                        "body_plain_text": "不应注入",
                    }
                },
                "N_VISUALS": {"visual_semantics": {"count": 2}},
            },
        },
    )

    assert all(
        item.semantic_name not in {"title", "body"}
        for item in context.candidates
    )


def test_runtime_input_context_preserves_same_file_at_distinct_media_anchors() -> None:
    context = BrowserInputContext.from_runtime(
        original_request="按指定位置插入两张配图",
        node=SimpleNamespace(
            node_id="publish",
            depends_on=["article"],
            meta={"capability_id": "browser.publish"},
        ),
        output_spec={
            "current_task_node_id": "publish",
            "current_task_node_meta": {"capability_id": "browser.publish"},
            "graph_topology": [
                {"node_id": "article", "depends_on": []},
                {"node_id": "publish", "depends_on": ["article"]},
            ],
            "graph_artifacts": {
                "article": {
                    "publish_payload": {
                        "schema_version": "1.0",
                        "title": "标题",
                        "body_plain_text": "第一段第二段",
                        "media": [
                            {
                                "source_url": "https://assets.example.test/shared.png",
                                "anchor_after_text": "第一段",
                                "anchor_plain_offset": 3,
                                "order": 0,
                            },
                            {
                                "source_url": "https://assets.example.test/shared.png",
                                "anchor_after_text": "第二段",
                                "anchor_plain_offset": 6,
                                "order": 1,
                            },
                        ],
                    },
                    "images": ["https://assets.example.test/shared.png"],
                },
            },
        },
    )

    files = [item for item in context.candidates if item.value_kind == "file"]
    assert len(files) == 2
    assert {
        item.metadata["media_anchor"]["after_text"]
        for item in files
    } == {"第一段", "第二段"}


def test_form_driver_fills_one_live_field_then_delegates() -> None:
    observation = _observation(
        {"ref": "e1", "role": "textbox", "name": "备注", "tag": "textarea", "required": True, "value": ""},
    )
    field_key = discover_fields(observation)[0].field_key
    resolver = _Resolver([FieldBinding(
        field_key=field_key,
        action="fill",
        source_kind="transform",
        value="页面所需的简短备注",
        confidence=0.95,
        rationale="根据原始请求生成页面级短适配",
    )])
    fallback = _Fallback()
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(original_request="提交申请", candidates=[]),
        capability_id="browser.submit",
        model_resolver=resolver,
    )

    decision = asyncio.run(driver.next_step("提交申请", [], observation))

    assert decision.tool == "browser_fill"
    assert decision.args == {"ref": "e1", "value": "页面所需的简短备注"}
    driver.on_step_completed(decision, True, _observation(
        {"ref": "e1", "role": "textbox", "name": "备注", "tag": "textarea", "required": True, "value": "页面所需的简短备注"},
    ))
    delegated = asyncio.run(driver.next_step("提交申请", [], _observation(
        {"ref": "e1", "role": "textbox", "name": "备注", "tag": "textarea", "required": True, "value": "页面所需的简短备注"},
    )))
    assert delegated.tool == "browser_observe"
    assert resolver.calls == 1


def test_rejected_fill_discards_snapshot_binding_and_rebinds_latest_ref() -> None:
    def state(ref: str) -> Observation:
        return _observation({
            "ref": ref,
            "role": "textbox",
            "name": "备注",
            "tag": "textarea",
            "selector": "#request-note",
            "editable": True,
            "required": True,
            "value": "",
        })

    initial = state("note-old")
    field_key = discover_fields(initial)[0].field_key
    resolver = _Resolver([FieldBinding(
        field_key=field_key,
        action="fill",
        source_kind="transform",
        value="重新绑定后的内容",
        confidence=0.95,
        rationale="resolve the current live note field",
    )])
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="填写备注后提交",
            candidates=[],
        ),
        capability_id="browser.submit",
        model_resolver=resolver,
    )

    stale = asyncio.run(driver.next_step("填写备注后提交", [], initial))
    driver.on_decision_rejected(
        stale,
        initial,
        category="scope_target_unresolved",
        reason="target disappeared before dispatch",
    )
    rebound = asyncio.run(
        driver.next_step("填写备注后提交", [], state("note-new")),
    )

    assert stale.args["ref"] == "note-old"
    assert rebound.tool == "browser_fill"
    assert rebound.args["ref"] == "note-new"
    assert resolver.calls == 2


def test_form_driver_refreshes_then_clicks_unique_enabled_commit_control() -> None:
    scope = "0:body > dialog > footer"
    scope_selector = "body > dialog > footer"

    def state(comment_ref: str, send_ref: str, *, value: str, disabled: bool) -> Observation:
        common = {
            "scopeId": scope,
            "scopeSelector": scope_selector,
            "scopeLockable": True,
            "scopeText": "发送",
            "frameDepth": 0,
            "visible": True,
            "hitTestable": True,
        }
        return _observation(
            {
                **common, "ref": comment_ref, "role": "textbox", "name": "评论",
                "tag": "textarea", "selector": "#comment", "editable": True,
                "multiline": True, "focused": True, "value": value,
            },
            {
                **common, "ref": send_ref, "role": "button", "name": "发送",
                "tag": "button", "selector": "#send", "disabled": disabled,
            },
            {
                **common, "ref": "cancel", "role": "button", "name": "取消",
                "tag": "button", "selector": "#cancel", "disabled": False,
            },
            {
                **common, "ref": "next", "role": "button", "name": "Next",
                "tag": "button", "selector": "#next", "disabled": False,
            },
        )

    initial = state("comment-old", "send-old", value="", disabled=True)
    field_key = discover_fields(initial)[0].field_key
    resolver = _Resolver([FieldBinding(
        field_key=field_key,
        action="fill",
        source_kind="transform",
        value="准备发布的评论",
        confidence=0.95,
        rationale="根据任务生成评论",
    )])
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="发表评论", candidates=[]),
        capability_id="browser.publish",
        model_resolver=resolver,
    )

    fill = asyncio.run(driver.next_step("发表评论", [], initial))
    filled = state("comment-old", "send-old", value="准备发布的评论", disabled=True)
    driver.on_step_completed(fill, True, filled)
    refresh = asyncio.run(driver.next_step("发表评论", [], filled))
    refreshed = state("comment-new", "send-new", value="准备发布的评论", disabled=False)
    driver.on_step_completed(refresh, True, refreshed)
    commit = asyncio.run(driver.next_step("发表评论", [], refreshed))

    assert fill.tool == "browser_fill"
    assert refresh.tool == "browser_observe"
    assert commit.tool == "browser_click"
    assert commit.args == {"ref": "send-new"}


def test_fallback_fill_is_adopted_then_committed_in_same_form() -> None:
    scope = "0:body > dialog > footer"
    common = {
        "scopeId": scope,
        "scopeSelector": "body > dialog > footer",
        "scopeLockable": True,
        "scopeText": "发送 取消",
        "frameDepth": 0,
        "visible": True,
        "hitTestable": True,
    }

    def state(*, field_ref: str, send_ref: str, value: str) -> Observation:
        return _observation(
            {
                **common, "ref": field_ref, "role": "textbox", "tag": "div",
                "selector": "#comment", "contentEditable": True, "editable": True,
                "focused": True, "value": value,
            },
            {
                **common, "ref": send_ref, "role": "button", "tag": "button",
                "selector": "#send", "name": "发送", "text": "发送",
            },
            {
                **common, "ref": "cancel", "role": "button", "tag": "button",
                "selector": "#cancel", "name": "取消", "text": "取消",
            },
        )

    initial = state(field_ref="comment-old", send_ref="send-old", value="")
    fallback = _Fallback(Decision(
        tool="browser_fill",
        args={"ref": "comment-old", "value": "LLM 根据当前帖子生成的评论"},
        rationale="fallback model generated current-page comment",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(original_request="发表评论", candidates=[]),
        capability_id="browser.publish",
        model_resolver=_Resolver([]),
    )

    fill = asyncio.run(driver.next_step("发表评论", [], initial))
    filled = state(
        field_ref="comment-old",
        send_ref="send-old",
        value="LLM 根据当前帖子生成的评论",
    )
    driver.on_step_completed(fill, True, filled)
    refresh = asyncio.run(driver.next_step("发表评论", [], filled))
    refreshed = state(
        field_ref="comment-new",
        send_ref="send-new",
        value="LLM 根据当前帖子生成的评论",
    )
    driver.on_step_completed(refresh, True, refreshed)
    commit = asyncio.run(driver.next_step("发表评论", [], refreshed))

    assert fill.tool == "browser_fill"
    assert fallback.completed == 1
    assert refresh.tool == "browser_observe"
    assert commit.tool == "browser_click"
    assert commit.args == {"ref": "send-new"}


def test_unfocused_editor_with_disabled_send_is_adopted_after_fallback_fill() -> None:
    scope = "0:body > dialog > footer"
    common = {
        "scopeId": scope,
        "scopeSelector": "body > dialog > footer",
        "scopeLockable": True,
        "scopeText": "说点什么 发送 取消",
        "frameDepth": 0,
        "visible": True,
        "hitTestable": True,
    }

    def state(
        *,
        field_ref: str,
        send_ref: str,
        value: str,
        send_disabled: bool,
    ) -> Observation:
        return _observation(
            {
                **common, "ref": field_ref, "role": "textbox", "tag": "p",
                "selector": "#comment", "contentEditable": True, "editable": True,
                "focused": False, "value": value,
            },
            {
                **common, "ref": send_ref, "role": "button", "tag": "button",
                "selector": "#send", "name": "发送", "text": "发送",
                "disabled": send_disabled,
                "hitTestable": not send_disabled,
            },
            {
                **common, "ref": "cancel", "role": "button", "tag": "button",
                "selector": "#cancel", "name": "取消", "text": "取消",
                "disabled": False,
            },
        )

    initial = state(
        field_ref="comment-old",
        send_ref="send-old",
        value="",
        send_disabled=True,
    )
    fallback = _Fallback(Decision(
        tool="browser_fill",
        args={"ref": "comment-old", "value": "LLM 生成的评论"},
        rationale="fallback generated a comment",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(original_request="发表评论", candidates=[]),
        capability_id="browser.publish",
        model_resolver=_Resolver([]),
    )

    fill = asyncio.run(driver.next_step("发表评论", [], initial))
    filled_without_dom_refresh = state(
        field_ref="comment-old",
        send_ref="send-old",
        value="LLM 生成的评论",
        send_disabled=True,
    )
    driver.on_step_completed(fill, True, filled_without_dom_refresh)
    refresh = asyncio.run(
        driver.next_step("发表评论", [], filled_without_dom_refresh)
    )
    refreshed = state(
        field_ref="comment-new",
        send_ref="send-new",
        value="LLM 生成的评论",
        send_disabled=False,
    )
    driver.on_step_completed(refresh, True, refreshed)
    commit = asyncio.run(driver.next_step("发表评论", [], refreshed))

    assert fill.tool == "browser_fill"
    assert refresh.tool == "browser_observe"
    assert commit.tool == "browser_click"
    assert commit.args == {"ref": "send-new"}


def test_disabled_cancel_does_not_make_an_editor_a_ready_form() -> None:
    scope = "0:body > dialog > footer"
    common = {
        "scopeId": scope,
        "scopeSelector": "body > dialog > footer",
        "scopeLockable": True,
        "scopeText": "说点什么 取消",
        "frameDepth": 0,
        "visible": True,
        "hitTestable": True,
    }
    observation = _observation(
        {
            **common, "ref": "comment", "role": "textbox", "tag": "p",
            "selector": "#comment", "contentEditable": True, "editable": True,
            "focused": False, "value": "",
        },
        {
            **common, "ref": "cancel", "role": "button", "tag": "button",
            "selector": "#cancel", "name": "取消", "text": "取消",
            "disabled": True,
        },
    )

    assert is_ready_business_form(observation, discover_fields(observation)) is False


def test_fallback_search_fill_is_not_adopted_as_business_form_mutation() -> None:
    observation = _observation({
        "ref": "search", "role": "searchbox", "tag": "textarea",
        "selector": "#search", "editable": True, "visible": True,
        "searchContext": True, "value": "",
    })
    fallback = _Fallback(Decision(
        tool="browser_fill",
        args={"ref": "search", "value": "工单系统"},
        rationale="search",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(original_request="搜索工单系统", candidates=[]),
        capability_id="browser.publish",
        model_resolver=_Resolver([]),
    )

    fill = asyncio.run(driver.next_step("搜索后发表评论", [], observation))
    filled = _observation({
        "ref": "search", "role": "searchbox", "tag": "textarea",
        "selector": "#search", "editable": True, "visible": True,
        "searchContext": True, "value": "工单系统",
    })
    driver.on_step_completed(fill, True, filled)
    next_decision = asyncio.run(driver.next_step("搜索后发表评论", [], filled))

    assert next_decision.tool == "browser_fill"
    assert not driver._mutated_field_keys


def test_unverified_fallback_fill_is_not_adopted() -> None:
    scope = "0:#comment-form"
    common = {
        "scopeId": scope, "scopeSelector": "#comment-form", "scopeLockable": True,
        "scopeText": "发送", "visible": True, "hitTestable": True,
    }
    initial = _observation(
        {
            **common, "ref": "comment", "role": "textbox", "tag": "textarea",
            "selector": "#comment", "editable": True, "value": "",
        },
        {
            **common, "ref": "send", "role": "button", "tag": "button",
            "selector": "#send", "name": "发送",
        },
    )
    fallback = _Fallback(Decision(
        tool="browser_fill",
        args={"ref": "comment", "value": "应写入的评论"},
        rationale="fallback fill",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(original_request="发表评论", candidates=[]),
        capability_id="browser.publish",
        model_resolver=_Resolver([]),
    )

    fill = asyncio.run(driver.next_step("发表评论", [], initial))
    driver.on_step_completed(fill, True, initial)

    assert not driver._mutated_field_keys


def test_read_capability_never_invokes_form_resolution() -> None:
    observation = _observation(
        {"ref": "e1", "role": "textbox", "name": "搜索", "tag": "input", "value": ""},
    )
    resolver = _Resolver([])
    fallback = _Fallback()
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(original_request="查询数据", candidates=[]),
        capability_id="browser.read",
        model_resolver=resolver,
    )

    decision = asyncio.run(driver.next_step("查询数据", [], observation))
    driver.on_step_completed(decision, True, observation)

    assert decision.tool == "browser_observe"
    assert resolver.calls == 0
    assert fallback.completed == 1


def test_incidental_editor_on_search_results_does_not_consume_upstream_content() -> None:
    observation = Observation(
        url="https://example.test/search?q=workflow",
        title="Search results",
        elements=[
            {"ref": "e1", "role": "searchbox", "name": "搜索", "tag": "input", "visible": True, "value": "workflow"},
            {
                "ref": "e2", "role": "textbox", "name": "", "tag": "div",
                "contentEditable": True, "editable": True, "visible": True, "value": "",
            },
            {"ref": "e3", "role": "link", "name": "查看结果", "visible": True},
        ],
        auth={"state": "authenticated"},
    )
    resolver = _Resolver([])
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="查找合适的问题后回复",
            candidates=[InputCandidate("report", "upstream", "artifacts.summary.report_markdown", "report_markdown", "上游总结")],
        ),
        capability_id="browser.publish",
        model_resolver=resolver,
    )

    decision = asyncio.run(driver.next_step("查找合适的问题后回复", [], observation))

    assert decision.tool == "browser_observe"
    assert resolver.calls == 0


def test_commit_action_from_another_scope_does_not_make_editor_ready() -> None:
    observation = _observation(
        {
            "ref": "e1", "role": "textbox", "tag": "div", "contentEditable": True,
            "editable": True, "visible": True, "scopeId": "0:#assistant",
            "scopeRole": "section", "value": "",
        },
        {
            "ref": "e2", "role": "button", "name": "添加评论", "visible": True,
            "scopeId": "0:#result-1", "scopeRole": "listitem",
        },
    )

    assert is_ready_business_form(observation, discover_fields(observation)) is False


def test_coherent_incidental_form_on_collection_surface_does_not_preempt_exploration() -> None:
    observation = Observation(
        url="https://example.test/search?q=workflow",
        title="Search results",
        elements=[
            {
                "ref": "e1", "role": "searchbox", "name": "搜索", "tag": "input",
                "editable": True, "visible": True, "value": "workflow", "scopeId": "0:#header",
            },
            {
                "ref": "e2", "role": "textbox", "tag": "div", "contentEditable": True,
                "editable": True, "visible": True, "value": "", "scopeId": "0:#assistant",
                "scopeRole": "section", "scopeName": "快速问答",
            },
            {
                "ref": "e3", "role": "combobox", "tag": "select", "visible": True,
                "options": ["中文", "English"], "scopeId": "0:#assistant",
                "scopeRole": "section", "scopeName": "快速问答",
            },
            {
                "ref": "e4", "role": "button", "name": "提交问题", "visible": True,
                "scopeId": "0:#assistant", "scopeRole": "section",
            },
            *[
                {
                    "ref": f"r{index}", "role": "listitem", "name": f"结果 {index}",
                    "visible": True, "scopeId": f"0:#result-{index}", "scopeRole": "listitem",
                }
                for index in range(3)
            ],
        ],
        auth={"state": "authenticated"},
    )
    resolver = _Resolver([])
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="选择合适结果后发表评论", candidates=[]),
        capability_id="browser.publish",
        model_resolver=resolver,
    )

    decision = asyncio.run(driver.next_step("选择合适结果后发表评论", [], observation))

    assert decision.tool == "browser_observe"
    assert resolver.calls == 0


def test_click_that_opens_inline_form_activates_only_its_scope() -> None:
    before = Observation(
        url="https://example.test/search?q=workflow",
        title="Search results",
        elements=[
            {
                "ref": "s1", "role": "searchbox", "name": "搜索", "tag": "input",
                "editable": True, "visible": True, "value": "workflow", "scopeId": "0:#header",
            },
            {
                "ref": "open", "role": "button", "name": "添加评论", "visible": True,
                "scopeId": "0:#result-1", "scopeRole": "listitem",
            },
            *[
                {
                    "ref": f"r{index}", "role": "listitem", "name": f"结果 {index}",
                    "visible": True, "scopeId": f"0:#result-{index}", "scopeRole": "listitem",
                }
                for index in range(3)
            ],
        ],
        auth={"state": "authenticated"},
    )
    after = Observation(
        url=before.url,
        title=before.title,
        elements=[
            *before.elements,
            {
                "ref": "body", "role": "textbox", "tag": "div", "contentEditable": True,
                "editable": True, "visible": True, "value": "", "scopeId": "0:#result-1",
                "scopeRole": "listitem",
            },
            {
                "ref": "submit", "role": "button", "name": "发布评论", "visible": True,
                "scopeId": "0:#result-1", "scopeRole": "listitem",
            },
        ],
        auth={"state": "authenticated"},
    )
    content_field = next(field for field in discover_fields(after) if field.ref == "body")
    resolver = _Resolver([FieldBinding(
        field_key=content_field.field_key,
        action="fill",
        source_kind="transform",
        value="已打开目标结果对应的评论内容",
        confidence=0.95,
    )])
    click = Decision(tool="browser_click", args={"ref": "open"}, rationale="open inline form")
    driver = FormInputDriver(
        fallback=_Fallback(click),
        input_context=BrowserInputContext(original_request="选择合适结果后发表评论", candidates=[]),
        capability_id="browser.publish",
        model_resolver=resolver,
    )

    first = asyncio.run(driver.next_step("选择合适结果后发表评论", [], before))
    driver.on_step_completed(first, True, after)
    second = asyncio.run(driver.next_step("选择合适结果后发表评论", [], after))

    assert first.tool == "browser_click"
    assert second.tool == "browser_fill"
    assert second.args == {"ref": "body", "value": "已打开目标结果对应的评论内容"}


def test_inline_form_activation_is_rebuilt_from_history_after_resume() -> None:
    before = Observation(
        url="https://example.test/search?q=workflow",
        title="Search results",
        elements=[
            {
                "ref": "search", "role": "searchbox", "name": "搜索", "tag": "input",
                "editable": True, "visible": True, "scopeId": "0:#header",
            },
            {
                "ref": "open", "role": "button", "name": "添加评论", "visible": True,
                "scopeId": "0:#result-1", "scopeRole": "listitem",
            },
            *[
                {"ref": f"r{i}", "role": "listitem", "name": f"结果 {i}", "visible": True}
                for i in range(3)
            ],
        ],
        auth={"state": "authenticated"},
    )
    after = Observation(
        url=before.url,
        title=before.title,
        elements=[
            *before.elements,
            {
                "ref": "body", "role": "textbox", "tag": "div", "contentEditable": True,
                "editable": True, "visible": True, "scopeId": "0:#result-1",
                "scopeRole": "listitem",
            },
            {
                "ref": "submit", "role": "button", "name": "发布评论", "visible": True,
                "scopeId": "0:#result-1", "scopeRole": "listitem",
            },
        ],
        auth={"state": "authenticated"},
    )
    field = next(item for item in discover_fields(after) if item.ref == "body")
    resolver = _Resolver([FieldBinding(
        field_key=field.field_key,
        action="fill",
        source_kind="transform",
        value="恢复后继续填写",
        confidence=0.95,
    )])
    history = [
        StepRecord(before, Decision(tool="browser_observe"), True),
        StepRecord(after, Decision(tool="browser_click", args={"ref": "open"}), True),
    ]
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="选择合适结果后发表评论", candidates=[]),
        capability_id="browser.publish",
        model_resolver=resolver,
    )

    decision = asyncio.run(driver.next_step("选择合适结果后发表评论", history, after))

    assert decision.tool == "browser_fill"
    assert decision.args == {"ref": "body", "value": "恢复后继续填写"}


def test_single_rich_text_editor_with_commit_action_is_ready() -> None:
    observation = Observation(
        url="https://example.test/topic/1",
        title="Topic",
        elements=[
            {
                "ref": "e1", "role": "textbox", "name": "", "tag": "div",
                "contentEditable": True, "editable": True, "visible": True, "value": "",
            },
            {"ref": "e2", "role": "button", "name": "发布回复", "visible": True},
        ],
        auth={"state": "authenticated"},
    )
    field_key = discover_fields(observation)[0].field_key
    resolver = _Resolver([FieldBinding(
        field_key=field_key,
        action="fill",
        source_kind="transform",
        value="页面级回复",
        confidence=0.9,
    )])
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="发布回复", candidates=[]),
        capability_id="browser.publish",
        model_resolver=resolver,
    )

    decision = asyncio.run(driver.next_step("发布回复", [], observation))

    assert decision.tool == "browser_fill"
    assert decision.args == {"ref": "e1", "value": "页面级回复"}


def test_focused_rich_editor_uses_structural_commit_evidence_before_button_is_enabled() -> None:
    observation = Observation(
        url="https://example.test/topic/1",
        title="Comments",
        elements=[
            {
                "ref": "container", "role": "", "tag": "div", "visible": True,
                "name": "暂无评论 理性发言 发布",
                "scopeId": "0:body > div:nth-of-type(5) > div",
                "scopeLockable": False,
            },
            {
                "ref": "body", "role": "textbox", "tag": "div",
                "contentEditable": True, "editable": True, "focused": True,
                "visible": True, "value": "",
                "scopeId": "0:body > div:nth-of-type(5) > div > div > div",
                "scopeRole": "div", "scopeLockable": True,
                "scopeText": "理性发言，友善互动 同时发布到想法 发布",
            },
            {
                "ref": "image", "role": "textbox", "tag": "input", "type": "file",
                "editable": True, "visible": False, "value": "",
                "scopeId": "0:body > div:nth-of-type(5) > div > div > div",
                "scopeRole": "div", "scopeLockable": True,
                "scopeText": "理性发言，友善互动 同时发布到想法 发布",
            },
        ],
        auth={"state": "authenticated"},
    )
    content_field = next(field for field in discover_fields(observation) if field.ref == "body")
    resolver = _Resolver([FieldBinding(
        field_key=content_field.field_key,
        action="fill",
        source_kind="transform",
        value="基于当前内容生成的简短评论",
        confidence=0.95,
    )])
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="撰写简短评论并发布", candidates=[]),
        capability_id="browser.publish",
        model_resolver=resolver,
    )

    decision = asyncio.run(driver.next_step("撰写简短评论并发布", [], observation))

    assert decision.tool == "browser_fill"
    assert decision.args == {"ref": "body", "value": "基于当前内容生成的简短评论"}
    assert [field.ref for field in resolver.fields] == ["body"]


def test_unfocused_or_broad_scope_text_does_not_activate_rich_editor() -> None:
    observation = _observation({
        "ref": "body", "role": "textbox", "tag": "div",
        "contentEditable": True, "editable": True, "focused": False,
        "visible": True, "value": "", "scopeId": "0:body",
        "scopeLockable": False, "scopeText": "页面其他区域包含发布文字",
    })

    assert is_ready_business_form(observation, discover_fields(observation)) is False


def test_optional_hidden_file_inputs_do_not_interrupt_visible_content_entry() -> None:
    observation = _observation(
        {
            "ref": "e1", "role": "textbox", "name": "", "tag": "div",
            "contentEditable": True, "editable": True, "value": "",
        },
        {
            "ref": "e2", "role": "textbox", "name": "", "tag": "input",
            "type": "file", "visible": False, "value": "",
        },
        {
            "ref": "e3", "role": "textbox", "name": "", "tag": "input",
            "type": "file", "visible": False, "value": "",
        },
        {"ref": "e4", "role": "button", "name": "提交", "visible": True},
    )
    content_field = discover_fields(observation)[0]
    resolver = _Resolver([FieldBinding(
        field_key=content_field.field_key,
        action="fill",
        source_kind="transform",
        value="根据任务生成的短内容",
        confidence=0.95,
    )])
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="撰写一段简短内容并提交",
            candidates=[],
        ),
        capability_id="browser.publish",
        model_resolver=resolver,
    )

    decision = asyncio.run(driver.next_step("撰写并提交", [], observation))

    assert decision.tool == "browser_fill"
    assert decision.args["ref"] == "e1"
    assert [field.control_kind for field in resolver.fields] == ["rich_text"]


def test_unresolved_content_field_delegates_to_existing_browser_planner() -> None:
    observation = _observation(
        {
            "ref": "e9", "role": "textbox", "name": "", "tag": "div",
            "contentEditable": True, "required": True, "value": "",
        },
        {"ref": "e10", "role": "button", "name": "发送", "visible": True},
    )
    fallback = _Fallback(Decision(
        tool="browser_fill",
        args={"ref": "e9", "value": "根据任务与上游证据生成的评论"},
        rationale="planner owns unresolved task-bound content",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="根据上游信息撰写简短评论并发送",
            candidates=[],
        ),
        capability_id="browser.publish",
        model_resolver=_Resolver([]),
    )

    decision = asyncio.run(driver.next_step("撰写评论并发送", [], observation))

    assert decision.tool == "browser_fill"
    assert decision.args["ref"] == "e9"
    assert decision.args["value"] == "根据任务与上游证据生成的评论"


def test_upstream_rich_html_keeps_existing_editor_binding_path() -> None:
    observation = _observation(
        {
            "ref": "editor", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "required": True, "value": "",
        },
        {"ref": "publish", "role": "button", "name": "发布", "visible": True},
    )
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="发布上游生成的文章",
            candidates=[InputCandidate(
                "article-body",
                "upstream",
                "artifacts.writer.publish_payload.body",
                "body",
                "第一段\n第二段",
                value_kind="rich_text",
                plain_text="第一段\n第二段",
                rich_html="<p>第一段</p><p>第二段</p>",
            )],
        ),
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("填写并发布文章", [], observation))

    assert decision.tool == "browser_fill"
    assert decision.args["ref"] == "editor"
    assert decision.args["value"] == "第一段\n第二段"
    assert decision.args["rich_html"] == "<p>第一段</p><p>第二段</p>"


def test_checkpoint_excludes_values_and_dom_refs() -> None:
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="包含敏感正文",
            candidates=[InputCandidate("secret", "user_input", "request", "body", "do-not-persist")],
        ),
        capability_id="browser.publish",
    )
    driver._completed_keys.add("field_semantic_key")
    state = driver.export_checkpoint_state()

    assert "do-not-persist" not in str(state)
    assert "ref" not in str(state)
    assert state["completed_field_keys"] == ["field_semantic_key"]


def test_pending_media_constrains_exploration_to_current_editor_toolbar() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "title", "role": "textbox", "name": "标题", "tag": "input",
            "editable": True, "visible": True, "value": "已填写标题",
            "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "已填写正文", "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "toolbar-image", "role": "button", "name": "", "text": "",
            "tag": "button", "visible": True, "hitTestable": True,
            "inViewport": True, "width": 32, "height": 32,
            "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "toolbar-format", "role": "button", "name": "", "text": "",
            "tag": "button", "visible": True, "hitTestable": True,
            "inViewport": True, "width": 32, "height": 32,
            "scopeId": scope, "scopeLockable": True,
        },
    )
    fallback = _Fallback()
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="将文章和配图写入当前编辑器",
            candidates=[InputCandidate(
                "media-batch", "upstream", "artifacts.publish_payload.media",
                "media", ["https://assets.example.test/one.png", "https://assets.example.test/two.png"],
                value_kind="file",
            )],
        ),
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("填写文章和配图", [], observation))

    assert decision.tool == "browser_observe"
    assert fallback.last_state_ledger is not None
    assert fallback.last_state_ledger["pending_media_count"] == 2
    assert fallback.last_state_ledger["pinned_refs"] == [
        "toolbar-image", "toolbar-format",
    ]
    constraints = " ".join(fallback.last_state_ledger["action_constraints"])
    assert "browser_upload_file" in constraints
    assert "截图中的 ref" in constraints
    assert "https://assets.example.test" not in str(fallback.last_state_ledger)


def test_semantic_image_control_is_activated_before_model_exploration() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "文章正文", "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "image", "role": "button", "name": "Image", "text": "",
            "description": "icon_semantic=image icon_geometry=framed_media",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True, "width": 32, "height": 32,
            "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "document-import", "role": "button", "name": "文档导入",
            "semanticPurpose": "upload", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True, "width": 32, "height": 32,
            "scopeId": scope, "scopeLockable": True,
        },
    )
    fallback = _Fallback()
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="将文章和配图写入当前编辑器",
            candidates=[InputCandidate(
                "media-batch", "upstream", "artifacts.publish_payload.media",
                "media", ["https://assets.example.test/one.png"],
                value_kind="file",
            )],
        ),
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("填写文章和配图", [], observation))

    assert decision.tool == "browser_upload_file"
    assert decision.args == {
        "ref": "image",
        "sources": ["https://assets.example.test/one.png"],
        "editor_ref": "body",
    }
    assert fallback.last_state_ledger is None
    driver.on_step_completed(decision, True, _confirmed_upload(observation))
    delegated = asyncio.run(driver.next_step("填写文章和配图", [], observation))
    assert delegated.tool == "browser_observe"
    assert fallback.last_state_ledger is None
    assert driver.export_checkpoint_state()["completed_candidate_ids"] == [
        "media-batch",
    ]


def test_explicit_copy_paste_request_uses_live_editor_without_clicking_upload() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "第一段图注第二段", "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "image", "role": "button", "name": "图片",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True,
            "scopeId": scope, "scopeLockable": True,
        },
    )
    fallback = _Fallback(Decision(
        tool="browser_click",
        args={"ref": "image"},
        rationale="click the image toolbar control",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="把生成的图片复制粘贴到正文对应位置",
            candidates=[InputCandidate(
                "media-first", "upstream", "publish.media.0", "media",
                ["https://assets.example.test/first.png"],
                value_kind="file",
                metadata={"media_anchor": {
                    "after_text": "第一段",
                    "before_text": "图注",
                    "plain_offset": 3,
                    "order": 0,
                }},
            )],
        ),
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("插入配图", [], observation))

    assert decision.tool == "browser_paste_image"
    assert decision.args == {
        "editor_ref": "body",
        "sources": ["https://assets.example.test/first.png"],
        "anchor": {
            "after_text": "第一段",
            "before_text": "图注",
            "plain_offset": 3,
            "order": 0,
        },
    }
    assert fallback.last_state_ledger is None

    driver.on_step_completed(decision, True, _confirmed_paste(observation))

    assert driver.export_checkpoint_state()["completed_candidate_ids"] == [
        "media-first",
    ]


def test_explicit_copy_paste_request_blocks_upload_control_at_dispatch() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "正文", "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "image", "role": "button", "name": "图片",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True,
            "scopeId": scope, "scopeLockable": True,
        },
    )
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="把配图复制粘贴到编辑器",
            candidates=[InputCandidate(
                "media", "upstream", "publish.media.0", "media",
                ["https://assets.example.test/image.png"],
                value_kind="file",
            )],
        ),
        capability_id="browser.publish",
    )

    guarded = driver.prepare_dispatch(
        Decision(tool="browser_click", args={"ref": "image"}),
        observation,
    )

    assert guarded.tool == "browser_observe"
    assert "browser_paste_image" in guarded.rationale


def test_explicit_copy_paste_request_rejects_model_file_upload() -> None:
    observation = _observation({
        "ref": "file", "role": "button", "name": "图片", "tag": "input",
        "type": "file", "visible": False, "disabled": False,
    })
    fallback = _Fallback(Decision(
        tool="browser_upload_file",
        args={
            "ref": "file",
            "sources": ["https://assets.example.test/model.png"],
        },
        rationale="upload the image",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="把生成的图片复制粘贴进正文",
            candidates=[InputCandidate(
                "media", "upstream", "publish.media.0", "media",
                ["https://assets.example.test/canonical.png"],
                value_kind="file",
            )],
        ),
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("插入图片", [], observation))

    assert decision.tool == "browser_observe"
    assert "browser_paste_image" in decision.rationale


def test_model_paste_uses_canonical_upstream_source() -> None:
    scope = "0:#article-editor"
    observation = _observation({
        "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
        "contentEditable": True, "editable": True, "visible": True,
        "value": "正文", "scopeId": scope, "scopeLockable": True,
    })
    fallback = _Fallback(Decision(
        tool="browser_paste_image",
        args={
            "editor_ref": "body",
            "sources": ["/tmp/model-invented.png"],
        },
        rationale="paste image",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="发布图文内容",
            candidates=[InputCandidate(
                "media", "upstream", "publish.media.0", "media",
                ["https://assets.example.test/canonical.png"],
                value_kind="file",
            )],
        ),
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("插入图片", [], observation))

    assert decision.tool == "browser_paste_image"
    assert decision.args == {
        "editor_ref": "body",
        "sources": ["https://assets.example.test/canonical.png"],
    }


def test_media_paste_prefers_iframe_body_over_contenteditable_title() -> None:
    observation = _observation(
        {
            "ref": "title", "role": "textbox", "name": "标题", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "测试标题", "scopeId": "0:#publish-form",
            "width": 688, "height": 48, "frameDepth": 0,
        },
        {
            "ref": "body", "role": "textbox", "name": "", "tag": "body",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "测试正文", "scopeId": "1:html > body",
            "frameHostScopeIds": ["0:#publish-form"],
            "width": 688, "height": 590, "frameDepth": 1,
        },
        {
            "ref": "assistant", "role": "textbox", "name": "", "tag": "textarea",
            "editable": True, "visible": True, "multiline": True,
            "placeholder": "输入关键词或观点生成内容",
            "value": "", "scopeId": "0:#assistant",
            "width": 290, "height": 22, "frameDepth": 0,
        },
    )

    assert resolve_media_editor_ref(observation, {}) == "body"
    assert [item["ref"] for item in media_editor_candidate_payload(observation)] == [
        "body",
    ]


def test_model_selected_title_is_rebound_to_current_body_editor() -> None:
    observation = _observation(
        {
            "ref": "title", "role": "textbox", "name": "标题", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "测试标题", "width": 688, "height": 48,
        },
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "测试正文", "width": 688, "height": 500,
        },
    )
    context = BrowserInputContext(
        original_request="把下载的图片复制粘贴到正文",
        candidates=[InputCandidate(
            "media", "upstream", "resources.images", "media",
            ["https://assets.example.test/image.png"],
            value_kind="file",
        )],
    )

    resolution = normalize_media_paste_decision(
        decision=Decision(
            tool="browser_paste_image",
            args={"editor_ref": "title"},
            rationale="model selected an editable field",
        ),
        observation=observation,
        context=context,
        completed_candidate_ids=set(),
    )

    assert resolution.decision is not None
    assert resolution.decision.tool == "browser_paste_image"
    assert resolution.decision.args["editor_ref"] == "body"


def test_stale_media_editor_ref_is_rebound_after_dom_refresh() -> None:
    observation = _observation({
        "ref": "body-new", "role": "textbox", "name": "正文", "tag": "div",
        "contentEditable": True, "editable": True, "visible": True,
        "value": "测试正文", "width": 680, "height": 420,
    })
    context = BrowserInputContext(
        original_request="复制图片到正文",
        candidates=[InputCandidate(
            "media", "upstream", "resources.images", "media",
            ["https://assets.example.test/image.png"],
            value_kind="file",
        )],
    )

    resolution = normalize_media_paste_decision(
        decision=Decision(
            tool="browser_paste_image",
            args={"editor_ref": "body-old"},
            rationale="stale model ref",
        ),
        observation=observation,
        context=context,
        completed_candidate_ids=set(),
    )

    assert resolution.decision is not None
    assert resolution.decision.args["editor_ref"] == "body-new"


def test_structured_empty_body_blocks_media_until_body_is_filled() -> None:
    def state(body_value: str) -> Observation:
        return _observation(
            {
                "ref": "title", "role": "textbox", "name": "标题", "tag": "div",
                "contentEditable": True, "editable": True, "visible": True,
                "value": "测试标题", "scopeId": "0:#publish-form",
                "width": 688, "height": 48, "frameDepth": 0,
            },
            {
                "ref": "body", "role": "textbox", "name": "", "tag": "body",
                "contentEditable": True, "editable": True, "visible": True,
                "value": body_value, "scopeId": "1:html > body",
                "frameHostScopeIds": ["0:#publish-form"],
                "width": 688, "height": 590, "frameDepth": 1,
            },
        )

    fallback = _Fallback(Decision(
        tool="browser_paste_image",
        args={"editor_ref": "title"},
        rationale="paste before body input",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="填写标题和正文，再把图片复制粘贴到正文",
            candidates=[InputCandidate(
                "media", "upstream", "resources.images", "media",
                ["https://assets.example.test/image.png"],
                value_kind="file",
            )],
        ),
        capability_id="browser.publish",
    )

    blocked = asyncio.run(driver.next_step("发布图文", [], state("")))
    assert blocked.tool == "browser_observe"
    assert "must be written before" in blocked.rationale
    assert fallback.last_state_ledger is not None
    assert fallback.last_state_ledger["pinned_refs"] == ["body"]

    ready = asyncio.run(driver.next_step("发布图文", [], state("测试正文")))
    assert ready.tool == "browser_paste_image"
    assert ready.args["editor_ref"] == "body"


def test_clipboard_media_batch_is_completed_one_image_at_a_time() -> None:
    observation = _observation({
        "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
        "contentEditable": True, "editable": True, "visible": True,
        "value": "正文", "scopeId": "0:#editor", "scopeLockable": True,
    })
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="将这些图片逐张复制粘贴进正文",
            candidates=[InputCandidate(
                "media-batch", "upstream", "resources.images", "media",
                [
                    "https://assets.example.test/one.png",
                    "https://assets.example.test/two.png",
                ],
                value_kind="file",
            )],
        ),
        capability_id="browser.publish",
    )

    first = asyncio.run(driver.next_step("粘贴图片", [], observation))
    assert first.tool == "browser_paste_image"
    assert first.args["sources"] == ["https://assets.example.test/one.png"]
    driver.on_step_completed(first, True, _confirmed_paste(observation))

    refresh = asyncio.run(driver.next_step("粘贴图片", [], observation))
    assert refresh.tool == "browser_observe"
    driver.on_step_completed(refresh, True, observation)

    second = asyncio.run(driver.next_step("粘贴图片", [], observation))
    assert second.tool == "browser_paste_image"
    assert second.args["sources"] == ["https://assets.example.test/two.png"]
    driver.on_step_completed(second, True, _confirmed_paste(observation))

    assert driver.export_checkpoint_state()["completed_candidate_ids"] == [
        "media-batch",
        "media-batch::paste::0",
        "media-batch::paste::1",
    ]


def test_single_clipboard_image_has_one_completion_identity() -> None:
    observation = _observation({
        "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
        "contentEditable": True, "editable": True, "visible": True,
        "value": "正文", "scopeId": "0:#editor", "scopeLockable": True,
    })
    context = BrowserInputContext(
        original_request="将图片复制粘贴进正文",
        candidates=[InputCandidate(
            "single-media", "upstream", "resources.images", "media",
            ["https://assets.example.test/one.png"],
            value_kind="file",
        )],
    )

    resolution = resolve_requested_media_paste(
        observation=observation,
        context=context,
        completed_candidate_ids=set(),
        attempted_keys=set(),
    )

    assert resolution.candidate_ids == ("single-media",)


def test_editor_upload_requires_confirmed_media_diagnostics_before_completion() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "文章正文", "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "image", "role": "button", "name": "Image",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True, "width": 32, "height": 32,
            "scopeId": scope, "scopeLockable": True,
        },
    )
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="将配图写入当前编辑器",
            candidates=[InputCandidate(
                "media-batch", "upstream", "artifacts.publish_payload.media",
                "media", ["https://assets.example.test/one.png"],
                value_kind="file",
            )],
        ),
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("填写配图", [], observation))
    assert decision.tool == "browser_upload_file"
    assert decision.args["editor_ref"] == "body"

    driver.on_step_completed(decision, True, observation)

    assert driver.export_checkpoint_state()["completed_candidate_ids"] == []


def test_pending_media_promotes_model_image_click_to_upload() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "文章正文", "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "image-one", "role": "button", "name": "Image",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True, "width": 32, "height": 32,
            "x": 100, "y": 20, "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "image-two", "role": "button", "name": "Image",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True, "width": 32, "height": 32,
            "x": 150, "y": 20, "scopeId": scope, "scopeLockable": True,
        },
    )
    fallback = _Fallback(Decision(
        tool="browser_click",
        args={"ref": "image-two"},
        rationale="model selected the second image control",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="将文章和配图写入当前编辑器",
            candidates=[InputCandidate(
                "media-batch", "upstream", "artifacts.publish_payload.media",
                "media", ["https://assets.example.test/one.png"],
                value_kind="file",
            )],
        ),
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("填写文章和配图", [], observation))

    assert decision.tool == "browser_upload_file"
    assert decision.args == {
        "ref": "image-two",
        "sources": ["https://assets.example.test/one.png"],
        "editor_ref": "body",
    }
    driver.on_step_completed(decision, False, observation)

    retry = asyncio.run(driver.next_step("填写文章和配图", [], observation))

    assert retry.tool == "browser_upload_file"
    assert retry.args["ref"] == "image-one"


def test_final_dispatch_promotes_rewritten_media_click_to_upload() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "文章正文", "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "image-one", "role": "button", "name": "Image",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True, "width": 32, "height": 32,
            "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "image-two", "role": "button", "name": "Image",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True, "width": 32, "height": 32,
            "scopeId": scope, "scopeLockable": True,
        },
    )
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="将文章和配图写入当前编辑器",
            candidates=[InputCandidate(
                "media", "upstream", "publish.media.0", "media",
                ["https://assets.example.test/one.png"],
                value_kind="file",
            )],
        ),
        capability_id="browser.publish",
    )

    prepared = driver.prepare_dispatch(
        Decision(
            tool="browser_click",
            args={"ref": "image-two"},
            rationale="executor rewrote a wait into a click",
        ),
        observation,
    )

    assert prepared.tool == "browser_upload_file"
    assert prepared.args["ref"] == "image-two"
    assert prepared.args["sources"] == ["https://assets.example.test/one.png"]


def test_final_dispatch_refreshes_stale_click_while_media_is_pending() -> None:
    observation = _observation({
        "ref": "live", "role": "button", "name": "Image",
        "semanticPurpose": "image", "tag": "button", "visible": True,
        "hitTestable": True, "inViewport": True, "width": 32, "height": 32,
    })
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="插入配图",
            candidates=[InputCandidate(
                "media", "upstream", "publish.media.0", "media",
                ["https://assets.example.test/one.png"],
                value_kind="file",
            )],
        ),
        capability_id="browser.publish",
    )

    prepared = driver.prepare_dispatch(
        Decision(
            tool="browser_click",
            args={"ref": "stale-e9"},
            rationale="model reused an element from the previous revision",
        ),
        observation,
    )

    assert prepared.tool == "browser_observe"
    assert "stale" in prepared.rationale


def test_final_media_dispatch_guard_does_not_change_read_only_browsing() -> None:
    observation = _observation({
        "ref": "image", "role": "button", "name": "Image",
        "semanticPurpose": "image", "tag": "button", "visible": True,
        "hitTestable": True, "inViewport": True, "width": 32, "height": 32,
    })
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="查看这张图片",
            candidates=[InputCandidate(
                "media", "upstream", "artifact.media", "media",
                ["https://assets.example.test/one.png"],
                value_kind="file",
            )],
        ),
        capability_id="browser.browse",
    )
    click = Decision(tool="browser_click", args={"ref": "image"})

    assert driver.prepare_dispatch(click, observation) == click


def test_skill_wrapped_media_click_uses_fallback_transaction_once() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "文章正文", "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "image", "role": "button", "name": "Image", "text": "Image",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True, "width": 32, "height": 32,
            "scopeId": scope, "scopeLockable": True,
        },
    )
    form_driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="将文章和配图写入当前编辑器",
            candidates=[InputCandidate(
                "media", "upstream", "publish.media.0", "media",
                ["https://assets.example.test/one.png"],
                value_kind="file",
            )],
        ),
        capability_id="browser.publish",
    )
    driver = SkillDriver(
        steps=[{
            "instruction": "插入配图",
            "locator": {"role": "button", "text": "Image"},
        }],
        fallback=form_driver,
    )

    scripted = asyncio.run(driver.next_step("发布图文", [], observation))
    prepared = driver.prepare_dispatch(scripted, observation)
    driver.on_step_completed(prepared, True, _confirmed_upload(observation))

    assert scripted.tool == "browser_click"
    assert prepared.tool == "browser_upload_file"
    assert driver.steps_remaining == 0
    assert form_driver.export_checkpoint_state()["completed_candidate_ids"] == [
        "media",
    ]


def test_rejected_skill_target_hands_off_after_bounded_rebinding_attempts() -> None:
    observation = _observation({
        "ref": "old-button",
        "role": "button",
        "name": "继续",
        "text": "继续",
        "visible": True,
    })
    fallback = _Fallback(Decision(
        tool="browser_observe",
        rationale="fallback after rejected recorded target",
    ))
    driver = SkillDriver(
        steps=[{
            "instruction": "继续",
            "locator": {"role": "button", "text": "继续"},
        }],
        fallback=fallback,
    )

    for _ in range(driver._UNRESOLVED_RETRY_BUDGET):
        decision = asyncio.run(driver.next_step("继续流程", [], observation))
        driver.on_decision_rejected(
            decision,
            observation,
            category="scope_target_unresolved",
            reason="target disappeared before dispatch",
        )

    delegated = asyncio.run(driver.next_step("继续流程", [], observation))

    assert driver.script_done is True
    assert delegated.tool == "browser_observe"
    assert delegated.rationale == "fallback after rejected recorded target"


def test_model_upload_is_adopted_with_canonical_source_anchor_and_editor() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "第一段正文图注：图1第二段正文", "scopeId": scope,
            "scopeLockable": True,
        },
        {
            "ref": "image-one", "role": "button", "name": "Image",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True, "width": 32, "height": 32,
            "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "image-two", "role": "button", "name": "Image",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True, "width": 32, "height": 32,
            "scopeId": scope, "scopeLockable": True,
        },
    )
    fallback = _Fallback(Decision(
        tool="browser_upload_file",
        args={
            "ref": "image-two",
            "sources": ["/tmp/model-selected-wrong.png"],
            "anchor": {"after_text": "wrong"},
        },
        rationale="model discovered an ambiguous image toolbar control",
    ))
    media = InputCandidate(
        "media-first", "upstream", "publish.media.0", "media",
        ["https://assets.example.test/first.png"],
        value_kind="file",
        metadata={"media_anchor": {
            "after_text": "第一段正文",
            "before_text": "图注：图1",
            "plain_offset": 5,
            "order": 0,
        }},
    )
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="按正文位置插入配图",
            candidates=[media],
        ),
        capability_id="browser.publish",
    )

    upload = asyncio.run(driver.next_step("插入配图", [], observation))

    assert upload.tool == "browser_upload_file"
    assert upload.args == {
        "ref": "image-two",
        "sources": ["https://assets.example.test/first.png"],
        "editor_ref": "body",
        "anchor": {
            "after_text": "第一段正文",
            "before_text": "图注：图1",
            "plain_offset": 5,
            "order": 0,
        },
    }
    driver.on_step_completed(upload, True, _confirmed_upload(observation))

    duplicate = asyncio.run(driver.next_step("插入配图", [], observation))

    assert duplicate.tool == "browser_observe"
    assert "already uploaded" in duplicate.rationale
    assert driver.export_checkpoint_state()["completed_candidate_ids"] == [
        "media-first",
    ]


def test_anchored_file_input_resolves_editor_across_dom_scopes() -> None:
    editor_scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "title", "role": "textbox", "name": "标题", "tag": "input",
            "editable": True, "visible": True, "value": "标题",
            "scopeId": editor_scope, "scopeLockable": True,
        },
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "前文正文图注：图1后文正文", "scopeId": editor_scope,
            "scopeLockable": True,
        },
        {
            "ref": "file", "role": "textbox", "name": "图片", "tag": "input",
            "type": "file", "visible": False, "disabled": False,
            "scopeId": "0:#global-upload-portal", "scopeLockable": False,
        },
    )
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="按正文位置插入配图",
            candidates=[InputCandidate(
                "media", "upstream", "publish.media.0", "media",
                ["https://assets.example.test/image.png"],
                value_kind="file",
                metadata={"media_anchor": {
                    "after_text": "前文正文",
                    "before_text": "图注：图1",
                    "plain_offset": 4,
                    "order": 0,
                }},
            )],
        ),
        capability_id="browser.publish",
    )

    upload = asyncio.run(driver.next_step("插入配图", [], observation))

    assert upload.tool == "browser_upload_file"
    assert upload.args["ref"] == "file"
    assert upload.args["editor_ref"] == "body"
    assert upload.args["anchor"]["plain_offset"] == 4


def test_anchored_upload_uses_unique_rich_editor_when_snapshot_text_is_truncated() -> None:
    observation = _observation(
        {
            "ref": "title", "role": "textbox", "name": "标题",
            "tag": "input", "editable": True, "visible": True,
            "value": "一个很长但与正文锚点无关的文章标题",
            "scopeId": "0:#editor",
        },
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "快照只保留了正文开头", "scopeId": "0:#editor",
        },
        {
            "ref": "file", "role": "textbox", "name": "图片", "tag": "input",
            "type": "file", "visible": False, "disabled": False,
            "scopeId": "0:#upload-portal",
        },
    )
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="按正文原位置插入配图",
            candidates=[InputCandidate(
                "media", "upstream", "publish.media.0", "media",
                ["https://assets.example.test/image.png"],
                value_kind="file",
                metadata={"media_anchor": {
                    "after_text": "快照中已被截断的较长正文锚点",
                    "before_text": "图注：图1",
                    "plain_offset": 320,
                    "order": 0,
                }},
            )],
        ),
        capability_id="browser.publish",
    )

    upload = asyncio.run(driver.next_step("插入配图", [], observation))

    assert upload.tool == "browser_upload_file"
    assert upload.args["editor_ref"] == "body"
    assert upload.args["anchor"]["plain_offset"] == 320


def test_pending_media_does_not_promote_navigation_card_image_to_upload() -> None:
    observation = _observation(
        {
            "ref": "create", "role": "button", "name": "新的创作",
            "text": "新的创作", "description": "icon_semantic=image",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True, "width": 120, "height": 40,
        },
    )
    fallback = _Fallback(Decision(
        tool="browser_click",
        args={"ref": "create"},
        rationale="open the editor",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="进入编辑器后填写文章和配图",
            candidates=[InputCandidate(
                "media-batch", "upstream", "artifacts.publish_payload.media",
                "media", ["https://assets.example.test/one.png"],
                value_kind="file",
            )],
        ),
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("打开编辑器", [], observation))

    assert decision.tool == "browser_click"
    assert decision.args == {"ref": "create"}


def test_prepare_only_request_does_not_click_final_publish_control() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "文章正文", "scopeId": scope, "scopeLockable": True,
            "scopeText": "文章正文 发布",
        },
        {
            "ref": "publish", "role": "button", "name": "发布", "tag": "button",
            "visible": True, "hitTestable": True, "inViewport": True,
            "scopeId": scope, "scopeLockable": True, "scopeText": "文章正文 发布",
        },
    )
    fallback = _Fallback()
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="填写文章并预览，暂时不要点击最终发布按钮",
            candidates=[],
        ),
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("填写文章并停留预览", [], observation))

    assert decision.tool == "browser_observe"
    assert fallback.last_state_ledger is None


def test_file_input_upload_completes_pending_media_batch() -> None:
    scope = "0:#article-editor"

    def state(*, include_file: bool) -> Observation:
        elements = [
            {
                "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
                "contentEditable": True, "editable": True, "visible": True,
                "value": "文章正文", "scopeId": scope, "scopeLockable": True,
                "scopeText": "文章正文 保存",
            },
            {
                "ref": "save", "role": "button", "name": "保存", "tag": "button",
                "visible": True, "hitTestable": True, "scopeId": scope,
                "scopeLockable": True, "scopeText": "文章正文 保存",
            },
        ]
        if include_file:
            elements.insert(1, {
                "ref": "file", "role": "textbox", "name": "图片", "tag": "input",
                "type": "file", "accept": "image/*", "visible": False,
                "disabled": False, "scopeId": scope, "scopeLockable": True,
                "scopeText": "文章正文 保存",
            })
        return _observation(*elements)

    fallback = _Fallback()
    media = InputCandidate(
        "media-batch", "upstream", "artifacts.publish_payload.media",
        "media", ["https://assets.example.test/one.png", "https://assets.example.test/two.png"],
        value_kind="file",
    )
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="上传文章配图",
            candidates=[media],
        ),
        capability_id="browser.publish",
    )

    with_file = state(include_file=True)
    upload = asyncio.run(driver.next_step("上传文章配图", [], with_file))

    assert upload.tool == "browser_upload_file"
    assert upload.args == {"ref": "file", "sources": list(media.value)}

    driver.on_step_completed(
        upload,
        True,
        _confirmed_upload(state(include_file=False)),
    )
    delegated = asyncio.run(
        driver.next_step("上传文章配图", [], state(include_file=False))
    )

    assert delegated.tool == "browser_observe"
    assert fallback.last_state_ledger is None
    assert driver.export_checkpoint_state()["completed_candidate_ids"] == [
        "media-batch",
    ]


def test_image_upload_rejects_video_input_and_waits_for_expected_body() -> None:
    body_text = "这是生成节点提供的完整文章正文，用于验证正文而不是标题。"
    context = BrowserInputContext(
        original_request="发布图文",
        candidates=[
            InputCandidate(
                "title", "upstream", "publish.title", "title",
                "这是一个足够长但不能代表正文已经写入的标题",
            ),
            InputCandidate(
                "body", "upstream", "publish.body", "body", body_text,
            ),
            InputCandidate(
                "media", "upstream", "publish.media.0", "media",
                ["https://assets.example.test/figure.png"],
                value_kind="file",
            ),
        ],
    )
    title_only = _observation(
        {
            "ref": "title", "role": "textbox", "name": "标题",
            "editable": True, "visible": True,
            "value": "这是一个足够长但不能代表正文已经写入的标题",
        },
        {
            "ref": "video", "role": "textbox", "name": "视频",
            "tag": "input", "type": "file", "accept": "video/*",
            "visible": False, "disabled": False,
        },
        {
            "ref": "image", "role": "textbox", "name": "图片",
            "tag": "input", "type": "file", "accept": "image/*",
            "visible": False, "disabled": False,
        },
    )

    blocked = resolve_media_activation(
        observation=title_only,
        context=context,
        completed_candidate_ids={"title"},
        attempted_keys=set(),
    )

    assert blocked.decision is None

    ready = _observation(
        *title_only.elements,
        {
            "ref": "body", "role": "textbox", "name": "正文",
            "tag": "div", "contentEditable": True, "editable": True,
            "visible": True, "value": body_text,
        },
    )
    resolution = resolve_media_activation(
        observation=ready,
        context=context,
        completed_candidate_ids={"title"},
        attempted_keys=set(),
    )

    assert resolution.decision is not None
    assert resolution.decision.tool == "browser_upload_file"
    assert resolution.decision.args["ref"] == "image"


def test_model_selected_video_input_is_rejected_for_image_candidate() -> None:
    context = BrowserInputContext(
        original_request="上传配图",
        candidates=[InputCandidate(
            "media", "upstream", "publish.media.0", "media",
            ["https://assets.example.test/figure.png"],
            value_kind="file",
        )],
    )
    observation = _observation({
        "ref": "video", "role": "textbox", "name": "视频",
        "tag": "input", "type": "file", "accept": "video/*",
        "visible": False, "disabled": False,
    })

    normalized = normalize_media_upload_decision(
        decision=Decision(
            tool="browser_upload_file",
            args={"ref": "video", "sources": ["wrong.png"]},
        ),
        observation=observation,
        context=context,
        completed_candidate_ids=set(),
    )

    assert normalized.decision is not None
    assert normalized.decision.tool == "browser_observe"
    assert "not a live media control" in normalized.decision.rationale


def test_anchored_media_reuses_one_control_as_independent_transactions() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "第一段第二段", "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "image", "role": "button", "name": "Image",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True, "width": 32, "height": 32,
            "scopeId": scope, "scopeLockable": True,
        },
    )
    first = InputCandidate(
        "media-first", "upstream", "publish.media.0", "media",
        ["https://assets.example.test/first.png"],
        value_kind="file",
        metadata={"media_anchor": {
            "after_text": "第一段", "before_text": "第二段",
            "plain_offset": 3, "order": 0,
        }},
    )
    second = InputCandidate(
        "media-second", "upstream", "publish.media.1", "media",
        ["https://assets.example.test/second.png"],
        value_kind="file",
        metadata={"media_anchor": {
            "after_text": "第二段", "before_text": "",
            "plain_offset": 6, "order": 1,
        }},
    )
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="写入正文并按原位置插入两张配图",
            candidates=[first, second],
        ),
        capability_id="browser.publish",
    )

    later = asyncio.run(driver.next_step("插入配图", [], observation))

    assert later.tool == "browser_upload_file"
    assert later.args == {
        "ref": "image",
        "sources": ["https://assets.example.test/second.png"],
        "editor_ref": "body",
        "anchor": {
            "after_text": "第二段", "before_text": "",
            "plain_offset": 6, "order": 1,
        },
    }
    driver.on_step_completed(later, True, _confirmed_upload(observation))

    refresh = asyncio.run(driver.next_step("插入配图", [], observation))
    assert refresh.tool == "browser_observe"
    driver.on_step_completed(refresh, True, observation)

    earlier = asyncio.run(driver.next_step("插入配图", [], observation))

    assert earlier.tool == "browser_upload_file"
    assert earlier.args == {
        "ref": "image",
        "sources": ["https://assets.example.test/first.png"],
        "editor_ref": "body",
        "anchor": {
            "after_text": "第一段", "before_text": "第二段",
            "plain_offset": 3, "order": 0,
        },
    }
    driver.on_step_completed(earlier, True, _confirmed_upload(observation))
    assert driver.export_checkpoint_state()["completed_candidate_ids"] == [
        "media-first", "media-second",
    ]


def test_anchored_media_can_reuse_one_live_file_input() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "第一段第二段", "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "file", "role": "textbox", "name": "图片", "tag": "input",
            "type": "file", "visible": False, "disabled": False,
            "scopeId": scope, "scopeLockable": True,
        },
    )
    candidates = [
        InputCandidate(
            f"media-{order}", "upstream", f"publish.media.{order}", "media",
            [f"https://assets.example.test/{order}.png"],
            value_kind="file",
            metadata={"media_anchor": {
                "after_text": text,
                "plain_offset": offset,
                "order": order,
            }},
        )
        for order, (text, offset) in enumerate([
            ("第一段", 3),
            ("第二段", 6),
        ])
    ]
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="按正文位置插入两张图",
            candidates=candidates,
        ),
        capability_id="browser.publish",
    )

    second = asyncio.run(driver.next_step("插入配图", [], observation))
    assert second.args["ref"] == "file"
    assert second.args["sources"] == ["https://assets.example.test/1.png"]
    assert second.args["anchor"]["plain_offset"] == 6
    driver.on_step_completed(second, True, _confirmed_upload(observation))

    refresh = asyncio.run(driver.next_step("插入配图", [], observation))
    assert refresh.tool == "browser_observe"
    driver.on_step_completed(refresh, True, observation)

    first = asyncio.run(driver.next_step("插入配图", [], observation))
    assert first.args["ref"] == "file"
    assert first.args["sources"] == ["https://assets.example.test/0.png"]
    assert first.args["anchor"]["plain_offset"] == 3


def test_sequential_media_rebinds_to_the_control_that_previously_uploaded() -> None:
    scope = "0:#article-editor"

    def state(*, first_ref: str) -> Observation:
        return _observation(
            {
                "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
                "contentEditable": True, "editable": True, "visible": True,
                "value": "第一段第二段", "scopeId": scope,
                "scopeLockable": True,
            },
            {
                "ref": first_ref, "role": "button", "name": "Image",
                "semanticPurpose": "image", "tag": "button", "visible": True,
                "hitTestable": True, "inViewport": True, "width": 32,
                "height": 32, "scopeId": scope, "scopeLockable": True,
                "selector": "#editor-toolbar > button:nth-of-type(9)",
            },
            {
                "ref": "other-image", "role": "button", "name": "Image",
                "semanticPurpose": "image", "tag": "button", "visible": True,
                "hitTestable": True, "inViewport": True, "width": 32,
                "height": 32, "scopeId": scope, "scopeLockable": True,
                "selector": "#editor-toolbar > button:nth-of-type(10)",
            },
        )

    candidates = [
        InputCandidate(
            f"media-{order}", "upstream", f"publish.media.{order}", "media",
            [f"https://assets.example.test/{order}.png"],
            value_kind="file",
            metadata={"media_anchor": {
                "after_text": text,
                "plain_offset": offset,
                "order": order,
            }},
        )
        for order, (text, offset) in enumerate([
            ("第一段", 3),
            ("第二段", 6),
        ])
    ]
    fallback = _Fallback(Decision(
        tool="browser_click",
        args={"ref": "working-image"},
        rationale="model selected one of two visually similar controls",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="按正文位置插入两张图",
            candidates=candidates,
        ),
        capability_id="browser.publish",
    )
    before = state(first_ref="working-image")

    first_upload = asyncio.run(driver.next_step("插入配图", [], before))
    assert first_upload.tool == "browser_upload_file"
    assert first_upload.args["ref"] == "working-image"
    driver.on_step_completed(first_upload, True, _confirmed_upload(before))

    after = state(first_ref="working-image-new-ref")
    refresh = asyncio.run(driver.next_step("插入配图", [], after))
    assert refresh.tool == "browser_observe"
    driver.on_step_completed(refresh, True, after)

    second_upload = asyncio.run(driver.next_step("插入配图", [], after))
    assert second_upload.tool == "browser_upload_file"
    assert second_upload.args["ref"] == "working-image-new-ref"


def test_sequential_media_keeps_refresh_barrier_until_observe_succeeds() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "第一段第二段", "scopeId": scope,
            "scopeLockable": True,
        },
        {
            "ref": "image", "role": "button", "name": "Image",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True, "width": 32,
            "height": 32, "scopeId": scope, "scopeLockable": True,
            "selector": "#editor-toolbar > button:nth-of-type(9)",
        },
    )
    candidates = [
        InputCandidate(
            f"media-{order}", "upstream", f"publish.media.{order}", "media",
            [f"https://assets.example.test/{order}.png"],
            value_kind="file",
            metadata={"media_anchor": {
                "after_text": text,
                "plain_offset": offset,
                "order": order,
            }},
        )
        for order, (text, offset) in enumerate([
            ("第一段", 3),
            ("第二段", 6),
        ])
    ]
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="按正文位置插入两张图",
            candidates=candidates,
        ),
        capability_id="browser.publish",
    )

    first_upload = asyncio.run(driver.next_step("插入配图", [], observation))
    driver.on_step_completed(
        first_upload,
        True,
        _confirmed_upload(observation),
    )

    failed_refresh = asyncio.run(driver.next_step("插入配图", [], observation))
    assert failed_refresh.tool == "browser_observe"
    driver.on_step_completed(failed_refresh, False, observation)

    retry_refresh = asyncio.run(driver.next_step("插入配图", [], observation))
    assert retry_refresh.tool == "browser_observe"


def test_completed_media_control_click_is_suppressed_instead_of_opening_picker() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "文章正文", "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "image", "role": "button", "name": "Image",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True, "width": 32, "height": 32,
            "scopeId": scope, "scopeLockable": True,
        },
    )
    fallback = _Fallback(Decision(
        tool="browser_click",
        args={"ref": "image"},
        rationale="model tries to click the image button again",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="插入一张配图",
            candidates=[InputCandidate(
                "media", "upstream", "publish.media.0", "media",
                ["https://assets.example.test/image.png"],
                value_kind="file",
                metadata={"media_anchor": {
                    "after_text": "文章正文", "plain_offset": 4, "order": 0,
                }},
            )],
        ),
        capability_id="browser.publish",
    )
    first = asyncio.run(driver.next_step("插入配图", [], observation))
    driver.on_step_completed(first, True, _confirmed_upload(observation))

    suppressed = asyncio.run(driver.next_step("插入配图", [], observation))

    assert suppressed.tool == "browser_observe"
    assert "already uploaded" in suppressed.rationale


def test_final_commit_is_blocked_while_generated_media_is_pending() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "文章正文", "scopeId": scope, "scopeLockable": True,
        },
        {
            "ref": "publish", "role": "button", "name": "发布",
            "tag": "button", "visible": True, "hitTestable": True,
            "inViewport": True, "scopeId": scope, "scopeLockable": True,
        },
    )
    driver = FormInputDriver(
        fallback=_Fallback(Decision(
            tool="browser_click",
            args={"ref": "publish"},
            rationale="model attempts final publish",
        )),
        input_context=BrowserInputContext(
            original_request="填写图文并发布",
            candidates=[InputCandidate(
                "media", "upstream", "publish.media.0", "media",
                ["https://assets.example.test/image.png"],
                value_kind="file",
                metadata={"media_anchor": {
                    "after_text": "文章正文", "plain_offset": 4, "order": 0,
                }},
            )],
        ),
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("填写图文并发布", [], observation))

    assert decision.tool == "browser_observe"
    assert "media is still pending" in decision.rationale


def test_pending_media_does_not_block_navigation_into_publish_flow() -> None:
    observation = _observation({
        "ref": "publish-entry",
        "role": "button",
        "name": "发布笔记",
        "tag": "button",
        "visible": True,
        "hitTestable": True,
        "inViewport": True,
    })
    fallback = _Fallback(Decision(
        tool="browser_click",
        args={"ref": "publish-entry"},
        rationale="enter the publish workflow",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="进入编辑器并发布图文",
            candidates=[InputCandidate(
                "media", "upstream", "publish.media.0", "media",
                ["https://assets.example.test/image.png"],
                value_kind="file",
            )],
        ),
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("进入编辑器并发布图文", [], observation))

    assert decision.tool == "browser_click"
    assert decision.args == {"ref": "publish-entry"}
    assert fallback.last_state_ledger is None


def test_rejected_outer_publish_is_replanned_to_current_editor_control() -> None:
    scope = "0:#article-editor"

    def state(body_value: str) -> Observation:
        return _observation(
            {
                "ref": "body",
                "selector": "#article-editor > .body",
                "role": "textbox",
                "name": "正文",
                "tag": "div",
                "contentEditable": True,
                "editable": True,
                "required": True,
                "visible": True,
                "value": body_value,
                "scopeId": scope,
                "scopeSelector": "#article-editor",
                "scopeLockable": False,
            },
            {
                "ref": "editor-next",
                "selector": "#article-editor > .toolbar > button",
                "role": "button",
                "name": "继续",
                "tag": "button",
                "visible": True,
                "hitTestable": True,
                "scopeId": scope,
                "scopeSelector": "#article-editor",
                "scopeLockable": False,
            },
            {
                "ref": "outer-publish",
                "selector": "#page-navigation > button",
                "role": "button",
                "name": "发布笔记",
                "tag": "button",
                "visible": True,
                "hitTestable": True,
                "scopeId": "0:#page-navigation",
                "scopeSelector": "#page-navigation",
                "scopeLockable": False,
            },
        )

    fallback = _SequenceFallback([
        Decision(tool="browser_click", args={"ref": "outer-publish"}),
        Decision(tool="browser_click", args={"ref": "outer-publish"}),
        Decision(tool="browser_click", args={"ref": "editor-next"}),
    ])
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="填写正文并完成当前发布流程",
            candidates=[
                InputCandidate(
                    "body-input",
                    "upstream",
                    "publish.body",
                    "body",
                    "文章正文",
                ),
            ],
        ),
        capability_id="browser.publish",
    )
    empty = state("")
    fill = asyncio.run(driver.next_step("发布文章", [], empty))
    assert fill.tool == "browser_fill"

    filled = state("文章正文")
    driver.on_step_completed(fill, True, filled)
    wrong = asyncio.run(driver.next_step("发布文章", [], filled))
    assert wrong.args == {"ref": "outer-publish"}

    guarded = driver.prepare_dispatch(wrong, filled)
    assert guarded.tool == "browser_observe"
    driver.on_step_completed(guarded, True, filled)

    recovered = asyncio.run(driver.next_step("发布文章", [], filled))

    assert recovered.tool == "browser_click"
    assert recovered.args == {"ref": "editor-next"}
    constrained = fallback.state_ledgers[-2]
    retry_constrained = fallback.state_ledgers[-1]
    assert constrained is not None
    assert constrained["pinned_refs"] == ["editor-next"]
    assert "outer-publish" in " ".join(constrained["forbidden_actions"])
    assert retry_constrained is not None
    assert "不得返回同一 ref" in " ".join(retry_constrained["action_constraints"])
    assert fallback.histories[-1][-1].ok is False
    assert driver.prepare_dispatch(recovered, filled) == recovered


def test_missing_commit_control_escalates_only_after_refresh_and_planner_turn() -> None:
    scope = "0:#editor"

    def state(value: str) -> Observation:
        return _observation({
            "ref": "body",
            "selector": "#editor > .body",
            "role": "textbox",
            "name": "正文",
            "tag": "div",
            "contentEditable": True,
            "editable": True,
            "required": True,
            "visible": True,
            "value": value,
            "scopeId": scope,
            "scopeSelector": "#editor",
            "scopeLockable": False,
        })

    fallback = _Fallback(Decision(tool="browser_observe", args={}, rationale="planner correction"))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="填写正文并保存",
            candidates=[InputCandidate(
                "body", "upstream", "publish.body", "body", "测试正文",
            )],
        ),
        capability_id="browser.submit",
    )
    empty = state("")
    fill = asyncio.run(driver.next_step("保存文章", [], empty))
    filled = state("测试正文")
    driver.on_step_completed(fill, True, filled)

    planner_turn = asyncio.run(driver.next_step("保存文章", [], filled))
    assert planner_turn.rationale == "planner correction"
    driver.on_step_completed(planner_turn, True, filled)

    refresh = asyncio.run(driver.next_step("保存文章", [], filled))
    assert refresh.tool == "browser_observe"
    driver.on_step_completed(refresh, True, filled)

    assistance = asyncio.run(driver.next_step("保存文章", [], filled))
    assert assistance.tool == "browser_ask_user"
    assert assistance.args["category"] == "form_commit"


def test_runtime_input_context_does_not_treat_page_url_lists_as_files() -> None:
    context = BrowserInputContext.from_runtime(
        original_request="将生成的图文发布出去",
        node=SimpleNamespace(depends_on=["collect"]),
        output_spec={
            "graph_artifacts": {
                "collect": {
                    "resource_bundle": {
                        "urls": [
                            "https://example.test/article",
                            "https://example.test/case-study",
                        ],
                    },
                    "downloaded_files": [
                        "https://assets.example.test/generated.png",
                    ],
                },
            },
        },
    )

    files = [item for item in context.candidates if item.value_kind == "file"]
    assert len(files) == 1
    assert files[0].semantic_name == "downloaded_files"
    assert files[0].value == ["https://assets.example.test/generated.png"]
    assert all(item.semantic_name != "urls" or item.value_kind != "file"
               for item in context.candidates)


def test_model_binding_cannot_escape_supplied_fields_candidates_or_options() -> None:
    field = FieldDescriptor(
        field_key="field_category",
        ref="e9",
        name="分类",
        control_kind="select",
        options=["产品", "服务"],
    )
    candidate = InputCandidate("in_known", "upstream", "artifacts.kind", "category", "产品")
    bindings = _validated_bindings(
        [
            _ModelBinding(
                field_key="field_category", resolution="selection",
                candidate_id="in_missing", value="产品", confidence=0.9,
            ),
            _ModelBinding(
                field_key="field_unknown", resolution="selection",
                candidate_id="in_known", value="产品", confidence=0.9,
            ),
            _ModelBinding(
                field_key="field_category", resolution="selection",
                candidate_id="in_known", value="不存在的选项", confidence=0.9,
            ),
            _ModelBinding(
                field_key="field_category", resolution="selection",
                candidate_id="in_known", value="产品", confidence=0.9,
            ),
        ],
        field_map={field.field_key: field},
        candidates={candidate.candidate_id: candidate},
    )

    assert len(bindings) == 1
    assert bindings[0].field_key == "field_category"
    assert bindings[0].value == "产品"


def test_model_transform_cannot_rewrite_authoritative_publish_body() -> None:
    field = FieldDescriptor(
        field_key="field_body",
        ref="e12",
        name="正文",
        control_kind="rich_text",
    )
    body = InputCandidate(
        "body",
        "upstream",
        "artifacts.writer.publish_payload.body",
        "body",
        "权威正文",
        value_kind="rich_text",
        plain_text="权威正文",
        rich_html="<p>权威正文</p>",
        metadata={
            "binding_authority": "publish_payload",
            "field_role": "body",
        },
    )
    media = InputCandidate(
        "media",
        "upstream",
        "artifacts.writer.publish_payload.media.0",
        "media",
        ["/tmp/generated.png"],
        value_kind="file",
        metadata={
            "binding_authority": "publish_payload",
            "field_role": "attachment",
        },
    )

    bindings = _validated_bindings(
        [_ModelBinding(
            field_key=field.field_key,
            resolution="transform",
            value='改写正文<img src="/askai-api/api/files/generated.png">',
            confidence=0.8,
            rationale="model rewrote the article",
        )],
        field_map={field.field_key: field},
        candidates={item.candidate_id: item for item in (body, media)},
    )

    assert len(bindings) == 1
    assert bindings[0].source_kind == "upstream"
    assert bindings[0].candidate_id == "body"
    assert bindings[0].value == "权威正文"
    assert bindings[0].rich_html == "<p>权威正文</p>"


def test_page_bound_text_without_publish_authority_can_still_transform() -> None:
    field = FieldDescriptor(
        field_key="field_comment",
        ref="e5",
        name="评论",
        control_kind="multiline",
    )

    bindings = _validated_bindings(
        [_ModelBinding(
            field_key=field.field_key,
            resolution="transform",
            value="这个方案更适合先从高频问题开始落地。",
            confidence=0.9,
            rationale="page-bound comment",
        )],
        field_map={field.field_key: field},
        candidates={},
    )

    assert len(bindings) == 1
    assert bindings[0].source_kind == "transform"
    assert bindings[0].value == "这个方案更适合先从高频问题开始落地。"
