from __future__ import annotations

import asyncio

from app.enterprise_capabilities.browser.engine.effect_verification.discovery import discover_effect_contract


def test_read_only_search_button_is_not_treated_as_commit() -> None:
    contract = asyncio.run(discover_effect_contract(
        goal=(
            "只使用浏览器搜索员工服务台并读取结果；"
            "不要点赞、收藏、关注、评论、回答或发布任何内容"
        ),
        capability_id="browser_task",
        target={"role": "button", "name": "搜索", "text": "搜索"},
        lang="zh",
        original_request="只读取搜索结果，不要发布任何内容",
    ))

    assert contract.is_commit is False
    assert contract.side_effect == "none"


def test_read_only_browser_capability_never_creates_side_effect_contract() -> None:
    contract = asyncio.run(discover_effect_contract(
        goal="Open the site, search for a phrase, and read the first result",
        capability_id="browser.navigate_and_extract",
        target={"role": "button", "name": "Search", "text": "Search"},
        lang="en",
    ))

    assert contract.is_commit is False
    assert contract.side_effect == "none"


def test_search_control_inside_publish_node_is_not_a_commit() -> None:
    contract = asyncio.run(discover_effect_contract(
        goal="搜索热门帖子，打开详情并发表评论",
        capability_id="browser.publish_or_submit",
        target={"role": "button", "name": "搜索", "text": "搜索"},
        lang="zh",
    ))

    assert contract.is_commit is False
    assert contract.side_effect == "none"
    assert contract.operation_family == "search"


def test_mutating_generic_button_still_uses_model_discovery() -> None:
    class FakeLlm:
        async def ainvoke_structured(self, _messages, schema):
            return schema(
                is_commit=True,
                action_name="执行",
                operation_family="custom_operation",
                side_effect="write",
            )

    contract = asyncio.run(discover_effect_contract(
        goal="在业务系统中执行调拨并确认结果",
        capability_id="browser_task",
        target={"role": "button", "name": "执行", "text": "执行"},
        lang="zh",
        llm=FakeLlm(),
    ))

    assert contract.is_commit is True
    assert contract.operation_family == "custom_operation"


def test_model_commit_survives_missing_derivable_action_name() -> None:
    class PartialLlm:
        async def ainvoke_structured(self, _messages, schema):
            return schema(
                is_commit=True,
                operation_family="save",
                side_effect="write",
                verification_hints=["保存后回查业务对象"],
            )

    contract = asyncio.run(discover_effect_contract(
        goal="填写内容后保存为草稿",
        capability_id="browser.publish_or_submit",
        target={"role": "button", "name": "存草稿", "text": "存草稿"},
        lang="zh",
        llm=PartialLlm(),
    ))

    assert contract.is_commit is True
    assert contract.action_name == "存草稿"
    assert contract.operation_family == "save"
    assert contract.side_effect == "write"


def test_model_commit_can_be_inferred_from_partial_semantic_fields() -> None:
    class PartialLlm:
        async def ainvoke_structured(self, _messages, schema):
            return schema(
                operation_family="save",
                side_effect="write",
            )

    contract = asyncio.run(discover_effect_contract(
        goal="保存当前业务对象",
        capability_id="browser.modify",
        target={"role": "button", "name": "完成"},
        lang="zh",
        llm=PartialLlm(),
    ))

    assert contract.is_commit is True
    assert contract.action_name == "完成"
    assert contract.operation_family == "save"
