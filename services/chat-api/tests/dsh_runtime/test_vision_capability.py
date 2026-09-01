from __future__ import annotations

import asyncio

import pytest

from app.enterprise_capabilities.runtime import adapters
from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext
from app.llm.configured_models import get_configured_model_context


def _context() -> CapabilityExecutionContext:
    return CapabilityExecutionContext(
        tenant_id="tenant-vision",
        user_id="user-vision",
        conversation_id="conversation-vision",
        kernel_session_id="kernel-vision",
        profile_version="profile-vision",
        action_id="action-vision",
    )


def test_image_extract_facts_uses_tenant_vision_model(monkeypatch: pytest.MonkeyPatch) -> None:
    vision_model = {
        "id": "vision-model",
        "model_name": "vision-model-name",
        "capabilities": ["vision"],
        "api_key": "secret",
        "base_url": "https://vision.example/v1",
        "status": "active",
    }

    async def resolve_model(main_id: str, *, capability: str):
        assert main_id == "tenant-vision"
        assert capability == "vision"
        return vision_model

    async def extract_image_facts(**_: object):
        assert get_configured_model_context() == vision_model
        return {"vision_summary": "Detected facts", "image_facts": {"images": [{}]}}

    monkeypatch.setattr(adapters, "get_default_model_config_by_capability", resolve_model)
    monkeypatch.setattr(adapters, "require_owned_artifacts", lambda artifacts, user_id: artifacts)
    monkeypatch.setattr(adapters.runtime_parse_service, "extract_image_facts", extract_image_facts)

    result = asyncio.run(
        adapters.image_extract_facts(
            {"images": [{"url": "https://example.test/image.png"}], "question": "What is shown?"},
            _context(),
        )
    )

    assert result["success"] is True
    assert result["vision_summary"] == "Detected facts"
    assert get_configured_model_context() is None


def test_image_extract_facts_reports_missing_vision_model(monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolve_model(main_id: str, *, capability: str):
        return None

    monkeypatch.setattr(adapters, "get_default_model_config_by_capability", resolve_model)

    result = asyncio.run(adapters.image_extract_facts({"images": []}, _context()))

    assert result == {
        "success": False,
        "ok": False,
        "error": "vision_model_unavailable",
        "message": "No active Vision model is configured for this organization.",
    }
