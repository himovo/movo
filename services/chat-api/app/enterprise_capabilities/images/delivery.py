"""Adapt persisted image assets to the shared deliverable contract."""

import mimetypes
from pathlib import PurePosixPath
from time import time
from typing import Any


def image_document(asset: dict[str, Any]) -> dict[str, Any]:
    filename = PurePosixPath(asset["object_path"]).name
    return {
        "type": PurePosixPath(filename).suffix.lstrip(".").lower() or "image",
        "filename": filename,
        "title": asset["alt_text"],
        "url": asset["image_url"],
        "object_path": asset["object_path"],
        "image_model_id": str(asset.get("image_model_id") or ""),
        "content_type": mimetypes.guess_type(filename)[0] or "image/png",
    }


def image_delivery_event(document: dict[str, Any], *, message_id: str, action_id: str, index: int) -> dict[str, Any]:
    identity = f"{message_id}:{action_id}:image:{index}"
    return {
        "v": 3, "event_id": identity, "id": identity,
        "ts": int(time() * 1000), "type": "item.completed",
        "item_kind": "artifact", "item_id": identity,
        "parent_item_id": action_id, "revision": 1,
        "payload": {**document, "kind": document["type"]},
    }
