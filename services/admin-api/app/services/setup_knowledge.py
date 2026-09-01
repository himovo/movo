from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.db import get_db


COLLECTION = "knowledge_document_settings"


async def configure_setup_knowledge_models(
    *,
    main_id: str,
    configured_models: list[tuple[dict[str, Any], str]],
    operator: str,
    embedding_dimension: int | None = None,
) -> None:
    by_capability = {
        str(payload.get("capability") or ""): (payload, instance_id)
        for payload, instance_id in configured_models
    }
    config: dict[str, Any] = {}
    embedding = by_capability.get("embedding")
    if embedding:
        config["embedding"] = {
            "provider": "model_center",
            "modelInstanceId": embedding[1],
            "dimension": int(embedding_dimension or 1536),
            "batchSize": 32,
            "timeoutSeconds": 30,
        }
    rerank = by_capability.get("rerank")
    if rerank:
        payload, instance_id = rerank
        config["retrieval"] = {
            "rerank": {
                "enabled": True,
                "provider": "model_center",
                "modelInstanceId": instance_id,
                "model": str(payload.get("modelName") or ""),
                "endpoint": str(payload.get("baseUrl") or ""),
                "topK": 20,
                "scoreThreshold": 0,
                "timeoutSeconds": 10,
                "fallbackPolicy": "return_vector_results",
            }
        }
    if not config:
        return
    now = datetime.now(timezone.utc)
    await get_db()[COLLECTION].update_one(
        {"main_id": main_id, "kind": "knowledge"},
        {
            "$set": {"config": config, "updated_by": operator, "updated_at": now},
            "$setOnInsert": {"main_id": main_id, "kind": "knowledge", "created_at": now},
        },
        upsert=True,
    )
