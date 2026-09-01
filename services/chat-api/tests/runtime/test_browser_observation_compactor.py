import json

from app.enterprise_capabilities.browser.engine.agent_loop.observation_compactor import compact_observation
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _element(index: int, *, name: str = "普通链接", href: str = "") -> dict:
    return {
        "ref": f"e{index}",
        "role": "link",
        "name": name,
        "text": name,
        "href": href or f"https://example.test/items/{index}",
        "visible": True,
        "disabled": False,
    }


def test_target_beyond_old_fixed_cutoff_is_included_with_href() -> None:
    elements = [_element(index) for index in range(1, 240)]
    elements[188] = _element(
        189,
        name="AskBot 如何帮助企业建设员工服务台",
        href="https://www.zhihu.com/question/123456",
    )
    observation = Observation(url="https://www.zhihu.com/search", title="搜索", elements=elements)

    compacted = compact_observation(
        observation,
        goal="在知乎查找 AskBot 员工服务台相关内容",
        element_budget_chars=6_000,
    )

    assert any(item["ref"] == "e189" for item in compacted["elements"])

    targeted = compact_observation(
        observation,
        target="AskBot 员工服务台",
        element_budget_chars=6_000,
    )

    assert targeted["target_matches"][0]["ref"] == "e189"
    assert targeted["target_matches"][0]["href"] == "https://www.zhihu.com/question/123456"
    assert compacted["element_compaction"]["total"] == 239


def test_same_label_with_distinct_destinations_is_not_deduplicated() -> None:
    observation = Observation(
        url="https://example.test/search",
        title="搜索",
        elements=[
            _element(1, name="查看详情", href="https://example.test/items/1"),
            _element(2, name="查看详情", href="https://example.test/items/2"),
            _element(3, name="查看详情", href="https://example.test/items/1"),
        ],
    )

    compacted = compact_observation(observation, goal="查看详情")

    destinations = {item["href"] for item in compacted["elements"]}
    assert destinations == {"https://example.test/items/1", "https://example.test/items/2"}
    assert len(compacted["elements"]) == 2


def test_compaction_is_budgeted_and_does_not_mutate_full_observation() -> None:
    elements = [
        {
            **_element(index, name=f"结果 {index} " + ("说明" * 100)),
            "description": "不会发送给模型的冗余结构" * 100,
        }
        for index in range(1, 220)
    ]
    observation = Observation(url="https://example.test", title="结果", elements=elements)
    original_last = dict(observation.elements[-1])

    compacted = compact_observation(observation, goal="查看结果", element_budget_chars=4_000)

    encoded_elements = json.dumps(compacted["elements"], ensure_ascii=False, separators=(",", ":"))
    assert len(encoded_elements) <= 4_100
    assert compacted["element_compaction"]["included"] < len(elements)
    assert observation.elements[-1] == original_last
    assert len(observation.elements) == 219


def test_covered_historical_ref_is_not_kept_ahead_of_live_controls() -> None:
    observation = Observation(
        url="https://example.test/post/1",
        title="Post",
        elements=[
            {**_element(1, name="old result"), "hitTestable": False},
            {"ref": "e2", "role": "textbox", "name": "Comment", "editable": True, "visible": True, "hitTestable": True},
        ],
    )

    compacted = compact_observation(observation, goal="发表评论", pinned_refs={"e1"}, element_budget_chars=2_000)

    assert compacted["elements"][0]["ref"] == "e2"


def test_visual_coordinate_metadata_survives_compaction() -> None:
    observation = Observation(
        url="https://example.test",
        title="Example",
        elements=[],
        viewport={"width": 820, "height": 684, "devicePixelRatio": 1},
        screenshot_metadata={"pixelWidth": 2048, "pixelHeight": 1536, "cssWidth": 820, "cssHeight": 684},
    )

    compacted = compact_observation(observation)

    assert compacted["viewport"]["width"] == 820
    assert compacted["screenshot_metadata"]["pixelWidth"] == 2048


def test_icon_semantics_survive_compaction_for_text_only_models() -> None:
    observation = Observation(
        url="https://example.test/editor",
        title="Editor",
        elements=[{
            "ref": "e7",
            "role": "button",
            "name": "Image",
            "description": "icon_semantic=image icon_geometry=framed_media",
            "semanticPurpose": "image",
            "visible": True,
            "hitTestable": True,
        }],
    )

    compacted = compact_observation(observation, goal="上传文章配图")

    assert compacted["elements"][0]["semanticPurpose"] == "image"
    assert "icon_semantic=image" in compacted["elements"][0]["description"]


def test_new_interaction_surface_diff_survives_compaction_with_clickable_refs() -> None:
    observation = Observation(
        url="https://example.test/publish",
        title="Publish",
        elements=[_element(1, name="发布图文"), _element(2, name="发布视频")],
        dom_diff={
            "transition": "new_interaction_surface",
            "waited_ms": 700,
            "added_elements": [
                {"ref": "e1", "role": "button", "name": "发布图文"},
                {"ref": "e2", "role": "button", "name": "发布视频"},
            ],
            "removed_elements": [],
            "changed_elements": [],
            "added_texts": ["发布图文", "发布视频"],
        },
    )

    compacted = compact_observation(observation, goal="发布图文文章")

    assert compacted["dom_diff"]["transition"] == "new_interaction_surface"
    assert [item["ref"] for item in compacted["dom_diff"]["added_elements"]] == ["e1", "e2"]
    assert compacted["dom_diff"]["added_texts"] == ["发布图文", "发布视频"]


def test_menu_relationship_and_scope_fields_survive_compaction() -> None:
    observation = Observation(
        url="https://example.test/publish",
        title="Publish",
        elements=[{
            "ref": "e1",
            "role": "button",
            "name": "发布文章",
            "visible": True,
            "hitTestable": True,
            "hasPopup": "menu",
            "expanded": True,
            "controlsId": "publish-menu",
            "scopeId": "0:#publish-toolbar",
            "scopeRole": "region",
            "scopeName": "发布工具栏",
            "scopeKind": "explicit",
            "scopeLockable": True,
        }],
    )

    element = compact_observation(observation)["elements"][0]

    assert element["hasPopup"] == "menu"
    assert element["expanded"] is True
    assert element["controlsId"] == "publish-menu"
    assert element["scopeId"] == "0:#publish-toolbar"
    assert element["scopeName"] == "发布工具栏"

    collapsed = compact_observation(Observation(
        url=observation.url,
        title=observation.title,
        elements=[{
            **observation.elements[0],
            "expanded": False,
            "controlledSurfaceId": "publish-menu",
        }],
    ))["elements"][0]
    assert collapsed["expanded"] is False
    assert collapsed["controlledSurfaceId"] == "publish-menu"
