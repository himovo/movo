from __future__ import annotations

from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.services.setup_model import SetupModelError, _normalize_payload, inspect_setup_model, test_setup_model
from app.services.setup_model_probe import SetupKnowledgeProbeResult


class SetupModelValidationTests(IsolatedAsyncioTestCase):
    def test_normalizes_openai_compatible_payload(self) -> None:
        provider = {
            "_id": "507f1f77bcf86cd799439011",
            "provider_type": "openai_compatible",
            "default_base_url": "https://api.example.com/v1",
        }
        result = _normalize_payload(
            {
                "providerId": str(provider["_id"]),
                "displayName": "Default model",
                "modelName": "example-chat",
                "baseUrl": "",
                "apiKey": "secret",
            },
            provider,
        )
        self.assertEqual(result["base_url"], "https://api.example.com/v1")
        self.assertFalse(result["is_default"])
        self.assertEqual(result["capabilities"], ["chat"])

    def test_requires_azure_api_version(self) -> None:
        provider = {
            "_id": "507f1f77bcf86cd799439011",
            "provider_type": "azure_openai",
            "default_base_url": "https://example.openai.azure.com",
        }
        with self.assertRaisesRegex(SetupModelError, "API Version"):
            _normalize_payload(
                {
                    "providerId": str(provider["_id"]),
                    "displayName": "Azure",
                    "modelName": "deployment",
                    "baseUrl": provider["default_base_url"],
                    "apiKey": "secret",
                },
                provider,
            )

    def test_normalizes_optional_embedding_without_making_it_default(self) -> None:
        provider = {
            "_id": "507f1f77bcf86cd799439011",
            "provider_type": "openai_compatible",
            "default_base_url": "https://api.example.com/v1",
        }
        result = _normalize_payload(
            {
                "providerId": str(provider["_id"]),
                "displayName": "Knowledge embedding",
                "modelName": "text-embedding-example",
                "baseUrl": "",
                "apiKey": "secret",
                "capability": "embedding",
            },
            provider,
        )
        self.assertEqual(result["capabilities"], ["embedding"])
        self.assertFalse(result["is_default"])

    def test_normalizes_optional_rerank_without_making_it_default(self) -> None:
        provider = {
            "_id": "507f1f77bcf86cd799439011",
            "provider_type": "openai_compatible",
            "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        }
        result = _normalize_payload(
            {
                "providerId": str(provider["_id"]),
                "displayName": "Knowledge reranker",
                "modelName": "qwen3-rerank",
                "baseUrl": "",
                "apiKey": "secret",
                "capability": "rerank",
            },
            provider,
        )
        self.assertEqual(result["capabilities"], ["rerank"])
        self.assertFalse(result["is_default"])

    def test_rejects_unsupported_capability(self) -> None:
        provider = {
            "_id": "507f1f77bcf86cd799439011",
            "provider_type": "openai_compatible",
            "default_base_url": "https://api.example.com/v1",
        }
        with self.assertRaisesRegex(SetupModelError, "Unsupported model capability"):
            _normalize_payload(
                {
                    "modelName": "unknown-model",
                    "apiKey": "secret",
                    "capability": "audio",
                },
                provider,
            )

    async def test_embedding_inspection_preserves_detected_dimension(self) -> None:
        provider = {
            "_id": "507f1f77bcf86cd799439011",
            "status": "active",
            "provider_type": "openai_compatible",
            "default_base_url": "https://api.example.com/v1",
        }
        payload = {
            "providerId": str(provider["_id"]),
            "displayName": "Knowledge embedding",
            "modelName": "embedding-model",
            "baseUrl": provider["default_base_url"],
            "apiKey": "secret",
            "capability": "embedding",
        }
        with (
            patch("app.services.setup_model.find_provider_by_id", AsyncMock(return_value=provider)),
            patch(
                "app.services.setup_model.probe_knowledge_model_details",
                return_value=SetupKnowledgeProbeResult(message="ok", dimension=1024),
            ),
        ):
            result = await inspect_setup_model(payload)
        self.assertEqual(result.dimension, 1024)
        self.assertEqual(result.message, "ok")

    async def test_temporary_model_is_deleted_after_failed_test(self) -> None:
        provider = {
            "_id": "507f1f77bcf86cd799439011",
            "status": "active",
            "provider_type": "openai_compatible",
            "default_base_url": "https://api.example.com/v1",
        }
        payload = {
            "providerId": str(provider["_id"]),
            "displayName": "Default",
            "modelName": "example-chat",
            "baseUrl": provider["default_base_url"],
            "apiKey": "secret",
        }
        delete = AsyncMock(return_value=True)
        with (
            patch("app.services.setup_model.find_provider_by_id", AsyncMock(return_value=provider)),
            patch("app.services.setup_model.create_instance", AsyncMock(return_value="507f1f77bcf86cd799439012")),
            patch("app.services.setup_model.run_saved_model_test", AsyncMock(return_value=(False, "connection failed"))),
            patch("app.services.setup_model.delete_instance", delete),
        ):
            with self.assertRaisesRegex(SetupModelError, "connection failed"):
                await test_setup_model(payload)
        delete.assert_awaited_once()
