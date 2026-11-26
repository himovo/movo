import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import httpx
from fastapi import HTTPException

from app.api.endpoints import image_edits as endpoint
from app.api.principal import ApiPrincipal
from app.dsh_runtime.session_access import SessionReadDeniedError
from app.services.image_editing import edit_request
from app.services import image_editing


def config(kind, **settings):
    return {"id": "original-model", "runtime_kind": kind, "model_name": "test-image", "api_key": "secret",
            "base_url": "https://provider.test/v1", "settings": settings}


def test_native_dashscope_edit_uses_reference_image_instead_of_text_only_generation():
    url, headers, payload, mode = edit_request(config("dashscope_image", n=4), prompt="Black glasses", source_url="https://assets.test/source.png")
    assert url == "https://provider.test/api/v1/services/aigc/multimodal-generation/generation"
    assert mode == "json"
    assert payload["input"]["messages"][0]["content"] == [{"image": "https://assets.test/source.png"}, {"text": "Black glasses"}]
    assert payload["parameters"]["n"] == 1


def test_custom_json_edit_and_standard_multipart_remain_distinct():
    url, _, payload, mode = edit_request(config("custom_images", request_path="/images/generations", size="1024*1024"), prompt="Black glasses", source_url="https://assets.test/source.png")
    assert url.endswith("/images/generations")
    assert mode == "json"
    assert payload["image"] == "https://assets.test/source.png"
    assert payload["size"] == "1024*1024"
    assert payload["n"] == 1
    url, _, payload, mode = edit_request(config("openai_images"), prompt="Black glasses", source_url="https://assets.test/source.png")
    assert url.endswith("/images/edits")
    assert mode == "multipart"
    assert "image" not in payload
    url, _, payload, mode = edit_request(config("openai_images", edit_request_format="json", edit_request_path="/edit", edit_image_field="source"), prompt="Black glasses", source_url="https://assets.test/source.png")
    assert mode == "json" and url.endswith("/edit")
    assert payload["source"] == "https://assets.test/source.png"


def test_source_matching_cannot_edit_an_unrelated_url_or_non_image():
    message = {"documents": [
        {"object_path": "owner/source.png", "url": "https://assets.test/source.png?old=1"},
        {"object_path": "owner/document.pdf", "url": "https://assets.test/document.pdf"},
    ]}
    assert endpoint.source_document(message, endpoint.ImageEditRequest(prompt="Edit", source_url="https://assets.test/source.png?new=2"))["object_path"] == "owner/source.png"
    assert endpoint.source_document(message, endpoint.ImageEditRequest(prompt="Edit", source_url="https://other.test/source.png")) is None
    assert endpoint.source_document(message, endpoint.ImageEditRequest(prompt="Edit", object_path="owner/document.pdf")) is None
    assert endpoint.source_document(message, endpoint.ImageEditRequest(prompt="Edit", object_path="other/source.png")) is None


@pytest.mark.parametrize("url", ["/api/files/signed/image", "http://localhost:8000/image", "http://127.0.0.1/image", "http://10.0.0.1/image", "https://files.internal/image", ""])
def test_local_image_sources_are_inlined_before_leaving_the_application(url):
    raw = b"\x89PNG\r\n\x1a\nreference-image"
    source = asyncio.run(image_editing.provider_image_source(SimpleNamespace(sign_url=lambda _: url, read_bytes=lambda _: raw), "owner/image.png"))
    assert source == "data:image/png;base64," + base64.b64encode(raw).decode()
    _, _, payload, _ = edit_request(config("dashscope_image"), prompt="Edit", source_url=source)
    assert payload["input"]["messages"][0]["content"][0]["image"] == source


def test_public_signed_image_source_does_not_require_reading_the_file():
    def forbidden(_):
        raise AssertionError("A public reference should not require a file download")
    url = "https://assets.test/image.png?signature=test"
    assert asyncio.run(image_editing.provider_image_source(SimpleNamespace(sign_url=lambda _: url, read_bytes=forbidden), "owner/image.png")) == url


