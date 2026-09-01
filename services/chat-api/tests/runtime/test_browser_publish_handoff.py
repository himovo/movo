from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.enterprise_capabilities.browser.engine.drivers.base import BrowserDriver
from app.enterprise_capabilities.browser.engine.drivers.form_input import FormInputDriver
from app.enterprise_capabilities.browser.engine.form_input import BrowserInputContext, discover_fields
from app.enterprise_capabilities.browser.engine.form_input.contracts import FieldDescriptor
from app.enterprise_capabilities.browser.engine.form_input.resolver import resolve_deterministic
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


class _Fallback(BrowserDriver):
    @property
    def kind(self) -> str:
        return "fake"

    async def next_step(self, goal, history, observation, state_ledger=None) -> Decision:
        del goal, history, observation, state_ledger
        return Decision(tool="browser_observe", rationale="fallback")


def _payload() -> dict:
    return {
        "schema_version": "1.0",
        "title": "企业知识助手落地指南",
        "body_markdown": "## 从高频问题开始\n\n先整理重复咨询。",
        "body_plain_text": "从高频问题开始\n先整理重复咨询。",
        "body_html": "<h2>从高频问题开始</h2><p>先整理重复咨询。</p>",
        "media": [
            {
                "source_url": "https://files.example.com/guide.png",
                "kind": "image",
                "order": 0,
                "alt_text": "落地路径",
            }
        ],
    }


def _context() -> BrowserInputContext:
    node = SimpleNamespace(depends_on=["N_GENERATE"])
    return BrowserInputContext.from_runtime(
        original_request="生成文章并发布",
        node=node,
        output_spec={
            "graph_artifacts": {
                "N_GENERATE": {
                    "answer": "不应成为重复候选",
                    "article_markdown": "不应成为重复候选",
                    "publish_payload": _payload(),
                }
            }
        },
    )


def _observation(*elements: dict) -> Observation:
    return Observation(
        url="https://example.test/publish",
        title="发布",
        elements=list(elements),
        auth={"state": "authenticated"},
    )


def _form(*, content_editable_mode: str = "true") -> Observation:
    common = {
        "scopeId": "0:publish-form",
        "scopeSelector": "#publish-form",
        "scopeLockable": True,
        "scopeText": "标题 正文 上传 发布",
        "visible": True,
        "hitTestable": True,
    }
    return _observation(
        {
            **common,
            "ref": "title",
            "role": "textbox",
            "name": "标题",
            "tag": "input",
            "selector": "#title",
            "editable": True,
            "value": "企业知识助手落地指南",
        },
        {
            **common,
            "ref": "body",
            "role": "textbox",
            "name": "正文",
            "tag": "div",
            "selector": "#editor",
            "editable": True,
            "contentEditable": True,
            "contentEditableMode": content_editable_mode,
            "value": "",
        },
        {
            **common,
            "ref": "media",
            "role": "textbox",
            "name": "图片上传",
            "tag": "input",
            "type": "file",
            "selector": "#media",
            "visible": False,
            "value": "",
        },
        {
            **common,
            "ref": "publish",
            "role": "button",
            "name": "发布",
            "tag": "button",
            "selector": "#publish",
            "disabled": False,
        },
    )


def test_publish_payload_is_canonical_and_keeps_ordered_media() -> None:
    candidates = _context().candidates

    assert [item.semantic_name for item in candidates] == ["title", "body", "media"]
    assert candidates[0].metadata["binding_authority"] == "publish_payload"
    assert candidates[0].metadata["field_role"] == "title"
    assert candidates[1].metadata["binding_authority"] == "publish_payload"
    assert candidates[1].metadata["field_role"] == "body"
    assert candidates[1].rich_html.startswith("<h2>")
    assert candidates[1].plain_text.startswith("从高频问题开始")
    assert candidates[2].value == ["https://files.example.com/guide.png"]
    assert candidates[2].metadata["media_anchor"] == {
        "after_text": "",
        "before_text": "",
        "plain_offset": 0,
        "order": 0,
    }
    assert candidates[2].metadata["binding_authority"] == "publish_payload"
    assert candidates[2].metadata["field_role"] == "attachment"


