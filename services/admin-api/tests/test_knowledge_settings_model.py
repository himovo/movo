from app.api.routes.knowledge_settings import (
    KnowledgeSettingsPayload,
    _camel_config,
    default_knowledge_settings,
)


def test_embedding_has_no_environment_backed_default() -> None:
    assert default_knowledge_settings()["embedding"] == {
        "provider": "model_center",
        "modelInstanceId": "",
        "dimension": 1536,
        "batchSize": 32,
        "timeoutSeconds": 30,
    }
    assert default_knowledge_settings()["retrieval"]["rerank"]["provider"] == "model_center"
    assert default_knowledge_settings()["retrieval"]["rerank"]["modelInstanceId"] == ""
    assert default_knowledge_settings()["retrieval"]["rerank"]["model"] == ""
    assert default_knowledge_settings()["retrieval"]["rerank"]["endpoint"] == ""


def test_legacy_embedding_provider_is_migrated_to_model_center() -> None:
    migrated = _camel_config({
        "embedding": {
            "provider": "default_azure",
            "modelInstanceId": "instance-1",
        }
    })
    payload = KnowledgeSettingsPayload.model_validate(migrated)

    assert payload.embedding.provider == "model_center"
    assert payload.embedding.modelInstanceId == "instance-1"


def test_legacy_rerank_provider_is_migrated_to_model_center() -> None:
    migrated = _camel_config({
        "retrieval": {
            "rerank": {
                "enabled": True,
                "provider": "dashscope_qwen",
                "modelInstanceId": "rerank-1",
            }
        }
    })
    payload = KnowledgeSettingsPayload.model_validate(migrated)

    assert payload.retrieval.rerank.provider == "model_center"
    assert payload.retrieval.rerank.modelInstanceId == "rerank-1"
