import base64

import httpx

from app.llm.providers.azure_gpt_image import AzureGptImageClient, AzureGptImageConfig


def test_generation_endpoint_matches_poc_v1_shape():
    client = AzureGptImageClient(config=AzureGptImageConfig(
        endpoint="https://example-resource.openai.azure.com/",
        api_key="secret",
        deployment="gpt-image-2",
        api_style="v1",
        api_version="2024-02-01",
    ))

    assert client.image_generation_endpoint("generations") == "https://example-resource.openai.azure.com/openai/v1/images/generations"


def test_generate_image_uses_poc_a_request_shape(monkeypatch):
    client = AzureGptImageClient(config=AzureGptImageConfig(
        endpoint="https://example-resource.openai.azure.com/",
        api_key="secret",
        deployment="gpt-image-2",
        size="1536x864",
        quality="low",
        api_style="v1",
        api_version="2024-02-01",
    ))
    captured = {}
    png_bytes = b"fake-png"

    def _fake_post_with_retry(endpoint, *, headers, request_tag, log_hook=None, json_payload=None):
        captured["endpoint"] = endpoint
        captured["headers"] = dict(headers)
        captured["request_tag"] = request_tag
        captured["json_payload"] = dict(json_payload or {})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": base64.b64encode(png_bytes).decode("ascii"),
                    }
                ]
            },
        )

    monkeypatch.setattr(client, "_post_with_retry", _fake_post_with_retry)
    result = client.generate_image("draw a cover background")

    assert result.image_bytes == png_bytes
    assert captured["endpoint"] == "https://example-resource.openai.azure.com/openai/v1/images/generations"
    assert captured["request_tag"] == "image_generation"
    assert captured["headers"]["api-key"] == "secret"
    assert captured["headers"]["Content-Type"] == "application/json"
    assert captured["headers"]["Connection"] == "close"
    assert captured["json_payload"] == {
        "model": "gpt-image-2",
        "prompt": "draw a cover background",
        "size": "1536x864",
        "n": 1,
        "quality": "low",
        "output_format": "png",
    }