def test_dispatch_replaces_model_rewritten_body_with_canonical_payload() -> None:
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=_context(),
        capability_id="browser.publish",
    )
    observation = _form()
    rewritten = Decision(
        tool="browser_fill",
        args={
            "ref": "body",
            "value": (
                '重写后的正文<img src="/askai-api/api/files/generated.png">'
            ),
            "rich_html": (
                '<p>重写后的正文</p>'
                '<img src="/askai-api/api/files/generated.png">'
            ),
        },
        rationale="generic loop reconstructed upstream content",
    )

    normalized = driver.prepare_dispatch(rewritten, observation)

    assert normalized.tool == "browser_fill"
    assert normalized.args == {
        "ref": "body",
        "value": "从高频问题开始\n先整理重复咨询。",
        "rich_html": "<h2>从高频问题开始</h2><p>先整理重复咨询。</p>",
    }
    assert "publish_payload_authority" in normalized.rationale


def test_publish_payload_suppresses_publish_assembly_draft_copies() -> None:
    node = SimpleNamespace(depends_on=["N_GENERATE"])
    context = BrowserInputContext.from_runtime(
        original_request="生成文章并发布",
        node=node,
        output_spec={
            "graph_artifacts": {
                "N_GENERATE": {
                    "publish_payload": _payload(),
                    "publish_assembly": {
                        "body_markdown": "重复正文草稿",
                        "final_markdown": "重复图文草稿",
                        "generated_assets": [
                            {"image_url": "https://files.example.com/guide.png"},
                        ],
                    },
                }
            }
        },
    )

    assert [item.semantic_name for item in context.candidates] == [
        "title",
        "body",
        "media",
    ]


def test_each_publish_media_item_becomes_an_independent_anchored_candidate() -> None:
    payload = _payload()
    payload["media"] = [
        {
            "source_url": "https://files.example.com/first.png",
            "kind": "image",
            "order": 0,
            "alt_text": "第一张",
            "anchor_after_text": "第一段",
            "anchor_before_text": "第二段",
            "anchor_plain_offset": 3,
        },
        {
            "source_url": "https://files.example.com/second.png",
            "kind": "image",
            "order": 1,
            "alt_text": "第二张",
            "anchor_after_text": "第二段",
            "anchor_before_text": "",
            "anchor_plain_offset": 6,
        },
    ]
    node = SimpleNamespace(depends_on=["N_GENERATE"])
    context = BrowserInputContext.from_runtime(
        original_request="发布图文",
        node=node,
        output_spec={
            "graph_artifacts": {
                "N_GENERATE": {"publish_payload": payload},
            },
        },
    )

    media = [item for item in context.candidates if item.value_kind == "file"]

    assert [item.value for item in media] == [
        ["https://files.example.com/first.png"],
        ["https://files.example.com/second.png"],
    ]
    assert [item.metadata["media_anchor"]["plain_offset"] for item in media] == [3, 6]


def test_multi_node_handoff_keeps_one_coherent_body_and_its_media() -> None:
    article_payload = _payload()
    article_payload["title"] = ""
    article_payload["body_markdown"] = "正式文章正文\n\n## 解决方案\n\n这里解释实施路径。"
    article_payload["body_plain_text"] = "正式文章正文\n解决方案\n这里解释实施路径。"
    article_payload["body_html"] = "<p>正式文章正文</p><h2>解决方案</h2><p>这里解释实施路径。</p>"
    article_payload["media"] = [
        {
            "source_url": "https://files.example.com/article-1.png",
            "order": 0,
            "anchor_after_text": "正式文章正文",
            "anchor_before_text": "解决方案",
            "anchor_plain_offset": 6,
        },
        {
            "source_url": "https://files.example.com/article-2.png",
            "order": 1,
            "anchor_after_text": "这里解释实施路径。",
            "anchor_before_text": "",
            "anchor_plain_offset": 18,
        },
    ]
    image_payload = _payload()
    image_payload["body_markdown"] = "配图说明文档，与正式文章不是同一正文。"
    image_payload["body_plain_text"] = "配图说明文档，与正式文章不是同一正文。"
    image_payload["media"] = [
        {
            "source_url": "https://files.example.com/foreign.png",
            "order": 0,
            "anchor_after_text": "配图说明文档",
            "anchor_before_text": "不是同一正文",
            "anchor_plain_offset": 6,
        }
    ]
    node = SimpleNamespace(depends_on=["N_ARTICLE", "N_IMAGES"])
    context = BrowserInputContext.from_runtime(
        original_request="生成两张配图并发布文章",
        node=node,
        output_spec={
            "effective_policy": {
                "compose_policy": {
                    "visual_preferences": {"min_images": 2, "max_images": 2}
                }
            },
            "graph_artifacts": {
                "N_ARTICLE": {
                    "article_markdown": "正式文章正文",
                    "publish_payload": article_payload,
                },
                "N_IMAGES": {
                    "dynamic_markdown": "配图说明文档",
                    "publish_payload": image_payload,
                },
            },
        },
    )

    bodies = [item for item in context.candidates if item.semantic_name == "body"]
    media = [item for item in context.candidates if item.value_kind == "file"]

    assert len(bodies) == 1
    assert bodies[0].value.startswith("正式文章正文")
    assert [item.value for item in media] == [
        ["https://files.example.com/article-1.png"],
        ["https://files.example.com/article-2.png"],
    ]
    assert all(
        item.semantic_name != "dynamic_markdown"
        for item in context.candidates
    )


