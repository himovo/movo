from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.dsh_runtime.events.projection import KernelEventProjector
from app.dsh_runtime.profile.tools import ToolProfileCompiler
from app.enterprise_capabilities.artifacts import service as artifact_service
from app.enterprise_capabilities.presentation.service import PresentationCreationCapability
from app.enterprise_capabilities.runtime import CapabilityExecutionContext, InternalCapabilityCatalog
from app.enterprise_capabilities.runtime.adapters import build_default_registry


def _context(progress: list[dict], **turn_context) -> CapabilityExecutionContext:
    async def publish(row: dict) -> None:
        progress.append(row)

    return CapabilityExecutionContext(
        tenant_id="tenant-a",
        user_id="user-a",
        conversation_id="conversation-a",
        kernel_session_id="session-a",
        profile_version="profile-a",
        action_id="presentation-action-a",
        message_id="message-a",
        model_instance_id="model-a",
        turn_context={"language": "zh", **turn_context},
        progress_sink=publish,
    )


class _Pipeline:
    def __init__(self, *, slide_count: int = 3) -> None:
        self.slide_count = slide_count
        self.messages = None
        self.output_spec = None

    async def build(self, *, messages, output_spec, progress_callback):
        self.messages = messages
        self.output_spec = output_spec
        await progress_callback({
            "stage": "story_planning",
            "kind": "analyze",
            "message": "正在生成PPT故事线",
        })
        bundle = {
            "slide_count": self.slide_count,
            "deck_ir_artifact": {
                "url": "https://signed.example.test/blueprint",
                "object_path": "user-a/presentation_blueprint_v5_deck.json",
                "filename": "presentation_blueprint_v5_deck.json",
            },
            "html_preview": {
                "url": "https://signed.example.test/preview",
                "object_path": "user-a/presentation_preview_v5_deck.html",
                "filename": "presentation_preview_v5_deck.html",
            },
            "preview_metadata": {
                "blueprint_artifact_path": "user-a/presentation_blueprint_v5_deck.json",
            },
        }
        return {
            "story_plan": SimpleNamespace(deck_goal="AskBot 员工AI助手介绍"),
            "preview_bundle": bundle,
            "document_payload": {
                "type": "presentation_preview_bundle",
                "url": "https://signed.example.test/preview",
                "object_path": "user-a/presentation_preview_v5_deck.html",
                "filename": "presentation_preview_v5_deck.html",
                "title": "PPT HTML 预览",
                "bundle": bundle,
                "summary": {"slide_count": self.slide_count},
            },
        }


async def _async_value(value):
    return value


@pytest.fixture(autouse=True)
def _default_presentation_settings(monkeypatch):
    from app.enterprise_capabilities.presentation import service as module

    monkeypatch.setattr(
        module,
        "get_presentation_generation_settings",
        lambda *args: _async_value(None),
    )


def test_presentation_is_one_business_level_dsh_tool() -> None:
    definition = next(
        item for item in InternalCapabilityCatalog().definitions()
        if item.capability_ref == "presentation.create@v1"
    )
    assert definition.tool_name == "presentation_create"
    assert definition.timeout_mode == "activity"
    assert definition.timeout_ms == 1_800_000
    assert definition.inactivity_timeout_ms == 600_000
    assert definition.consumes_execution_evidence is True
    assert "never construct, guess, export, or trial internal Blueprint JSON" in definition.description
    assert "minimum" not in str(definition.output_schema)
    assert build_default_registry().require("presentation.create@v1") is not None


def test_presentation_tool_compiles_once_and_spreadsheet_scope_is_explicit() -> None:
    class EmptyAdminTools:
        async def list_enabled(self, tenant_id, user_id):
            return []

    tools = asyncio.run(ToolProfileCompiler(
        EmptyAdminTools(), InternalCapabilityCatalog()
    ).compile(tenant_id="tenant-a", user_id="user-a"))
    presentations = [item for item in tools if item.name == "presentation_create"]
    assert len(presentations) == 1
    assert presentations[0].consumes_execution_evidence is True
    table = next(item for item in tools if item.name == "table_generate")
    assert "explicitly requests a spreadsheet/data attachment" in table.description
    assert "do not authorize a separate spreadsheet artifact" in table.description


