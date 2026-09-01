from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.enterprise_capabilities.browser.engine.drivers.base import BrowserDriver
from app.enterprise_capabilities.browser.engine.drivers.form_input import FormInputDriver
from app.enterprise_capabilities.browser.engine.form_input import BrowserInputContext
from app.enterprise_capabilities.browser.engine.form_input.resource_projection import (
    project_resource_artifact,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


class _Fallback(BrowserDriver):
    @property
    def kind(self) -> str:
        return "fake"

    async def next_step(
        self,
        goal,
        history,
        observation,
        state_ledger=None,
    ) -> Decision:
        del goal, history, observation, state_ledger
        return Decision(tool="browser_observe", rationale="fallback")


def _observation(*elements: dict) -> Observation:
    return Observation(
        url="https://example.test/editor",
        title="Editor",
        elements=list(elements),
        auth={"state": "authenticated"},
    )


def test_resource_bundle_projects_one_file_without_evidence_pollution() -> None:
    image = {
        "filename": "generated.png",
        "url": "/askai-api/api/files/generated.png",
        "source_url": "https://source.example.test/generated.png",
        "content_type": "image/png",
    }
    decoded = {
        "results": [{
            "title": "collector response",
            "content": "download fallback diagnostics must not become form content",
        }],
        "source_material": [{
            "title": "collector response",
            "content": "download fallback diagnostics must not become form content",
        }],
        "images": [image],
        "resource_bundle": {
            "requested_types": ["urls", "images"],
            "urls": [{
                "url": "https://source.example.test/generated.png",
                "source": "user_or_upstream_text",
            }],
            "images": [image],
            "attachments": [],
        },
    }
    context = BrowserInputContext.from_runtime(
        original_request="把这张图片上传到编辑器",
        node=SimpleNamespace(depends_on=["collect"]),
        output_spec={
            "graph_artifacts": {
                "collect": {
                    "tool_results": [{"tool": "collect", "result": decoded}],
                    "research_bundle": {"results": decoded["results"]},
                    "source_material": {"results": decoded["results"]},
                    "decoded_payload": decoded,
                    "images": [{
                        "filename": "generated.png",
                        "url": "/askai-api/api/files/generated.png",
                    }],
                    "resource_bundle": decoded["resource_bundle"],
                },
            },
        },
    )

    files = [item for item in context.candidates if item.value_kind == "file"]
    assert len(files) == 1
    assert files[0].value == ["/askai-api/api/files/generated.png"]
    assert files[0].source_path == "artifacts.collect.resource_bundle.images"
    assert all(
        item.semantic_name not in {
            "content", "results", "source_material", "urls",
        }
        for item in context.candidates
    )
    assert "download fallback diagnostics" not in str(context.model_payload())
    assert "https://source.example.test/generated.png" not in str(
        [item.value for item in files]
    )


def test_cached_resource_envelope_projects_same_file_without_evidence_pollution() -> None:
    image = {
        "filename": "generated.png",
        "signed_url": "/askai-api/api/files/generated.png",
        "source_url": "https://source.example.test/generated.png",
    }
    cached_result = {
        "results": [{
            "title": "collector response",
            "content": "cached collector evidence is not article body",
        }],
        "source_material": [{
            "content": "cached fallback diagnostics are not article body",
        }],
        "images": [image],
        "resource_bundle": {
            "requested_types": ["urls", "images"],
            "images": [image],
            "attachments": [],
        },
    }
    context = BrowserInputContext.from_runtime(
        original_request="填写正文并上传缓存图片",
        node=SimpleNamespace(depends_on=["collect"]),
        output_spec={
            "graph_artifacts": {
                "collect": {
                    "decoded_payload": {
                        "ok": True,
                        "result": cached_result,
                    },
                    "business_payload": {
                        "content": "wrapped evidence must remain outside form input",
                    },
                    "research_bundle": {
                        "results": cached_result["results"],
                    },
                },
            },
        },
    )

    assert len(context.candidates) == 1
    assert context.candidates[0].value_kind == "file"
    assert context.candidates[0].value == [
        "/askai-api/api/files/generated.png",
    ]
    assert context.candidates[0].source_path == (
        "artifacts.collect.decoded_payload.result.resource_bundle.images"
    )
    assert not any(
        candidate.semantic_name.casefold() in {"body", "content"}
        for candidate in context.candidates
    )


def test_non_resource_result_wrapper_is_not_treated_as_resource_envelope() -> None:
    artifact = {
        "decoded_payload": {
            "ok": True,
            "result": {
                "content": "ordinary tool result",
            },
        },
    }

    assert project_resource_artifact(
        artifact,
        source_path="artifacts.tool",
    ) is None


def test_resource_bundle_suppresses_executor_business_payload_copy() -> None:
    image = {
        "filename": "generated.png",
        "signed_url": "/askai-api/api/files/generated.png",
    }
    context = BrowserInputContext.from_runtime(
        original_request="填写任意内容并上传图片",
        node=SimpleNamespace(depends_on=["collect"]),
        output_spec={
            "graph_artifacts": {
                "collect": {
                    "resource_bundle": {
                        "requested_types": ["urls", "images"],
                        "images": [image],
                        "attachments": [],
                    },
                    "business_payload": {
                        "ok": True,
                        "tool": "firecrawl_collect_url",
                        "results": [{
                            "title": "downloaded_resource.html",
                            "content": "采集证据不能成为浏览器正文候选",
                        }],
                        "source_material": [{
                            "content": "采集失败说明也不能成为浏览器正文候选",
                        }],
                        "resource_bundle": {
                            "images": [image],
                        },
                    },
                    "business_schema": {
                        "payload_array_paths": [
                            "results",
                            "source_material",
                            "resource_bundle.images",
                        ],
                    },
                },
            },
        },
    )

    assert len(context.candidates) == 1
    assert context.candidates[0].value_kind == "file"
    assert context.candidates[0].value == [
        "/askai-api/api/files/generated.png",
    ]
    assert not any(
        candidate.semantic_name.casefold() in {"body", "content"}
        for candidate in context.candidates
    )


def test_resource_bundle_preserves_explicit_business_values() -> None:
    context = BrowserInputContext.from_runtime(
        original_request="提交工单并附上截图",
        node=SimpleNamespace(depends_on=["prepare"]),
        output_spec={
            "graph_artifacts": {
                "prepare": {
                    "resource_bundle": {
                        "images": [{
                            "url": "https://assets.example.test/screenshot.png",
                        }],
                    },
                    "business_data": {
                        "ticket_subject": "无法登录工作台",
                    },
                },
            },
        },
    )

    assert any(
        item.value_kind == "file"
        and item.value == ["https://assets.example.test/screenshot.png"]
        for item in context.candidates
    )
    assert any(
        item.semantic_name == "ticket_subject"
        and item.value == "无法登录工作台"
        for item in context.candidates
    )


def test_short_fallback_body_does_not_block_typed_resource_upload() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "body", "role": "textbox", "name": "正文", "tag": "div",
            "contentEditable": True, "editable": True, "visible": True,
            "value": "这是一篇测试笔记的内容。", "scopeId": scope,
            "scopeLockable": True,
        },
        {
            "ref": "image", "role": "button", "name": "Image",
            "semanticPurpose": "image", "tag": "button", "visible": True,
            "hitTestable": True, "inViewport": True, "width": 32, "height": 32,
            "scopeId": scope, "scopeLockable": True,
        },
    )
    context = BrowserInputContext.from_runtime(
        original_request="填写任意短正文并上传图片",
        node=SimpleNamespace(depends_on=["download"]),
        output_spec={
            "graph_artifacts": {
                "download": {
                    "resource_bundle": {
                        "images": [{
                            "url": "/askai-api/api/files/generated.png",
                            "source_url": "https://source.example.test/generated.png",
                        }],
                        "urls": [{
                            "url": "https://source.example.test/generated.png",
                        }],
                    },
                    "source_material": {
                        "results": [{
                            "content": "irrelevant collector content",
                        }],
                    },
                },
            },
        },
    )
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=context,
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("填写并上传图片", [], observation))

    assert decision.tool == "browser_upload_file"
    assert decision.args["ref"] == "image"
    assert decision.args["sources"] == [
        "/askai-api/api/files/generated.png",
    ]


