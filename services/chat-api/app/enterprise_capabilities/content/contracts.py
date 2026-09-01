from __future__ import annotations

from typing import Any


CONTENT_FORMS = (
    "article", "report", "proposal", "plan", "brief", "manual", "guide", "whitepaper",
)


def content_production_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "request": {"type": "string", "minLength": 1},
            "content_form": {"type": "string", "enum": list(CONTENT_FORMS)},
            "audience": {"type": "string"},
            "tone": {"type": "string"},
            "writing_mode": {"type": "string", "enum": ["hybrid", "evidence_bound", "creative"]},
            "required_sections": {
                "type": "array", "items": {"type": "string", "minLength": 1}, "maxItems": 18,
            },
            "min_words": {"type": "integer", "minimum": 100, "maximum": 30000},
            "max_words": {"type": "integer", "minimum": 100, "maximum": 30000},
            "visual_min": {"type": "integer", "minimum": 0, "maximum": 6},
            "visual_max": {"type": "integer", "minimum": 0, "maximum": 6},
            "writing_style_ref": {
                "type": "string",
                "description": "Opaque writing standard reference supplied by a MOVO workflow Skill.",
            },
        },
        "required": ["request"],
        "additionalProperties": False,
    }


def content_production_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "accepted": {"type": "boolean"},
            "acceptance": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["accepted", "rejected"]},
                    "retry_allowed": {"type": "boolean"},
                    "reasons": {"type": "array", "items": {"type": "string"}},
                    "quality_verdict": {"type": "string"},
                    "quality_status": {"type": "string"},
                    "character_count": {"type": "integer"},
                    "image_count": {"type": "integer"},
                    "required_visual_min": {"type": "integer"},
                },
                "required": ["status", "retry_allowed", "reasons"],
                "additionalProperties": True,
            },
            "markdown": {"type": "string"},
            "artifacts": {"type": "array"},
            "production": {"type": "object"},
            "message": {"type": "string"},
            "reused": {"type": "boolean"},
            "source_action_id": {"type": "string"},
        },
        "required": ["success", "accepted", "acceptance"],
        "additionalProperties": True,
    }


def normalized_content_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    minimum = max(100, int(arguments.get("min_words") or 800))
    maximum = max(minimum, int(arguments.get("max_words") or max(2200, minimum)))
    visual_min = max(0, min(6, int(arguments.get("visual_min") or 0)))
    visual_max = max(visual_min, min(6, int(arguments.get("visual_max") or visual_min)))
    return {
        "request": str(arguments.get("request") or "").strip(),
        "content_form": str(arguments.get("content_form") or "article").strip().lower(),
        "audience": str(arguments.get("audience") or "").strip(),
        "tone": str(arguments.get("tone") or "").strip(),
        "writing_mode": str(arguments.get("writing_mode") or "hybrid").strip().lower(),
        "required_sections": [str(x).strip() for x in list(arguments.get("required_sections") or []) if str(x).strip()][:18],
        "min_words": minimum,
        "max_words": maximum,
        "visual_min": visual_min,
        "visual_max": visual_max,
    }