def test_presentation_reuses_pipeline_and_returns_one_editable_bundle(monkeypatch) -> None:
    from app.enterprise_capabilities.presentation import service as module

    pipeline = _Pipeline(slide_count=3)
    capability = PresentationCreationCapability(lambda output_spec: pipeline)
    monkeypatch.setattr(module, "get_model_config", lambda *args: _async_value({"id": "model-a"}))
    monkeypatch.setattr(module, "get_default_model_config", lambda *args: _async_value(None))
    progress: list[dict] = []
    result = asyncio.run(capability.run(
        {
            "request": "根据 AskBot 的情况生成一个简单介绍 PPT",
            "page_count": 3,
            "audience": "企业管理者",
        },
        _context(progress, evidence_bundle={
            "results": [{
                "tool": "web_search",
                "title": "AskBot 官网",
                "source_url": "https://www.askbot.cn",
                "content": "AskBot 是企业智能体平台。",
            }],
        }),
    ))

    assert result["success"] is True
    assert result["accepted"] is True
    assert result["acceptance"] == {
        "status": "accepted",
        "retry_allowed": False,
        "reasons": [],
        "slide_count": 3,
        "requested_slide_count": 3,
        "editable": True,
    }
    artifact = result["artifact"]
    assert artifact["type"] == "presentation_preview_bundle"
    assert artifact["title"] == "AskBot 员工AI助手介绍"
    assert artifact["lifecycle"] == "final"
    assert artifact["visibility"] == "user"
    assert artifact["bundle"]["preview_metadata"]["blueprint_artifact_path"].endswith(".json")
    assert "url" not in artifact
    assert "url" not in artifact["bundle"]["html_preview"]
    assert "必须生成且仅生成 3 页幻灯片" in pipeline.messages[0]["content"]
    assert pipeline.output_spec["tool_observations"][0]["source_label"] == "AskBot 官网"
    assert pipeline.output_spec["presentation_generation_mode"] == "llm"
    assert progress[0]["payload"]["text"] == "正在生成PPT故事线"


def test_presentation_tool_result_does_not_embed_full_deck_ir() -> None:
    huge_deck_ir = {"pages": [{"blocks": [{"content": "内容" * 100_000}]}]}
    artifact = PresentationCreationCapability._stable_document({
        "type": "presentation_preview_bundle",
        "object_path": "user-a/preview.html",
        "filename": "preview.html",
        "title": "企业战略汇报",
        "bundle": {
            "artifact_version": "0.1",
            "pipeline_version": "current",
            "slide_count": 8,
            "deck_ir": huge_deck_ir,
            "page_ir_refs": [{"page_id": f"page_{index}"} for index in range(8)],
            "html_preview": {
                "url": "https://signed.example.test/preview",
                "object_path": "user-a/preview.html",
                "filename": "preview.html",
            },
            "deck_ir_artifact": {
                "url": "https://signed.example.test/blueprint",
                "object_path": "user-a/blueprint.json",
                "filename": "blueprint.json",
            },
            "preview_metadata": {
                "blueprint_artifact_path": "user-a/blueprint.json",
                "delivery_mode": "artifact_preview",
            },
        },
        "summary": {"slide_count": 8},
    })

    assert "deck_ir" not in artifact["bundle"]
    assert "page_ir_refs" not in artifact["bundle"]
    assert artifact["bundle"]["deck_ir_artifact"]["object_path"] == "user-a/blueprint.json"
    assert "url" not in artifact["bundle"]["html_preview"]
    assert len(json.dumps(artifact, ensure_ascii=False).encode("utf-8")) < 5_000