def test_cached_resource_envelope_uploads_through_hidden_file_input() -> None:
    scope = "0:#article-editor"
    observation = _observation(
        {
            "ref": "title", "role": "textbox", "name": "测试标题",
            "tag": "div", "contentEditable": True, "editable": True,
            "visible": True, "value": "测试标题", "scopeId": scope,
        },
        {
            "ref": "body", "role": "textbox", "name": "这是测试正文内容。",
            "tag": "body", "contentEditable": True, "editable": True,
            "visible": True, "value": "这是测试正文内容。",
            "frameDepth": 1,
        },
        {
            "ref": "image-file", "role": "textbox", "tag": "input",
            "type": "file", "accept": "image/*", "editable": True,
            "visible": False, "hitTestable": False, "disabled": False,
            "scopeId": scope,
        },
    )
    context = BrowserInputContext.from_runtime(
        original_request="正文填写完成后上传图片",
        node=SimpleNamespace(depends_on=["download"]),
        output_spec={
            "graph_artifacts": {
                "download": {
                    "decoded_payload": {
                        "ok": True,
                        "result": {
                            "images": [{
                                "signed_url": "/askai-api/api/files/generated.png",
                            }],
                            "resource_bundle": {
                                "requested_types": ["images"],
                                "images": [{
                                    "signed_url": "/askai-api/api/files/generated.png",
                                }],
                                "attachments": [],
                            },
                        },
                    },
                },
            },
        },
    )
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=context,
        capability_id="browser.publish",
    )

    decision = asyncio.run(driver.next_step("填写并上传图片", [], observation))

    assert decision.tool == "browser_upload_file"
    assert decision.args["ref"] == "image-file"
    assert decision.args["sources"] == [
        "/askai-api/api/files/generated.png",
    ]
