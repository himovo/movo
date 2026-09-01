from __future__ import annotations

from app.enterprise_capabilities.browser.engine.action_target import (
    element_can_receive,
    locator_match_score,
    locator_matches,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.replay_target_resolution import resolve_replay_target


def test_exact_child_label_does_not_match_an_actionable_ancestor() -> None:
    locator = {"role": "menuitem", "name": "内容管理", "text": "内容管理"}
    ancestor = {
        "ref": "e1",
        "role": "button",
        "name": "展开导航 首页 内容管理 草稿箱",
        "text": "首页 内容管理 草稿箱",
        "visible": True,
        "inViewport": True,
        "hitTestable": True,
    }

    assert locator_match_score(locator, ancestor) == 0
    assert not locator_matches(locator, ancestor, tool="browser_click")


def test_name_and_text_are_alternate_exact_label_sources() -> None:
    locator = {"role": "menuitem", "name": "内容管理", "text": "内容管理"}
    target = {
        "ref": "e58",
        "role": "menuitem",
        "name": "内容管理",
        "text": "内容管理 未读 2",
        "visible": True,
        "inViewport": True,
        "hitTestable": True,
    }

    assert locator_match_score(locator, target) > 0
    assert locator_matches(locator, target, tool="browser_click")


def test_click_role_can_change_within_same_action_family() -> None:
    locator = {"role": "menuitem", "name": "内容管理"}
    rerendered_target = {
        "ref": "e58", "role": "link", "name": "内容管理",
        "visible": True, "inViewport": True, "hitTestable": True,
    }

    assert locator_matches(locator, rerendered_target, tool="browser_click")


def test_hidden_or_covered_target_cannot_receive_a_replayed_click() -> None:
    base = {"role": "menuitem", "visible": True, "inViewport": True, "hitTestable": True}

    assert not element_can_receive("browser_click", {**base, "inViewport": False})
    assert not element_can_receive("browser_click", {**base, "hitTestable": False})
    assert not element_can_receive("browser_click", {**base, "visible": False})


def test_plain_container_is_not_promoted_to_click_target_by_matching_text() -> None:
    container = {
        "role": "generic",
        "name": "内容管理",
        "visible": True,
        "inViewport": True,
        "hitTestable": True,
    }

    assert not element_can_receive("browser_click", container)


def test_hidden_native_file_input_remains_replayable() -> None:
    file_input = {
        "role": "button", "tag": "input", "type": "file",
        "visible": False, "inViewport": False, "hitTestable": False,
    }

    assert element_can_receive("browser_upload_file", file_input)
    assert not element_can_receive("browser_click", file_input)


def test_replay_tie_prefers_verified_native_activation_surface() -> None:
    locator = {"role": "button", "name": "保存草稿"}
    elements = [
        {
            "ref": "wrapper", "role": "button", "name": "保存草稿",
            "visible": True, "inViewport": True, "hitTestable": True,
        },
        {
            "ref": "native", "role": "button", "name": "保存草稿", "tag": "button",
            "activationVerified": True, "backendNodeId": 42,
            "visible": True, "inViewport": True, "hitTestable": True,
        },
    ]

    resolved = resolve_replay_target(locator, elements, tool="browser_click")

    assert resolved.ref == "native"


def test_replay_keeps_distinct_equally_verified_commit_controls_ambiguous() -> None:
    locator = {"role": "button", "name": "保存草稿"}
    elements = [
        {
            "ref": "top", "role": "button", "name": "保存草稿", "tag": "button",
            "activationVerified": True, "backendNodeId": 41,
            "visible": True, "inViewport": True, "hitTestable": True,
        },
        {
            "ref": "bottom", "role": "button", "name": "保存草稿", "tag": "button",
            "activationVerified": True, "backendNodeId": 42,
            "visible": True, "inViewport": True, "hitTestable": True,
        },
    ]

    resolved = resolve_replay_target(locator, elements, tool="browser_click")

    assert not resolved.ref
    assert resolved.reason == "ambiguous_distinct_action_surfaces"


def test_replay_collapses_duplicate_refs_for_same_physical_surface() -> None:
    locator = {"role": "button", "name": "保存草稿"}
    elements = [
        {
            "ref": "label", "role": "button", "name": "保存草稿",
            "activationVerified": True, "controlledSurfaceId": "editor-save",
            "visible": True, "inViewport": True, "hitTestable": True,
        },
        {
            "ref": "button", "role": "button", "name": "保存草稿",
            "activationVerified": True, "controlledSurfaceId": "editor-save",
            "visible": True, "inViewport": True, "hitTestable": True,
        },
    ]

    resolved = resolve_replay_target(locator, elements, tool="browser_click")

    assert resolved.ref in {"label", "button"}
    assert resolved.reason == "equivalent_physical_surface"