@pytest.mark.parametrize("denied_after_generation", [False, True])
def test_edit_rechecks_membership_and_appends_without_replacing_original(monkeypatch, denied_after_generation):
    image = {"object_path": "owner/source.png", "content_type": "image/png", "image_model_id": "original-model"}
    result = {"object_path": "viewer/edited.png", "source_object_path": "owner/source.png", "type": "png"}
    messages = SimpleNamespace(find_one=AsyncMock(return_value={"documents": [image]}), update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)))
    db = SimpleNamespace(chat_messages=messages)
    authorize = AsyncMock(side_effect=[SimpleNamespace(session={}), SessionReadDeniedError()] if denied_after_generation else [SimpleNamespace(session={}), SimpleNamespace(session={})])
    generator = AsyncMock(return_value=result)
    monkeypatch.setattr(endpoint, "get_db", lambda: db)
    monkeypatch.setattr(endpoint, "SessionReadAuthorizer", lambda _: SimpleNamespace(authorize_read=authorize))
    monkeypatch.setattr(endpoint, "edit_image_asset", generator)
    call = endpoint.edit_message_image("507f1f77bcf86cd799439011", "message", endpoint.ImageEditRequest(prompt="Black glasses", object_path="owner/source.png"), ApiPrincipal("end_user", "tenant", "viewer"))
    if denied_after_generation:
        with pytest.raises(HTTPException) as failure:
            asyncio.run(call)
        assert failure.value.status_code == 404
        messages.update_one.assert_not_called()
    else:
        assert asyncio.run(call) == result
        scope, update = messages.update_one.call_args.args
        assert scope["main_id"] == "tenant"
        assert scope["message_id"] == "message"
        assert update == {"$addToSet": {"documents": result}}
    assert generator.call_args.kwargs["user_id"] == "viewer"
    assert generator.call_args.kwargs["image_model_id"] == "original-model"


def test_unrelated_source_is_rejected_before_calling_the_model(monkeypatch):
    db = SimpleNamespace(chat_messages=SimpleNamespace(find_one=AsyncMock(return_value={"documents": []})))
    monkeypatch.setattr(endpoint, "get_db", lambda: db)
    monkeypatch.setattr(endpoint, "SessionReadAuthorizer", lambda _: SimpleNamespace(authorize_read=AsyncMock(return_value=SimpleNamespace(session={}))))
    generator = AsyncMock()
    monkeypatch.setattr(endpoint, "edit_image_asset", generator)
    with pytest.raises(HTTPException) as failure:
        asyncio.run(endpoint.edit_message_image("507f1f77bcf86cd799439011", "message", endpoint.ImageEditRequest(prompt="Edit", object_path="other/source.png"), ApiPrincipal("end_user", "tenant", "viewer")))
    assert failure.value.status_code == 404
    generator.assert_not_called()


@pytest.mark.parametrize("kind", ["custom_images", "openai_images"])
def test_edit_transport_sends_original_image_and_persists_only_the_new_result(monkeypatch, kind):
    png = b"\x89PNG\r\n\x1a\nreference-bytes"
    settings = config(kind)
    original_client = httpx.AsyncClient
    requests = []

    def handle(request):
        requests.append(request)
        if kind == "custom_images":
            payload = json.loads(request.content)
            assert payload["image"] == "https://assets.test/original.png"
            assert payload["prompt"] == "Black glasses"
        else:
            assert "multipart/form-data" in request.headers["content-type"]
            assert png in request.content
            assert b'name="image"' in request.content
            assert b"Black glasses" in request.content
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png).decode()}]})

    monkeypatch.setattr(image_editing.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs))
    monkeypatch.setattr(image_editing._service, "_resolve_image_model_config", AsyncMock(return_value=(settings, "admin_config")))
    storage = SimpleNamespace(sign_url=lambda path: "https://assets.test/original.png", read_bytes=lambda path: png)
    monkeypatch.setattr(image_editing, "AliyunOSSUploader", lambda: storage)
    uploads = []

    def upload(**kwargs):
        uploads.append(kwargs)
        return {"url": "https://assets.test/edited.png", "object_path": "viewer/edited.png"}

    monkeypatch.setattr(image_editing._service, "_upload_bytes", upload)
    result = asyncio.run(image_editing.edit_image_asset(object_path="owner/original.png", prompt="Black glasses", tenant_id="tenant", user_id="viewer", image_model_id="original-model"))
    assert len(requests) == 1
    assert uploads[0]["image_bytes"] == png
    assert uploads[0]["user_id"] == "viewer"
    assert result["object_path"] == "viewer/edited.png"
    assert result["source_object_path"] == "owner/original.png"
    assert result["image_model_id"] == "original-model"
    assert image_editing._service._resolve_image_model_config.call_args.kwargs["output_spec"]["image_model_id"] == "original-model"
