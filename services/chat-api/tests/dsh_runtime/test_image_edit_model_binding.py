import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.endpoints import image_edits as endpoint
from app.api.principal import ApiPrincipal
from app.services import image_edit_model


@pytest.mark.parametrize("resolved", [None, {"id": "new-default-model"}])
def test_original_model_never_silently_falls_back_to_another_model(monkeypatch, resolved):
    resolver = AsyncMock(return_value=(resolved, "admin_config"))
    monkeypatch.setattr(image_edit_model._service, "_resolve_image_model_config", resolver)
    with pytest.raises(image_edit_model.ImageEditModelError, match="image_edit_model_unavailable"):
        asyncio.run(image_edit_model.resolve_edit_model("original-model", tenant_id="tenant", user_id="user"))
    assert resolver.call_args.kwargs["output_spec"] == {"main_id": "tenant", "image_model_id": "original-model"}
    assert resolver.await_count == 1


def test_removed_or_denied_model_does_not_use_the_default(monkeypatch):
    resolver = AsyncMock(side_effect=PermissionError("denied"))
    monkeypatch.setattr(image_edit_model._service, "_resolve_image_model_config", resolver)
    with pytest.raises(image_edit_model.ImageEditModelError, match="image_edit_model_unavailable"):
        asyncio.run(image_edit_model.resolve_edit_model("original-model", tenant_id="tenant", user_id="user"))
    assert resolver.await_count == 1


@pytest.mark.parametrize("source_model, selected_model, error", [
    ("original-model", "another-model", "image_edit_model_mismatch"),
    ("", "", "image_edit_model_required"),
    ("", "chosen-model", None),
    ("original-model", "", None),
])
def test_source_binding_and_explicit_legacy_selection(monkeypatch, source_model, selected_model, error):
    image = {"object_path": "owner/source.png", "content_type": "image/png", "image_model_id": source_model}
    db = SimpleNamespace(chat_messages=SimpleNamespace(
        find_one=AsyncMock(return_value={"documents": [image]}),
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
    ))
    monkeypatch.setattr(endpoint, "get_db", lambda: db)
    monkeypatch.setattr(endpoint, "SessionReadAuthorizer", lambda _: SimpleNamespace(authorize_read=AsyncMock(return_value=SimpleNamespace(session={}))))
    generator = AsyncMock(return_value={"object_path": "user/result.png"})
    monkeypatch.setattr(endpoint, "edit_image_asset", generator)
    call = endpoint.edit_message_image("507f1f77bcf86cd799439011", "message",
        endpoint.ImageEditRequest(prompt="Edit", object_path="owner/source.png", image_model_id=selected_model),
        ApiPrincipal("end_user", "tenant", "user"))
    if error:
        with pytest.raises(HTTPException) as failure:
            asyncio.run(call)
        assert failure.value.detail == error
        generator.assert_not_called()
    else:
        asyncio.run(call)
        assert generator.call_args.kwargs["image_model_id"] == (source_model or selected_model)
