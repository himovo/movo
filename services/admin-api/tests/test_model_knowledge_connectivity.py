from __future__ import annotations

from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.api.routes.model_knowledge_tests import (
    KnowledgeModelTestPayload,
    test_knowledge_model_instance as run_knowledge_model_test_route,
)
from app.services.model_knowledge_connectivity import (
    ModelKnowledgeConnectivityError,
    resolve_knowledge_test_capability,
    run_saved_knowledge_model_test,
)


class ModelKnowledgeCapabilityTests(TestCase):
    def test_resolves_requested_embedding_capability(self) -> None:
        instance = {"capabilities": ["chat", "embedding"]}
        self.assertEqual(resolve_knowledge_test_capability(instance, "embedding"), "embedding")

    def test_rejects_capability_not_configured_on_model(self) -> None:
        with self.assertRaisesRegex(ModelKnowledgeConnectivityError, "不支持能力"):
            resolve_knowledge_test_capability({"capabilities": ["embedding"]}, "rerank")


class SavedKnowledgeModelTests(IsolatedAsyncioTestCase):
    async def test_embedding_uses_saved_configuration_and_returns_dimension(self) -> None:
        instance = {
            "status": "active",
            "capabilities": ["embedding"],
            "base_url": "https://models.example/v1",
            "model_name": "embedding-model",
            "api_key_encrypted": "encrypted",
            "api_version": "",
        }
        provider = {"provider_type": "openai_compatible"}
        with (
            patch("app.services.model_knowledge_connectivity.decrypt_secret", return_value="secret"),
            patch(
                "app.services.model_knowledge_connectivity.probe_knowledge_model_details",
                side_effect=lambda model, _provider: _probe_result(model),
            ),
        ):
            result = await run_saved_knowledge_model_test(instance, provider, capability="embedding")
        self.assertEqual(result.dimension, 3)

    async def test_disabled_model_is_not_probed(self) -> None:
        instance = {"status": "disabled", "capabilities": ["embedding"]}
        with self.assertRaisesRegex(ModelKnowledgeConnectivityError, "已禁用"):
            await run_saved_knowledge_model_test(instance, {}, capability="embedding")


def _probe_result(model: dict[str, object]):
    from app.services.setup_model_probe import SetupKnowledgeProbeResult

    assert model["capabilities"] == ["embedding"]
    assert model["api_key"] == "secret"
    return SetupKnowledgeProbeResult(message="Embedding connection succeeded (3 dimensions).", dimension=3)


class KnowledgeModelRouteTests(IsolatedAsyncioTestCase):
    async def test_success_marks_saved_model_healthy(self) -> None:
        from app.services.setup_model_probe import SetupKnowledgeProbeResult

        instance = {"provider_id": "507f1f77bcf86cd799439011"}
        update_health = AsyncMock()
        with (
            patch(
                "app.api.routes.model_knowledge_tests.find_instance_by_id",
                AsyncMock(return_value=instance),
            ),
            patch(
                "app.api.routes.model_knowledge_tests.find_provider_by_id",
                AsyncMock(return_value={"provider_type": "openai_compatible"}),
            ),
            patch(
                "app.api.routes.model_knowledge_tests.run_saved_knowledge_model_test",
                AsyncMock(return_value=SetupKnowledgeProbeResult(message="ok", dimension=1024)),
            ),
            patch("app.api.routes.model_knowledge_tests.update_instance_health", update_health),
        ):
            result = await run_knowledge_model_test_route(
                "507f1f77bcf86cd799439012",
                KnowledgeModelTestPayload(capability="embedding"),
                {"main_id": "tenant"},
            )
        self.assertTrue(result["success"])
        self.assertEqual(result["dimension"], 1024)
        update_health.assert_awaited_once_with("507f1f77bcf86cd799439012", "tenant", "healthy", "")

    async def test_probe_failure_marks_saved_model_failed(self) -> None:
        instance = {"provider_id": "507f1f77bcf86cd799439011"}
        update_health = AsyncMock()
        with (
            patch(
                "app.api.routes.model_knowledge_tests.find_instance_by_id",
                AsyncMock(return_value=instance),
            ),
            patch(
                "app.api.routes.model_knowledge_tests.find_provider_by_id",
                AsyncMock(return_value={"provider_type": "openai_compatible"}),
            ),
            patch(
                "app.api.routes.model_knowledge_tests.run_saved_knowledge_model_test",
                AsyncMock(side_effect=ModelKnowledgeConnectivityError("upstream failed")),
            ),
            patch("app.api.routes.model_knowledge_tests.update_instance_health", update_health),
        ):
            result = await run_knowledge_model_test_route(
                "507f1f77bcf86cd799439012",
                KnowledgeModelTestPayload(capability="rerank"),
                {"main_id": "tenant"},
            )
        self.assertFalse(result["success"])
        self.assertEqual(result["message"], "upstream failed")
        update_health.assert_awaited_once_with(
            "507f1f77bcf86cd799439012", "tenant", "failed", "upstream failed"
        )
