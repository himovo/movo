from __future__ import annotations

import asyncio

from app.enterprise_capabilities.browser.engine.effect_verification.local_interaction_policy import (
    local_read_only_interaction_contract,
)
from app.enterprise_capabilities.browser.engine.effect_verification.tracker import EffectTracker
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _obs(*elements: dict) -> Observation:
    return Observation(url="https://example.test/list", title="List", elements=list(elements))


def test_nonsemantic_popup_menu_item_is_a_local_transition() -> None:
    target = {
        "ref": "e1", "role": "menuitem", "name": "文章",
        "description": "interaction_surface=popup_menu_item",
    }

    contract = local_read_only_interaction_contract(target, _obs(target))

    assert contract is not None
    assert contract.operation_family == "select_menu_item"
    assert contract.side_effect == "none"
    assert contract.is_commit is False


def test_popup_controller_is_local_but_publish_label_stays_guarded() -> None:
    open_menu = {"role": "button", "name": "新的创作", "hasPopup": "menu", "expanded": False}
    publish_menu = {"role": "button", "name": "发布", "hasPopup": "menu", "expanded": False}

    assert local_read_only_interaction_contract(open_menu, _obs(open_menu)) is not None
    assert local_read_only_interaction_contract(publish_menu, _obs(publish_menu)) is None


def test_tabs_options_and_tree_items_do_not_call_effect_model() -> None:
    class UnexpectedLlm:
        async def ainvoke_structured(self, _messages, _schema):
            raise AssertionError("structural view selection must remain local")

    for role, label in (("tab", "草稿箱"), ("option", "文章"), ("treeitem", "内容管理")):
        target = {"ref": role, "role": role, "name": label}
        tracker = EffectTracker(
            goal="进入草稿箱并创建文章",
            capability_id="browser.publish_or_submit",
            lang="zh",
            llm=UnexpectedLlm(),
        )
        assert asyncio.run(tracker.prepare_click(target=target, before=_obs(target))) is None


def test_explicit_editor_entry_is_local_only_before_a_form_is_open() -> None:
    target = {"role": "button", "name": "新的创作"}
    list_page = _obs(target)
    editor_page = _obs(
        target,
        {"role": "textbox", "name": "标题", "editable": True},
    )

    assert local_read_only_interaction_contract(target, list_page) is not None
    assert local_read_only_interaction_contract(target, editor_page) is None


def test_mutating_menu_items_never_bypass_effect_discovery() -> None:
    for label in ("保存", "发布", "删除", "Send", "Approve"):
        target = {"role": "menuitem", "name": label}
        assert local_read_only_interaction_contract(target, _obs(target)) is None
