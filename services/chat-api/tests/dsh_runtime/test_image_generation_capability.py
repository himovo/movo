from __future__ import annotations

import asyncio

from app.dsh_runtime.profile.tools import ToolProfileCompiler
from app.enterprise_capabilities.images.service import ImageGenerationCapability
from app.enterprise_capabilities.runtime import CapabilityExecutionContext, InternalCapabilityCatalog
from app.enterprise_capabilities.runtime.adapters import build_default_registry


def _context(progress: list[dict]) -> CapabilityExecutionContext:
    async def publish(row: dict) -> None:
        progress.append(row)

    return CapabilityExecutionContext(
        tenant_id="tenant-a",
        user_id="user-a",
        conversation_id="conversation-a",
        kernel_session_id="session-a",
        profile_version="profile-a",
        action_id="image-action-a",
        message_id="message-a",
        turn_context={"language": "zh"},
        progress_sink=publish,
    )


def test_image_generation_is_one_provider_neutral_dsh_tool() -> None:
    definition = next(
        item for item in InternalCapabilityCatalog().definitions()
        if item.capability_ref == "image.generate@v1"
    )
    assert definition.tool_name == "generate_images"
    assert definition.display_name == "生成图片"
    assert definition.timeout_mode == "activity"
    assert definition.output_validation == "strict"
    assert "administrator-configured image model" in definition.description
    assert "never choose or name Qwen, OpenAI, Azure" in definition.description
    assert set(definition.output_schema["properties"]) >= {
        "success", "status", "assets", "failures", "continuation_required",
    }
    assert "minimum" not in str(definition.output_schema)
    assert "maximum" not in str(definition.output_schema)
    assert build_default_registry().require("image.generate@v1") is not None


def test_image_generation_compiles_once_regardless_of_configured_provider() -> None:
    class EmptyAdminTools:
        async def list_enabled(self, tenant_id, user_id):
            return []

    tools = asyncio.run(ToolProfileCompiler(
        EmptyAdminTools(), InternalCapabilityCatalog()
    ).compile(tenant_id="tenant-a", user_id="user-a"))
    generated = [item for item in tools if item.name == "generate_images"]
    assert len(generated) == 1
    assert generated[0].capability_ref == "image.generate@v1"


def test_image_generation_reuses_configured_service_and_returns_embeddable_markdown() -> None:
    calls = []

    async def generator(**kwargs):
        calls.append(kwargs)
        index = len(calls)
        return {
            "ok": True,
            "image_url": f"https://assets.example.test/image-{index}.png",
            "object_path": f"generated/user-a/image-{index}.png",
            "provider_type": "provider-secret-shape",
            "model_name": "provider-specific-model",
        }

    progress: list[dict] = []
    result = asyncio.run(ImageGenerationCapability(generator).run(
        {
            "images": [
                {"prompt": "Architecture illustration", "alt_text": "DSH 架构图", "placement_hint": "架构章节后"},
                {"prompt": "Agent workflow illustration", "alt_text": "Agent 工作流", "placement_hint": "流程章节后"},
            ]
        },
        _context(progress),
    ))

    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["generated_count"] == 2
    assert result["assets"][0]["markdown"] == "![DSH 架构图](https://assets.example.test/image-1.png)"
    assert "provider_type" not in result["assets"][0]
    assert "model_name" not in result["assets"][0]
    assert calls[0]["user_id"] == "user-a"
    assert calls[0]["output_spec"] == {"main_id": "tenant-a"}
    assert [row["payload"]["text"] for row in progress] == [
        "正在生成第 1/2 张图片", "第 1/2 张图片已生成",
        "正在生成第 2/2 张图片", "第 2/2 张图片已生成",
    ]


def test_partial_image_generation_preserves_successful_assets_for_continuation() -> None:
    calls = 0

    async def generator(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("provider temporarily unavailable")
        return {
            "image_url": "https://assets.example.test/ok.png",
            "object_path": "generated/user-a/ok.png",
        }

    result = asyncio.run(ImageGenerationCapability(generator).run(
        {"images": [{"prompt": "one"}, {"prompt": "two"}]},
        _context([]),
    ))
    assert result["success"] is True
    assert result["status"] == "partial_success"
    assert result["continuation_required"] is True
    assert result["generated_count"] == 1
    assert result["failures"][0]["index"] == 2