def test_presentation_fails_closed_without_exact_editable_result(monkeypatch) -> None:
    from app.enterprise_capabilities.presentation import service as module

    pipeline = _Pipeline(slide_count=0)
    capability = PresentationCreationCapability(lambda output_spec: pipeline)
    monkeypatch.setattr(module, "get_model_config", lambda *args: _async_value({"id": "model-a"}))
    monkeypatch.setattr(module, "get_default_model_config", lambda *args: _async_value(None))
    result = asyncio.run(capability.run(
        {"request": "生成三页 PPT", "page_count": 3},
        _context([]),
    ))
    assert result["success"] is False
    assert result["accepted"] is False
    assert "artifact" not in result
    assert set(result["acceptance"]["reasons"]) >= {
        "presentation_has_no_slides", "requested_slide_count_mismatch",
    }


def test_presentation_semantically_reuses_prior_conversation_evidence(monkeypatch) -> None:
    from app.enterprise_capabilities.presentation import service as module

    pipeline = _Pipeline(slide_count=3)
    capability = PresentationCreationCapability(lambda output_spec: pipeline)
    monkeypatch.setattr(module, "get_model_config", lambda *args: _async_value({"id": "model-a"}))
    monkeypatch.setattr(module, "get_default_model_config", lambda *args: _async_value(None))
    calls = []

    async def collect(**kwargs):
        calls.append(kwargs)
        return {
            "evidence_bundle": {
                "results": [{
                    "tool": "conversation_history",
                    "title": "AskBot 官网",
                    "content": "AskBot is an enterprise agent platform.",
                    "source_url": "https://askbot.cn",
                }],
            }
        }

    monkeypatch.setattr(module.conversation_evidence_service, "collect", collect)
    result = asyncio.run(capability.run(
        {
            "request": "根据上文的 AskBot 调研制作三页 PPT",
            "page_count": 3,
            "use_conversation_evidence": True,
        },
        _context([], user_request="根据上文制作三页 PPT"),
    ))

    assert result["accepted"] is True
    assert calls[0]["current_request"] == "根据上文制作三页 PPT"
    assert calls[0]["evidence_requirement"] == "根据上文的 AskBot 调研制作三页 PPT"
    assert pipeline.output_spec["tool_observations"][0]["source_label"] == "AskBot 官网"


def test_presentation_does_not_read_history_without_semantic_opt_in(monkeypatch) -> None:
    from app.enterprise_capabilities.presentation import service as module

    pipeline = _Pipeline(slide_count=3)
    capability = PresentationCreationCapability(lambda output_spec: pipeline)
    monkeypatch.setattr(module, "get_model_config", lambda *args: _async_value({"id": "model-a"}))
    monkeypatch.setattr(module, "get_default_model_config", lambda *args: _async_value(None))

    async def unexpected(**kwargs):
        raise AssertionError("conversation evidence must not be loaded")

    monkeypatch.setattr(module.conversation_evidence_service, "collect", unexpected)
    result = asyncio.run(capability.run(
        {"request": "从零创建三页产品介绍", "page_count": 3},
        _context([]),
    ))
    assert result["accepted"] is True
    assert pipeline.output_spec["tool_observations"] == []


def test_presentation_rejects_before_pipeline_when_no_vision_model(monkeypatch) -> None:
    from app.enterprise_capabilities.presentation import service as module

    pipeline = _Pipeline(slide_count=3)
    capability = PresentationCreationCapability(lambda output_spec: pipeline)
    monkeypatch.setattr(module, "get_presentation_generation_settings", lambda *args: _async_value({
        "generation_mode": "image_rebuild",
        "llm_model_id": "model-a",
        "image_model_id": "image-a",
        "vision_model_id": "vision-a",
    }))
    monkeypatch.setattr(module, "get_model_config_by_capability", lambda model_id, *args, **kwargs: _async_value(
        {"id": "model-a", "capabilities": ["chat"]} if model_id == "model-a" else None
    ))
    monkeypatch.setattr(module, "get_image_model_config", lambda *args: _async_value({"id": "image-a"}))

    result = asyncio.run(capability.run(
        {"request": "生成三页 PPT", "page_count": 3},
        _context([]),
    ))

    assert result["success"] is False
    assert "vision rebuild model is unavailable" in result["message"]
    assert pipeline.messages is None


