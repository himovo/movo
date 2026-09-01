from app.enterprise_capabilities.content.publish_assembly.browser_payload import (
    attach_browser_publish_payload,
    build_browser_publish_payload,
)


def test_builds_channel_neutral_payload_from_markdown() -> None:
    payload = build_browser_publish_payload(
        """
# 一线服务团队如何用好 AI

## 先解决重复问题

把常见问题沉淀下来，**先给员工直接答案**。

![流程图](https://files.example.com/flow.png)
"""
    )

    assert payload is not None
    assert payload.title == "一线服务团队如何用好 AI"
    assert "# 一线服务团队" not in payload.body_markdown
    assert "![流程图]" not in payload.body_markdown
    assert "<h2>先解决重复问题</h2>" in payload.body_html
    assert "<strong>先给员工直接答案</strong>" in payload.body_html
    assert payload.body_plain_text.startswith("先解决重复问题")
    assert [item.source_url for item in payload.media] == [
        "https://files.example.com/flow.png",
    ]
    assert "把常见问题沉淀下来" in payload.media[0].anchor_after_text
    assert "先给员工直接答案" in payload.media[0].anchor_after_text
    assert payload.media[0].anchor_before_text == ""
    assert payload.media[0].anchor_plain_offset > 0


def test_deduplicates_media_and_preserves_order() -> None:
    payload = build_browser_publish_payload(
        "正文\n\n![甲](https://files.example.com/a.png)\n\n![乙](https://files.example.com/b.png)",
        visual_assets=[
            {"source_url": "https://files.example.com/a.png", "alt_text": "重复"},
            {"image_url": "/askai-api/api/files/c.png", "alt_text": "丙"},
        ],
    )

    assert payload is not None
    assert [(item.order, item.source_url) for item in payload.media] == [
        (0, "https://files.example.com/a.png"),
        (1, "https://files.example.com/b.png"),
        (2, "/askai-api/api/files/c.png"),
    ]
    assert payload.media[0].anchor_after_text == "正文"
    assert payload.media[1].anchor_plain_offset >= payload.media[0].anchor_plain_offset
    assert payload.media[2].anchor_plain_offset >= payload.media[1].anchor_plain_offset


def test_markdown_anchors_win_over_equivalent_visual_asset_routes() -> None:
    payload = build_browser_publish_payload(
        """
第一段正文。

![第一张](/api/files/user/article/first.png)

第二段正文。

![第二张](/api/files/user/article/second.png)

结尾正文。
""",
        visual_assets=[
            {
                "slot_id": "v2",
                "image_url": "/askai-api/api/files/user/article/second.png",
                "alt_text": "资产中的第二张",
            },
            {
                "slot_id": "v1",
                "image_url": "http://127.0.0.1:8000/api/files/user/article/first.png",
                "alt_text": "资产中的第一张",
            },
        ],
    )

    assert payload is not None
    assert [item.source_url for item in payload.media] == [
        "/api/files/user/article/first.png",
        "/api/files/user/article/second.png",
    ]
    assert "第一段正文" in payload.media[0].anchor_after_text
    assert "第二段正文" in payload.media[0].anchor_before_text
    assert "第二段正文" in payload.media[1].anchor_after_text
    assert "结尾正文" in payload.media[1].anchor_before_text
    assert payload.media[0].anchor_plain_offset < payload.media[1].anchor_plain_offset


def test_standalone_visual_asset_uses_end_fallback_only_when_not_in_markdown() -> None:
    payload = build_browser_publish_payload(
        "第一段。\n\n![正文图](/api/files/body.png)\n\n最后一段。",
        visual_assets=[
            "/askai-api/api/files/body.png",
            {
                "slot_id": "supplement",
                "image_url": "/api/files/standalone.png",
                "alt_text": "独立附件",
            },
        ],
    )

    assert payload is not None
    assert [item.source_url for item in payload.media] == [
        "/api/files/body.png",
        "/api/files/standalone.png",
    ]
    assert "第一段" in payload.media[0].anchor_after_text
    assert "最后一段" in payload.media[0].anchor_before_text
    assert "最后一段" in payload.media[1].anchor_after_text
    assert payload.media[1].anchor_before_text == ""


def test_visual_asset_slot_identity_deduplicates_standalone_route_variants() -> None:
    payload = build_browser_publish_payload(
        "只有正文。",
        visual_assets=[
            {
                "slot_id": "v1",
                "image_url": "/askai-api/api/files/article/image.png",
            },
            {
                "slot_id": "v1",
                "image_url": "/api/files/article/image.png",
            },
        ],
    )

    assert payload is not None
    assert [item.source_url for item in payload.media] == [
        "/askai-api/api/files/article/image.png",
    ]


def test_repeated_markdown_image_keeps_each_authored_anchor() -> None:
    payload = build_browser_publish_payload(
        """
第一处之前。

![复用图](/api/files/shared.png)

两处之间。

![复用图](/api/files/shared.png)

第二处之后。
""",
        visual_assets=["/askai-api/api/files/shared.png"],
    )

    assert payload is not None
    assert [item.source_url for item in payload.media] == [
        "/api/files/shared.png",
        "/api/files/shared.png",
    ]
    assert "第一处之前" in payload.media[0].anchor_after_text
    assert "两处之间" in payload.media[0].anchor_before_text
    assert "两处之间" in payload.media[1].anchor_after_text
    assert "第二处之后" in payload.media[1].anchor_before_text
    assert payload.media[0].anchor_plain_offset < payload.media[1].anchor_plain_offset


def test_raw_html_is_not_forwarded_as_executable_markup() -> None:
    payload = build_browser_publish_payload(
        "# 标题\n\n<script>alert('x')</script>\n\n普通正文"
    )

    assert payload is not None
    assert "<script>" not in payload.body_html
    assert "&lt;script&gt;" in payload.body_html


def test_empty_markdown_has_no_publish_payload() -> None:
    assert build_browser_publish_payload(" \n ") is None


def test_non_file_backend_routes_are_not_forwarded_as_media() -> None:
    payload = build_browser_publish_payload(
        "正文",
        visual_assets=[
            "/askai-api/api/tasks/not-an-image",
            "/askai-api/files/real-image.png",
        ],
    )

    assert payload is not None
    assert [item.source_url for item in payload.media] == [
        "/askai-api/files/real-image.png",
    ]


def test_handoff_is_only_attached_for_browser_scoped_generation() -> None:
    normal_artifacts = {"answer": "# 标题\n\n正文"}
    scoped_artifacts = {"answer": "# 标题\n\n正文"}

    assert attach_browser_publish_payload(normal_artifacts, enabled=False) is False
    assert "publish_payload" not in normal_artifacts
    assert attach_browser_publish_payload(
        scoped_artifacts,
        enabled=True,
        visual_assets=["https://files.example.com/cover.png"],
    ) is True
    assert scoped_artifacts["publish_payload"]["title"] == "标题"
    assert scoped_artifacts["publish_payload"]["media"][0]["source_url"].endswith(
        "/cover.png"
    )
