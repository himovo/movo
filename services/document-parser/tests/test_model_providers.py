from __future__ import annotations

import base64
import hashlib
import hmac
from unittest import TestCase
from unittest.mock import patch

from app.services.embedding_provider import _model_center_embed_texts
from app.services.reranker_provider import _model_center_rerank
from app.services.secret_codec import decrypt_admin_secret


class _Response:
    def __init__(self, body: str) -> None:
        self.body = body.encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class ModelProviderTests(TestCase):
    def test_embedding_uses_openai_compatible_endpoint(self) -> None:
        runtime = {
            "providerType": "openai_compatible",
            "providerCode": "openai",
            "baseUrl": "https://models.example/v1",
            "apiVersion": "",
            "apiKey": "secret",
            "modelName": "embedding-model",
        }
        with patch(
            "app.services.embedding_provider.urllib.request.urlopen",
            return_value=_Response('{"data":[{"index":0,"embedding":[0.1,0.2]}]}'),
        ) as request:
            result = _model_center_embed_texts(["hello"], runtime=runtime, batch_size=32, timeout=10)
        self.assertEqual(result, [[0.1, 0.2]])
        self.assertEqual(request.call_args.args[0].full_url, "https://models.example/v1/embeddings")

    def test_qwen_rerank_uses_dashscope_endpoint(self) -> None:
        runtime = {
            "providerType": "openai_compatible",
            "providerCode": "qwen",
            "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "apiVersion": "",
            "apiKey": "secret",
            "modelName": "qwen3-rerank",
        }
        candidates = [{"text": "first"}, {"text": "second"}]
        with (
            patch("app.services.reranker_provider.resolve_model_instance", return_value=runtime),
            patch(
                "app.services.reranker_provider.urllib.request.urlopen",
                return_value=_Response('{"output":{"results":[{"index":1,"relevance_score":0.9}]}}'),
            ) as request,
        ):
            result = _model_center_rerank(
                "query", candidates, {"modelInstanceId": "instance", "topK": 2}, "tenant"
            )
        self.assertEqual(result[0]["text"], "second")
        self.assertEqual(result[0]["rerankScore"], 0.9)
        self.assertIn("/services/rerank/", request.call_args.args[0].full_url)

    def test_admin_secret_counter_is_compatible(self) -> None:
        secret = "saved-api-key"
        key = hashlib.sha256(b"shared-jwt-secret").digest()
        nonce = bytes(range(16))
        stream = bytearray()
        counter = 0
        while len(stream) < len(secret.encode("utf-8")):
            stream.extend(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
            counter += 1
        cipher = bytes(left ^ right for left, right in zip(secret.encode("utf-8"), stream))
        mac = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
        encrypted = base64.urlsafe_b64encode(nonce + mac + cipher).decode("ascii")
        with patch("app.services.secret_codec.settings.admin_jwt_secret", "shared-jwt-secret"):
            self.assertEqual(decrypt_admin_secret(encrypted), secret)