def test_supporting_media_is_rebased_when_primary_payload_has_no_images() -> None:
    article_payload = _payload()
    article_payload["body_markdown"] = "正式正文第一段。\n\n## 第二节\n\n正式正文结尾。"
    article_payload["body_plain_text"] = "正式正文第一段。\n第二节\n正式正文结尾。"
    article_payload["media"] = []
    image_payload = _payload()
    image_payload["body_markdown"] = "独立配图说明。"
    image_payload["body_plain_text"] = "独立配图说明。"
    image_payload["media"] = [
        {
            "source_url": "https://files.example.com/support.png",
            "order": 0,
            "anchor_after_text": "独立配图说明",
            "anchor_before_text": "",
            "anchor_plain_offset": 7,
        }
    ]
    node = SimpleNamespace(depends_on=["N_ARTICLE", "N_IMAGES"])
    context = BrowserInputContext.from_runtime(
        original_request="生成一张配图并发布文章",
        node=node,
        output_spec={
            "effective_policy": {
                "compose_policy": {
                    "visual_preferences": {"min_images": 1, "max_images": 1}
                }
            },
            "graph_artifacts": {
                "N_ARTICLE": {
                    "article_markdown": "正式正文",
                    "publish_payload": article_payload,
                },
                "N_IMAGES": {
                    "dynamic_markdown": "独立配图说明",
                    "publish_payload": image_payload,
                },
            },
        },
    )

    media = next(item for item in context.candidates if item.value_kind == "file")
    anchor = media.metadata["media_anchor"]

    assert media.value == ["https://files.example.com/support.png"]
    assert "正式正文结尾" in anchor["after_text"]
    assert "独立配图说明" not in anchor["after_text"]


def test_rich_editor_uses_safe_rich_fill_without_changing_tool_contract() -> None:
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=_context(),
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("发布文章", [], _form()))

    assert decision.tool == "browser_fill"
    assert decision.args == {
        "ref": "body",
        "value": "从高频问题开始\n先整理重复咨询。",
        "rich_html": "<h2>从高频问题开始</h2><p>先整理重复咨询。</p>",
    }


def test_unique_unlabelled_rich_editor_binds_without_model_guessing() -> None:
    observation = _form()
    body = next(item for item in observation.elements if item.get("ref") == "body")
    body["name"] = ""
    body["description"] = ""
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=_context(),
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("发布文章", [], observation))

    assert decision.tool == "browser_fill"
    assert decision.args["ref"] == "body"
    assert decision.args["rich_html"].startswith("<h2>")


