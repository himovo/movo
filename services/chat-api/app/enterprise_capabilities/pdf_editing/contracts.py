from __future__ import annotations

from copy import deepcopy
from typing import Any


def pdf_retain_pages_input_schema(artifact_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "artifact": deepcopy(artifact_schema),
            "keep_pages": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "One-based source PDF page numbers selected by the agent after inspecting the document. "
                    "The tool preserves their original source order and does not rewrite page content."
                ),
            },
            "filename": {
                "type": "string",
                "description": "Filename for the new derived PDF. The source PDF is never overwritten.",
            },
        },
        "required": ["artifact", "keep_pages"],
        "additionalProperties": False,
    }


def pdf_retain_pages_output_schema() -> dict[str, Any]:
    artifact = {
        "type": "object",
        "properties": {
            "object_path": {"type": "string"},
            "filename": {"type": "string"},
            "content_type": {"type": "string"},
            "size": {"type": "integer"},
            "lifecycle": {"type": "string"},
            "visibility": {"type": "string"},
        },
        "required": ["object_path", "filename", "content_type", "size"],
        "additionalProperties": True,
    }
    selection = {
        "type": "object",
        "properties": {
            "source_page_count": {"type": "integer"},
            "output_page_count": {"type": "integer"},
            "kept_pages": {"type": "array", "items": {"type": "integer"}},
            "removed_pages": {"type": "array", "items": {"type": "integer"}},
            "source_order_preserved": {"type": "boolean"},
            "source_unchanged": {"type": "boolean"},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "source_page_count",
            "output_page_count",
            "kept_pages",
            "removed_pages",
            "source_order_preserved",
            "source_unchanged",
            "warnings",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "artifact": artifact,
            "selection": selection,
        },
        "required": ["success", "artifact", "selection"],
        "additionalProperties": False,
    }


__all__ = ["pdf_retain_pages_input_schema", "pdf_retain_pages_output_schema"]
