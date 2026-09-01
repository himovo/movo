from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.api.routes import presentation_settings as module


def _instance(*capabilities: str) -> dict:
    return {"status": "active", "capabilities": list(capabilities)}


def test_llm_mode_validates_only_the_selected_chat_model(monkeypatch) -> None:
    calls: list[str] = []

    async def find_model(model_id: str, main_id: str):
        calls.append(model_id)
        assert main_id == "tenant-a"
        return _instance("chat")

    async def save_settings(**kwargs):
        return {**kwargs, "updated_at": None}

    monkeypatch.setattr(module, "find_instance_by_id", find_model)
    monkeypatch.setattr(module, "save_presentation_settings", save_settings)
    result = asyncio.run(module.put_settings(
        module.PresentationSettingsPayload(
            generationMode="llm",
            llmModelId="llm-a",
        ),
        {"main_id": "tenant-a", "username": "admin"},
    ))

    assert calls == ["llm-a"]
    assert result["generationMode"] == "llm"
    assert result["configured"] is True


def test_image_rebuild_validates_all_three_capabilities(monkeypatch) -> None:
    capabilities = {
        "llm-a": _instance("chat"),
        "image-a": _instance("image_generation"),
        "vision-a": _instance("vision"),
    }
    calls: list[str] = []

    async def find_model(model_id: str, main_id: str):
        calls.append(model_id)
        return capabilities.get(model_id)

    async def save_settings(**kwargs):
        return {**kwargs, "updated_at": None}

    monkeypatch.setattr(module, "find_instance_by_id", find_model)
    monkeypatch.setattr(module, "save_presentation_settings", save_settings)
    result = asyncio.run(module.put_settings(
        module.PresentationSettingsPayload(
            generationMode="image_rebuild",
            llmModelId="llm-a",
            imageModelId="image-a",
            visionModelId="vision-a",
        ),
        {"main_id": "tenant-a", "username": "admin"},
    ))

    assert calls == ["llm-a", "image-a", "vision-a"]
    assert result["generationMode"] == "image_rebuild"


def test_image_rebuild_rejects_model_without_required_capability(monkeypatch) -> None:
    capabilities = {
        "llm-a": _instance("chat"),
        "image-a": _instance("chat"),
    }

    async def find_model(model_id: str, main_id: str):
        return capabilities.get(model_id)

    monkeypatch.setattr(module, "find_instance_by_id", find_model)
    with pytest.raises(HTTPException, match="image_generation"):
        asyncio.run(module.put_settings(
            module.PresentationSettingsPayload(
                generationMode="image_rebuild",
                llmModelId="llm-a",
                imageModelId="image-a",
                visionModelId="vision-a",
            ),
            {"main_id": "tenant-a", "username": "admin"},
        ))