def test_presentation_uses_models_selected_in_image_rebuild_settings(monkeypatch) -> None:
    from app.enterprise_capabilities.presentation import service as module

    pipeline = _Pipeline(slide_count=3)
    capability = PresentationCreationCapability(lambda output_spec: pipeline)
    monkeypatch.setattr(module, "get_presentation_generation_settings", lambda *args: _async_value({
        "generation_mode": "image_rebuild",
        "llm_model_id": "model-a",
        "image_model_id": "image-a",
        "vision_model_id": "vision-a",
    }))

    async def configured_model(model_id, *args, **kwargs):
        return {
            "model-a": {"id": "model-a", "capabilities": ["chat"]},
            "vision-a": {"id": "vision-a", "capabilities": ["vision"]},
        }.get(model_id)

    monkeypatch.setattr(module, "get_model_config_by_capability", configured_model)
    monkeypatch.setattr(module, "get_image_model_config", lambda *args: _async_value({"id": "image-a"}))
    result = asyncio.run(capability.run(
        {"request": "生成三页 PPT", "page_count": 3},
        _context([]),
    ))

    assert result["success"] is True
    assert pipeline.output_spec["presentation_generation_mode"] == "image_rebuild"


def test_presentation_llm_mode_does_not_switch_when_image_models_exist(monkeypatch) -> None:
    from app.enterprise_capabilities.presentation import service as module

    pipeline = _Pipeline(slide_count=3)
    capability = PresentationCreationCapability(lambda output_spec: pipeline)
    monkeypatch.setattr(module, "get_presentation_generation_settings", lambda *args: _async_value({
        "generation_mode": "llm",
        "llm_model_id": "model-a",
        "image_model_id": "image-a",
        "vision_model_id": "vision-a",
    }))
    monkeypatch.setattr(
        module,
        "get_model_config_by_capability",
        lambda *args, **kwargs: _async_value({"id": "model-a", "capabilities": ["chat"]}),
    )

    async def unexpected(*args, **kwargs):
        raise AssertionError("LLM mode must not resolve image or vision models")

    monkeypatch.setattr(module, "get_image_model_config", unexpected)
    result = asyncio.run(capability.run(
        {"request": "生成三页 PPT", "page_count": 3},
        _context([]),
    ))

    assert result["success"] is True
    assert pipeline.output_spec["presentation_generation_mode"] == "llm"


def test_pptx_export_rejects_empty_deck_and_links_valid_blueprint(monkeypatch) -> None:
    async def empty(**kwargs):
        return {"type": "pptx", "object_path": "user-a/empty.pptx", "slide_count": 0}

    monkeypatch.setattr(artifact_service.document_service, "render_presentation_pptx", empty)
    with pytest.raises(ValueError, match="produced no slides"):
        asyncio.run(artifact_service.artifact_export(
            {
                "format": "pptx",
                "blueprint_object_path": "user-a/presentation_blueprint_v5_deck.json",
            },
            _context([]),
        ))

    async def valid(**kwargs):
        return {"type": "pptx", "object_path": "user-a/deck.pptx", "slide_count": 3}

    monkeypatch.setattr(artifact_service.document_service, "render_presentation_pptx", valid)
    result = asyncio.run(artifact_service.artifact_export(
        {
            "format": "pptx",
            "blueprint_object_path": "user-a/presentation_blueprint_v5_deck.json",
        },
        _context([]),
    ))
    artifact = result["artifact"]
    assert artifact["bundle"]["preview_metadata"]["blueprint_artifact_path"].endswith(".json")
    assert artifact["bundle"]["deck_ir_artifact"]["object_path"].endswith(".json")


def test_intermediate_and_internal_artifacts_are_not_projected() -> None:
    assert KernelEventProjector._result_artifacts({
        "artifact": {
            "type": "md",
            "object_path": "user-a/internal-blueprint.md",
            "lifecycle": "intermediate",
            "visibility": "internal",
        }
    }) == []
