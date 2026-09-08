from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.api.routes import presentation_settings as module


def _instance(*capabilities: str) -> dict:
    return {"status": "active", "capabilities": list(capabilities)}


def test_settings_validate_all_three_capabilities(monkeypatch) -> None:
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
            llmModelId="llm-a",
            imageModelId="image-a",
            visionModelId="vision-a",
        ),
        {"main_id": "tenant-a", "username": "admin"},
    ))

    assert calls == ["llm-a", "image-a", "vision-a"]
    assert "generationMode" not in result
    assert result["configured"] is True


def test_settings_accept_legacy_image_capability(monkeypatch) -> None:
    capabilities = {
        "llm-a": _instance("chat"),
        "image-a": _instance("image"),
        "vision-a": _instance("vision"),
    }

    async def find_model(model_id: str, main_id: str):
        return capabilities.get(model_id)

    async def save_settings(**kwargs):
        return {**kwargs, "updated_at": None}

    monkeypatch.setattr(module, "find_instance_by_id", find_model)
    monkeypatch.setattr(module, "save_presentation_settings", save_settings)

    result = asyncio.run(module.put_settings(
        module.PresentationSettingsPayload(
            llmModelId="llm-a",
            imageModelId="image-a",
            visionModelId="vision-a",
        ),
        {"main_id": "tenant-a", "username": "admin"},
    ))

    assert result["configured"] is True


def test_settings_reject_model_without_required_capability(monkeypatch) -> None:
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
                llmModelId="llm-a",
                imageModelId="image-a",
                visionModelId="vision-a",
            ),
            {"main_id": "tenant-a", "username": "admin"},
        ))


def test_legacy_partial_settings_are_reported_as_incomplete() -> None:
    result = module._serialize({"llm_model_id": "llm-a", "generation_mode": "llm"})

    assert result["configured"] is False
    assert "generationMode" not in result
