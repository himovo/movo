"""Lossless JSON fields for arbitrary tool data stored in MongoDB."""

from __future__ import annotations

import json
from typing import Any


def encode_json_field(value: Any) -> str:
    """Encode untrusted nested data without exposing its keys to BSON semantics."""
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def decode_json_field(value: Any, *, default: Any) -> Any:
    if not isinstance(value, str) or not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def store_json_field(document: dict[str, Any], field: str) -> dict[str, Any]:
    """Move one arbitrary field into a lossless, BSON-safe JSON string."""
    result = dict(document)
    result[f"{field}_json"] = encode_json_field(result.pop(field, {}))
    return result


def restore_json_field(document: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(document)
    encoded = result.pop(f"{field}_json", None)
    if encoded is not None:
        result[field] = decode_json_field(encoded, default=result.get(field, {}))
    return result


__all__ = ["decode_json_field", "encode_json_field", "restore_json_field", "store_json_field"]
