from __future__ import annotations

from typing import Any, Dict, List

from app.services.presentation.contracts import StoryDeckPlan


def extract_message_text(messages: List[Any]) -> str:
    parts: List[str] = []
    for item in list(messages or []):
        if isinstance(item, dict):
            role = str(item.get("role") or "").strip()
            content = item.get("content")
        else:
            role = str(getattr(item, "role", "") or "").strip()
            content = getattr(item, "content", "")
        if role != "user":
            continue
        if isinstance(content, str) and content.strip():
            parts.append(content.strip())
        elif isinstance(content, list):
            for entry in content:
                if isinstance(entry, dict) and str(entry.get("text") or "").strip():
                    parts.append(str(entry.get("text") or "").strip())
    return "\n\n".join(parts[-6:]).strip()


def extract_user_outline(*, messages: List[Any], output_spec: Dict[str, Any]) -> str:
    task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
    schema = task_spec.get("schema") if isinstance(task_spec.get("schema"), dict) else {}
    sections = [
        item for item in list(schema.get("section_specs") or [])
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ]
    if sections:
        lines: List[str] = []
        for index, item in enumerate(sections, start=1):
            line = f"{index}. {str(item.get('title') or '').strip()}"
            purpose = str(item.get("purpose") or "").strip()
            topics = [str(value).strip() for value in list(item.get("must_cover_topics") or []) if str(value).strip()]
            if purpose:
                line += f" | purpose={purpose}"
            if topics:
                line += f" | topics={', '.join(topics[:6])}"
            lines.append(line)
        return "\n".join(lines).strip()
    explicit = str(
        output_spec.get("outline")
        or output_spec.get("deck_outline")
        or output_spec.get("user_outline")
        or ""
    ).strip()
    return explicit or extract_message_text(messages)


def extract_generation_guidance(*, messages: List[Any], output_spec: Dict[str, Any]) -> str:
    policy = output_spec.get("compose_policy") if isinstance(output_spec.get("compose_policy"), dict) else {}
    chunks: List[str] = []
    for key in ("user_request", "deck_goal", "presentation_context", "target_audience"):
        value = str(output_spec.get(key) or "").strip()
        if value:
            chunks.append(f"{key}: {value}")
    writing = [str(value).strip() for value in list(policy.get("writing_instructions") or []) if str(value).strip()]
    sections = [str(value).strip() for value in list(policy.get("required_sections") or []) if str(value).strip()]
    if writing:
        chunks.append(f"writing_instructions: {' | '.join(writing[:12])}")
    if sections:
        chunks.append(f"required_sections: {' | '.join(sections[:12])}")
    user_text = extract_message_text(messages)
    if user_text:
        chunks.append(f"user_messages: {user_text}")
    return "\n".join(chunks).strip()


def story_payload(story_plan: StoryDeckPlan) -> Dict[str, Any]:
    return {
        "deck_id": story_plan.deck_id,
        "deck_goal": story_plan.deck_goal,
        "target_audience": story_plan.target_audience,
        "presentation_context": story_plan.presentation_context,
        "language": story_plan.language,
        "narrative_outline": list(story_plan.narrative_outline or []),
        "pages": [
            {
                "page_id": page.page_id,
                "page_index": page.page_index,
                "page_type": page.page_type,
                "page_intent": page.page_intent,
                "communication_goal": page.communication_goal,
                "key_message": page.key_message,
                "visual_intent": page.visual_intent,
                "narrative_role": page.narrative_role,
                "density_level": page.density_level,
            }
            for page in list(story_plan.pages or [])
        ],
    }


__all__ = [
    "extract_generation_guidance",
    "extract_message_text",
    "extract_user_outline",
    "story_payload",
]
