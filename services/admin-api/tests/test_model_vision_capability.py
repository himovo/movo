"""Vision enablement changes only the selected model's capability."""

import asyncio

from bson import ObjectId

from app.repositories import model_repository


def test_enable_vision_is_additive_and_scoped(monkeypatch) -> None:
    captured = {}

    class Collection:
        async def update_one(self, query, update):
            captured.update(query=query, update=update)
            return type("Result", (), {"matched_count": 1})()

    monkeypatch.setattr(model_repository, "get_db", lambda: {model_repository.INSTANCE_COLLECTION: Collection()})
    model_id = str(ObjectId())
    assert asyncio.run(model_repository.add_vision_capability(model_id, "tenant-a")) is True
    assert captured["query"] == {"_id": ObjectId(model_id), "main_id": "tenant-a"}
    assert captured["update"]["$addToSet"] == {"capabilities": "vision"}
    assert "api_key_encrypted" not in captured["update"].get("$set", {})
