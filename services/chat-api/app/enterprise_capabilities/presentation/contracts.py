"""Business-level DSH contract for ASKAI's existing presentation pipeline."""

from __future__ import annotations

from typing import Any


def presentation_create_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "request": {
                "type": "string",
                "minLength": 1,
                "description": "Complete presentation brief in the user's language.",
            },
            "page_count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "description": "Exact slide count only when the user specified one.",
            },
            "audience": {"type": "string"},
            "design_intent": {"type": "string"},
            "required_sections": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "maxItems": 20,
            },
            "use_agenda": {"type": "boolean"},
            "grounding_mode": {
                "type": "string",
                "enum": ["hybrid", "strict", "free"],
            },
            "use_conversation_evidence": {
                "type": "boolean",
                "description": "Use relevant persisted evidence from prior turns when this deck depends on conversation history.",
            },
        },
        "required": ["request"],
        "additionalProperties": False,
    }


def presentation_create_output_schema() -> dict[str, Any]:
    # Keep to the strict portable subset supported by the DSH Runtime Host.
    artifact = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "const": "presentation_preview_bundle"},
            "object_path": {"type": "string"},
            "filename": {"type": "string"},
            "title": {"type": "string"},
            "bundle": {"type": "object"},
            "summary": {"type": "object"},
            "lifecycle": {"type": "string", "enum": ["final"]},
            "visibility": {"type": "string", "enum": ["user"]},
            "delivery_id": {"type": "string"},
        },
        "required": ["type", "object_path", "filename", "title", "bundle"],
        "additionalProperties": True,
    }
    acceptance = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["accepted", "rejected"]},
            "retry_allowed": {"type": "boolean"},
            "reasons": {"type": "array", "items": {"type": "string"}},
            "slide_count": {"type": "integer"},
            "requested_slide_count": {"type": "integer"},
            "editable": {"type": "boolean"},
        },
        "required": ["status", "retry_allowed", "reasons", "slide_count", "editable"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "accepted": {"type": "boolean"},
            "acceptance": acceptance,
            "artifact": artifact,
            "message": {"type": "string"},
        },
        "required": ["success", "accepted", "acceptance", "message"],
        "additionalProperties": False,
    }


def normalize_presentation_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    raw_count = arguments.get("page_count")
    page_count = max(1, min(50, int(raw_count))) if raw_count not in (None, "") else 0
    grounding = str(arguments.get("grounding_mode") or "hybrid").strip().lower()
    if grounding not in {"hybrid", "strict", "free"}:
        grounding = "hybrid"
    return {
        "request": str(arguments.get("request") or "").strip(),
        "page_count": page_count,
        "audience": str(arguments.get("audience") or "").strip(),
        "design_intent": str(arguments.get("design_intent") or "").strip(),
        "required_sections": [
            str(item).strip()
            for item in list(arguments.get("required_sections") or [])
            if str(item).strip()
        ][:20],
        "use_agenda": arguments.get("use_agenda"),
        "grounding_mode": grounding,
        "use_conversation_evidence": bool(arguments.get("use_conversation_evidence")),
    }


__all__ = [
    "normalize_presentation_arguments",
    "presentation_create_input_schema",
    "presentation_create_output_schema",
]
