from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any, Dict, Mapping, Type

_KIND = "__checkpoint_kind__"


def encode_checkpoint_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            _KIND: "dataclass",
            "type": type(value).__name__,
            "value": {
                item.name: encode_checkpoint_value(getattr(value, item.name))
                for item in fields(value)
            },
        }
    if isinstance(value, list):
        return [encode_checkpoint_value(item) for item in value]
    if isinstance(value, tuple):
        return {_KIND: "tuple", "items": [encode_checkpoint_value(item) for item in value]}
    if isinstance(value, set):
        return {_KIND: "set", "items": [encode_checkpoint_value(item) for item in value]}
    if isinstance(value, dict):
        if all(isinstance(key, str) for key in value):
            return {key: encode_checkpoint_value(item) for key, item in value.items()}
        return {
            _KIND: "mapping",
            "items": [
                [encode_checkpoint_value(key), encode_checkpoint_value(item)]
                for key, item in value.items()
            ],
        }
    raise TypeError(f"unsupported checkpoint value: {type(value).__name__}")


def decode_checkpoint_value(value: Any, *, dataclasses: Mapping[str, Type[Any]] | None = None) -> Any:
    registry = dict(dataclasses or {})
    if isinstance(value, list):
        return [decode_checkpoint_value(item, dataclasses=registry) for item in value]
    if not isinstance(value, dict):
        return value
    kind = value.get(_KIND)
    if kind == "tuple":
        return tuple(decode_checkpoint_value(item, dataclasses=registry) for item in value.get("items") or [])
    if kind == "set":
        return set(decode_checkpoint_value(item, dataclasses=registry) for item in value.get("items") or [])
    if kind == "mapping":
        return {
            decode_checkpoint_value(pair[0], dataclasses=registry): decode_checkpoint_value(pair[1], dataclasses=registry)
            for pair in value.get("items") or []
            if isinstance(pair, list) and len(pair) == 2
        }
    if kind == "dataclass":
        cls = registry.get(str(value.get("type") or ""))
        payload = decode_checkpoint_value(value.get("value") or {}, dataclasses=registry)
        return cls(**payload) if cls is not None and isinstance(payload, dict) else payload
    return {key: decode_checkpoint_value(item, dataclasses=registry) for key, item in value.items()}
