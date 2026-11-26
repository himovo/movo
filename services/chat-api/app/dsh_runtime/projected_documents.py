"""Preserve structured tool deliverables alongside workspace deliveries."""

from typing import Any


async def update_projection(messages: Any, scope: dict[str, Any], values: dict[str, Any]):
    """Preserve edits with compare-and-swap, including on older MongoDB servers."""
    if "documents" not in values:
        return await messages.update_one(scope, {"$set": values})
    for _ in range(5):
        row = await messages.find_one(scope, {"documents": 1})
        if row is None:
            raise LookupError("assistant_message_not_found")
        documents = list(values["documents"])
        paths = {document.get("object_path") for document in documents}
        for document in row.get("documents") or []:
            if document.get("source_object_path") and document.get("object_path") not in paths:
                documents.append(document)
                paths.add(document.get("object_path"))
        previous = row["documents"] if "documents" in row else {"$exists": False}
        result = await messages.update_one({**scope, "documents": previous},
            {"$set": {**values, "documents": documents}})
        if result.matched_count:
            return result
    raise RuntimeError("assistant_projection_changed_concurrently")


def projected_documents(events: list[dict[str, Any]], workspace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for event in events:
        if event.get("type") != "item.completed":
            continue
        payload = event.get("payload") or {}
        if event.get("item_kind") == "artifact":
            candidates.append(payload)
        elif event.get("item_kind") == "tool":
            candidates.extend(payload.get("artifacts") or [])
    candidates.extend(workspace)
    documents = {}
    for value in candidates:
        if not isinstance(value, dict):
            continue
        if str(value.get("lifecycle") or "").lower() == "intermediate" or str(value.get("visibility") or "").lower() == "internal":
            continue
        key = str(value.get("object_path") or "")
        if key:
            documents[key] = {**value, "type": value.get("type") or value.get("kind") or "document"}
    return list(documents.values())
