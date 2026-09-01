from __future__ import annotations

from typing import Any, Dict, List


def _clip(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _string_list(values: Any, *, limit: int | None, item_chars: int) -> List[str]:
    out: List[str] = []
    items = list(values or [])
    if limit is not None:
        items = items[:limit]
    for item in items:
        text = _clip(item, item_chars)
        if text and text not in out:
            out.append(text)
    return out


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except Exception:
        return default


def compact_output_spec_for_profile(output_spec: Dict[str, Any]) -> Dict[str, Any]:
    spec = dict(output_spec or {}) if isinstance(output_spec, dict) else {}
    task_contract = spec.get("task_contract") if isinstance(spec.get("task_contract"), dict) else {}
    content_task_spec = spec.get("content_task_spec") if isinstance(spec.get("content_task_spec"), dict) else {}
    prompt_contract = spec.get("prompt_contract") if isinstance(spec.get("prompt_contract"), dict) else {}
    compose_profile = spec.get("compose_profile") if isinstance(spec.get("compose_profile"), dict) else {}
    documents = spec.get("documents") if isinstance(spec.get("documents"), dict) else {}
    multimodal = spec.get("multimodal") if isinstance(spec.get("multimodal"), dict) else {}

    parsed_documents: List[Dict[str, Any]] = []
    for item in list(documents.get("parsed_documents") or [])[:4]:
        if not isinstance(item, dict):
            continue
        profile = item.get("profile") if isinstance(item.get("profile"), dict) else {}
        parsed_documents.append(
            {
                "asset_id": _clip(item.get("asset_id"), 80),
                "filename": _clip(item.get("filename"), 160),
                "parse_status": _clip(item.get("parse_status"), 32),
                "markdown_chars": int(item.get("markdown_chars") or len(str(item.get("markdown") or ""))),
                "inline_mode": _clip(item.get("inline_mode"), 40),
                "embedded_image_count": len(list(item.get("embedded_images") or [])),
                "profile": {
                    "title": _clip(profile.get("title"), 160),
                    "summary": _clip(profile.get("summary"), 900),
                    "key_points": _string_list(profile.get("key_points"), limit=8, item_chars=220),
                    "section_outline": _string_list(profile.get("section_outline"), limit=10, item_chars=160),
                },
                "chunk_briefs": _string_list(item.get("chunk_briefs"), limit=6, item_chars=260),
            }
        )

    uploaded_assets: List[Dict[str, Any]] = []
    for item in list(multimodal.get("uploaded_assets") or [])[:16]:
        if not isinstance(item, dict):
            continue
        uploaded_assets.append(
            {
                "asset_id": _clip(item.get("asset_id"), 90),
                "source": _clip(item.get("source"), 60),
                "filename": _clip(item.get("filename"), 140),
                "summary": _clip(item.get("summary"), 260),
                "page_area": _clip(item.get("page_area"), 120),
                "tags": _string_list(item.get("tags"), limit=8, item_chars=60),
                "paragraph_index": item.get("paragraph_index"),
                "source_order": item.get("source_order"),
                "has_path": bool(_clip(item.get("path"), 20)),
            }
        )

    goal = content_task_spec.get("goal") if isinstance(content_task_spec.get("goal"), dict) else {}
    medium = content_task_spec.get("medium") if isinstance(content_task_spec.get("medium"), dict) else {}
    structure = content_task_spec.get("structure") if isinstance(content_task_spec.get("structure"), dict) else {}
    quality = content_task_spec.get("quality_targets") if isinstance(content_task_spec.get("quality_targets"), dict) else {}
    visual_plan = content_task_spec.get("visual_plan") if isinstance(content_task_spec.get("visual_plan"), dict) else {}

    return {
        "type": _clip(spec.get("type"), 40),
        "formats": _string_list(spec.get("formats"), limit=6, item_chars=20),
        "pipeline_intent": _clip(spec.get("pipeline_intent") or spec.get("intent"), 60),
        "inherited_user_request": _clip(spec.get("inherited_user_request"), 2500),
        "required_blocks": _string_list(spec.get("required_blocks"), limit=12, item_chars=120),
        "task_contract": {
            "goal_intent": _clip(task_contract.get("goal_intent"), 80),
            "evidence_mode": _clip(task_contract.get("evidence_mode"), 40),
            "selected_mode": _clip(task_contract.get("selected_mode") or task_contract.get("deliverable_mode"), 80),
            "execution_capabilities": _string_list(task_contract.get("execution_capabilities"), limit=10, item_chars=80),
            "post_actions": _string_list(task_contract.get("post_actions"), limit=8, item_chars=80),
        },
        "content_task_spec": {
            "execution_kind": _clip(content_task_spec.get("execution_kind"), 40),
            "kind": _clip(content_task_spec.get("kind"), 40),
            "goal": {
                "goal_type": _clip(goal.get("goal_type"), 80),
                "intent": _clip(goal.get("intent"), 180),
                "success_criteria": _string_list(goal.get("success_criteria"), limit=8, item_chars=160),
            },
            "medium": {
                "format": _clip(medium.get("format"), 80),
                "channel": _clip(medium.get("channel"), 80),
            },
            "structure": {
                "required_sections": _string_list(
                    structure.get("required_sections") or structure.get("required_blocks"),
                    limit=12,
                    item_chars=140,
                ),
            },
            "quality_targets": {
                "min_words": quality.get("min_words"),
                "max_words": quality.get("max_words"),
                "tone": _clip(quality.get("tone"), 120),
            },
            "visual_plan": {
                "needs_visuals": bool(visual_plan.get("needs_visuals")),
                "visual_count": visual_plan.get("visual_count"),
                "visual_requirements": _string_list(visual_plan.get("visual_requirements"), limit=8, item_chars=160),
            },
        },
        "prompt_contract": {
            "must_include": _string_list(prompt_contract.get("must_include"), limit=None, item_chars=160),
            "forbidden_patterns": _string_list(prompt_contract.get("forbidden_patterns"), limit=None, item_chars=160),
        },
        "compose_profile": compose_profile,
        "documents": {
            "enabled": bool(documents.get("enabled")),
            "count": _safe_int(documents.get("count"), len(parsed_documents)),
            "active_document_context": _clip(documents.get("active_document_context") or spec.get("active_document_context"), 1800),
            "active_document_markdown_chars": len(str(documents.get("active_document_markdown") or spec.get("active_document_markdown") or "")),
            "parsed_documents": parsed_documents,
        },
        "multimodal": {
            "enabled": bool(multimodal.get("enabled")),
            "image_count": _safe_int(multimodal.get("image_count"), 0),
            "embedded_document_image_count": _safe_int(multimodal.get("embedded_document_image_count"), 0),
            "uploaded_assets": uploaded_assets,
        },
    }