def test_unlabelled_rich_body_wins_over_title_textarea() -> None:
    observation = _form()
    title = next(item for item in observation.elements if item.get("ref") == "title")
    title["name"] = ""
    title["description"] = ""
    title["placeholder"] = "输入标题"
    title["tag"] = "textarea"
    title["multiline"] = True
    title["value"] = ""
    body = next(item for item in observation.elements if item.get("ref") == "body")
    body["name"] = ""
    body["description"] = ""
    fields = discover_fields(observation)
    resolved, unresolved = resolve_deterministic(fields, _context())

    body_field = next(field for field in fields if field.ref == "body")
    title_field = next(field for field in fields if field.ref == "title")
    assert resolved[body_field.field_key].rich_html.startswith("<h2>")
    assert resolved[title_field.field_key].value == "企业知识助手落地指南"
    assert body_field.field_key not in {field.field_key for field in unresolved}
    assert title_field.field_key not in {field.field_key for field in unresolved}


def test_missing_upstream_title_does_not_block_rich_body_binding() -> None:
    payload = _payload()
    payload["title"] = ""
    node = SimpleNamespace(depends_on=["N_GENERATE"])
    context = BrowserInputContext.from_runtime(
        original_request="围绕企业服务台生成文章并发布",
        node=node,
        output_spec={
            "graph_artifacts": {
                "N_GENERATE": {"publish_payload": payload},
            },
        },
    )
    observation = _form()
    title = next(item for item in observation.elements if item.get("ref") == "title")
    title.update({
        "name": "",
        "description": "",
        "placeholder": "输入标题",
        "tag": "textarea",
        "multiline": True,
        "value": "",
    })
    body = next(item for item in observation.elements if item.get("ref") == "body")
    body.update({"name": "", "description": ""})

    fields = discover_fields(observation)
    resolved, unresolved = resolve_deterministic(fields, context)

    body_field = next(field for field in fields if field.ref == "body")
    title_field = next(field for field in fields if field.ref == "title")
    assert resolved[body_field.field_key].rich_html.startswith("<h2>")
    assert title_field.field_key in {field.field_key for field in unresolved}


def test_strict_title_placeholder_is_a_role_hint_not_a_value() -> None:
    title = FieldDescriptor(
        field_key="title",
        ref="e12",
        role="textbox",
        placeholder="输入标题",
        control_kind="multiline",
    )
    dynamic = FieldDescriptor(
        field_key="search",
        ref="e13",
        role="searchbox",
        placeholder="法国vs英格兰",
        control_kind="text",
    )

    assert title.semantic_label == "title"
    assert title.display_label("zh") == "标题"
    assert dynamic.semantic_label == "input"


def test_plaintext_only_editor_falls_back_to_existing_fill_path() -> None:
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=_context(),
        capability_id="browser.publish",
    )

    decision = asyncio.run(
        driver.next_step("发布文章", [], _form(content_editable_mode="plaintext-only"))
    )

    assert decision.tool == "browser_fill"
    assert decision.args == {
        "ref": "body",
        "value": "从高频问题开始\n先整理重复咨询。",
    }


def test_publish_body_candidate_never_uses_raw_markdown_as_default_value() -> None:
    body = next(
        item for item in _context().candidates
        if item.semantic_name == "body"
    )

    assert body.value == "从高频问题开始\n先整理重复咨询。"
    assert "##" not in body.preview()
    assert body.rich_html == "<h2>从高频问题开始</h2><p>先整理重复咨询。</p>"


def test_one_media_payload_is_not_guessed_across_multiple_upload_fields() -> None:
    observation = _form()
    media = next(item for item in observation.elements if item.get("ref") == "media")
    observation.elements.append({
        **media,
        "ref": "cover",
        "name": "封面图片",
        "selector": "#cover",
    })

    resolved, unresolved = resolve_deterministic(
        discover_fields(observation),
        _context(),
    )

    assert all(binding.action != "upload" for binding in resolved.values())
    assert {"media", "cover"} <= {field.ref for field in unresolved}


def test_non_publish_artifacts_keep_existing_candidate_walk() -> None:
    node = SimpleNamespace(depends_on=["N_GENERATE"])
    context = BrowserInputContext.from_runtime(
        original_request="发表评论",
        node=node,
        output_spec={
            "graph_artifacts": {
                "N_GENERATE": {"comment": "这是普通评论，不应触发富文本写入"}
            }
        },
    )

    assert len(context.candidates) == 1
    assert context.candidates[0].value_kind == "text"
    assert context.candidates[0].rich_html == ""
