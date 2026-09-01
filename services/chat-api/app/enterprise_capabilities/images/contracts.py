"""Provider-neutral DSH contract for ASKAI-managed image generation."""

from __future__ import annotations

from typing import Any


def image_generation_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "images": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "minLength": 1},
                        "alt_text": {"type": "string"},
                        "placement_hint": {"type": "string"},
                    },
                    "required": ["prompt"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["images"],
        "additionalProperties": False,
    }


def image_generation_output_schema() -> dict[str, Any]:
    # DSH strict output schemas intentionally use its portable subset only.
    asset = {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
            "image_url": {"type": "string"},
            "object_path": {"type": "string"},
            "markdown": {"type": "string"},
            "alt_text": {"type": "string"},
            "placement_hint": {"type": "string"},
        },
        "required": ["index", "image_url", "object_path", "markdown", "alt_text"],
        "additionalProperties": False,
    }
    failure = {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
            "error": {"type": "string"},
        },
        "required": ["index", "error"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "status": {"type": "string", "enum": ["completed", "partial_success", "failed"]},
            "requested_count": {"type": "integer"},
            "generated_count": {"type": "integer"},
            "assets": {"type": "array", "items": asset},
            "failures": {"type": "array", "items": failure},
            "continuation_required": {"type": "boolean"},
            "message": {"type": "string"},
        },
        "required": [
            "success", "status", "requested_count", "generated_count",
            "assets", "failures", "continuation_required", "message",
        ],
        "additionalProperties": False,
    }


__all__ = ["image_generation_input_schema", "image_generation_output_schema"]
