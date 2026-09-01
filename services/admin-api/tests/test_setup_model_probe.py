from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

from app.services.setup_model_probe import probe_knowledge_model


class _Response:
    def __init__(self, body: str) -> None:
        self.body = body.encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class SetupModelProbeTests(TestCase):
    def test_embedding_probe(self) -> None:
        model = {
            "capabilities": ["embedding"],
            "base_url": "https://models.example/v1",
            "model_name": "embedding-model",
            "api_key": "secret",
        }
        with patch(
            "app.services.setup_model_probe.urllib.request.urlopen",
            return_value=_Response('{"data":[{"embedding":[0.1,0.2,0.3]}]}'),
        ):
            message = probe_knowledge_model(model, {"provider_type": "openai_compatible"})
        self.assertIn("3 dimensions", message)

    def test_qwen_rerank_probe(self) -> None:
        model = {
            "capabilities": ["rerank"],
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model_name": "qwen3-rerank",
            "api_key": "secret",
        }
        with patch(
            "app.services.setup_model_probe.urllib.request.urlopen",
            return_value=_Response('{"output":{"results":[{"index":0,"relevance_score":0.9}]}}'),
        ) as request:
            message = probe_knowledge_model(model, {"provider_type": "openai_compatible", "code": "qwen"})
        self.assertEqual(message, "Rerank connection succeeded.")
        self.assertIn("/services/rerank/", request.call_args.args[0].full_url)
