"""Visual input is gated by the saved model and the current upload owner."""

import asyncio
import base64
from io import BytesIO

import pytest
from PIL import Image

from app.dsh_runtime.model_gateway.service import ModelGatewayRequest, ModelGatewayService
from app.dsh_runtime import image_input
from app.services import model_vision_probe


def _request() -> ModelGatewayRequest:
    return ModelGatewayRequest(
        profileVersion="profile-a", modelInstanceId="model-a", provider="askai-model-gateway",
        model="vision-model", sessionId="session-a",
        messages=[
            {"role": "user", "content": [{"type": "text", "text": "What is in this picture?"}]},
            {"role": "assistant", "content": [{"type": "tool-call", "id": "call-a", "name": "lookup", "arguments": "{}"}]},
            {"role": "tool", "toolCallId": "call-a", "content": [{"type": "text", "text": "done"}]},
        ],
    )


def test_blue_probe_contains_actual_blue_pixels() -> None:
    data = base64.b64decode(model_vision_probe._blue_square_data_url().split(",", 1)[1])
    image = Image.open(BytesIO(data))
    assert image.getpixel((16, 16)) == (23, 88, 219)


def test_probe_requires_visual_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self, content):
            self.content = content
    class FakeClient:
        async def ainvoke(self, messages):
            assert messages[-1].content[1]["type"] == "image_url"
            return FakeResponse("Blue.")
    async def client(*_args, **_kwargs):
        return FakeClient()
    monkeypatch.setattr(model_vision_probe, "get_llm_client_by_model_id", client)
    supported, _answer = asyncio.run(model_vision_probe.probe_model_vision("model-a", "tenant-a"))
    assert supported is True


def test_gateway_keeps_durable_image_in_user_message() -> None:
    request = _request()
    request.messages[0]["content"].append({"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}})
    messages = ModelGatewayService._messages(request)
    assert messages[0].content[0] == {"type": "text", "text": "What is in this picture?"}
    assert messages[0].content[1]["type"] == "image_url"
    assert messages[-1].role.value == "tool"


def test_image_reference_must_belong_to_speaker(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeUploader:
        storage_backend = "local"
        def read_bytes(self, _path):
            return b"png"
    monkeypatch.setattr(image_input, "AliyunOSSUploader", FakeUploader)
    with pytest.raises(ValueError, match="does not belong"):
        asyncio.run(image_input.image_content_blocks([{"object_path": "another-user/secret.png", "content_type": "image/png"}], user_id="user-a"))


def test_uploaded_image_becomes_dsh_image_block(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeUploader:
        def read_bytes(self, _path):
            return b"png bytes"
    monkeypatch.setattr(image_input, "AliyunOSSUploader", FakeUploader)
    blocks = asyncio.run(image_input.image_content_blocks([
        {"object_path": "user-a/image.png", "content_type": "image/png", "filename": "image.png"},
    ], user_id="user-a"))
    assert blocks[0].type == "image"
    assert base64.b64decode(blocks[0].data["data"]) == b"png bytes"
