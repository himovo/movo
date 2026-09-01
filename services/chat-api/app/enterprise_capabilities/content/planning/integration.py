from __future__ import annotations

import re
from typing import Any, Dict, List

from app.enterprise_capabilities.content.planning.contracts import SectionFactSpec
from app.enterprise_capabilities.content.structure_roles import normalize_section_role


def _normalize_fact_specs(value: Any) -> List[Dict[str, Any]]:
    items = value if isinstance(value, list) else [value] if value else []
    out: List[Dict[str, Any]] = []
    seen = set()
    for idx, item in enumerate(items, start=1):
        if isinstance(item, dict):
            payload = dict(item)
        else:
            token = str(item or "").strip()
            if not token:
                continue
            payload = {
                "fact_id": f"fact_{idx}",
                "fact_type": "fact",
                "summary": token,
                "source_kind": "legacy_text",
                "source_ref": "",
                "raw_evidence": token,
            }
        fact = SectionFactSpec.model_validate(payload).model_dump()
        summary = str(fact.get("summary") or "").strip()
        if not summary or summary in seen:
            continue
        seen.add(summary)
        out.append(fact)
    return out


def _normalize_title_token(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    out: List[str] = []
    for ch in raw:
        if ch.isalnum() or "\u4e00" <= ch <= "\u9fff":
            out.append(ch)
    return "".join(out)


def _title_match_score(left: str, right: str) -> float:
    a = _normalize_title_token(left)
    b = _normalize_title_token(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.86
    a_set = set(a)
    b_set = set(b)
    overlap = len(a_set & b_set)
    return float(overlap) / float(max(len(a_set), len(b_set), 1))


def _best_planned_section(*, title: str, plan_sections: List[Dict[str, Any]], used_indices: set[int]) -> Dict[str, Any]:
    best_idx = -1
    best_score = 0.0
    for idx, item in enumerate(plan_sections):
        if idx in used_indices or not isinstance(item, dict):
            continue
        score = _title_match_score(title, str(item.get("title") or ""))
        if score > best_score:
            best_score = score
            best_idx = idx
    if best_idx >= 0 and best_score >= 0.45:
        used_indices.add(best_idx)
        return dict(plan_sections[best_idx] or {})
    return {}


def build_body_plan(*, structure: Dict[str, Any], content_plan: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    plan = dict(content_plan or {})

    plan_sections = [item for item in list(plan.get("sections") or []) if isinstance(item, dict)]
    raw_blocks = structure.get("blocks") if isinstance(structure.get("blocks"), list) else []
    body_sections: List[Dict[str, Any]] = []
    used_plan_indices: set[int] = set()

    if raw_blocks:
        for idx, item in enumerate(raw_blocks, start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or item.get("block_name") or "").strip()
            if not title:
                continue
            planned = _best_planned_section(title=title, plan_sections=plan_sections, used_indices=used_plan_indices)
            section_id = str((planned or {}).get("section_id") or f"s{idx}").strip() or f"s{idx}"
            target_words = int((planned or {}).get("target_words") or 0)
            body_sections.append(
                {
                    "section_id": section_id,
                    "title": title,
                    "role": normalize_section_role(str((planned or {}).get("role") or "").strip()),
                    "purpose": str((planned or {}).get("purpose") or item.get("objective") or item.get("purpose") or "").strip(),
                    "key_points": [str(x).strip() for x in list((planned or {}).get("key_points") or item.get("key_points") or []) if str(x).strip()][:8],
                    "evidence_focus": [str(x).strip() for x in list((planned or {}).get("evidence_focus") or item.get("evidence_focus") or []) if str(x).strip()][:8],
                    "must_cover_facts": _normalize_fact_specs((planned or {}).get("must_cover_facts"))[:12],
                    "allowed_claim_types": [str(x).strip() for x in list((planned or {}).get("allowed_claim_types") or []) if str(x).strip()][:8],
                    "disallowed_claim_types": [str(x).strip() for x in list((planned or {}).get("disallowed_claim_types") or []) if str(x).strip()][:8],
                    "open_questions": [str(x).strip() for x in list((planned or {}).get("open_questions") or []) if str(x).strip()][:8],
                    "target_words": target_words,
                }
            )
    else:
        required_blocks = [str(x).strip() for x in list(structure.get("required_blocks") or []) if str(x).strip()]
        for idx, title in enumerate(required_blocks, start=1):
            planned = _best_planned_section(title=title, plan_sections=plan_sections, used_indices=used_plan_indices)
            section_id = str((planned or {}).get("section_id") or f"s{idx}").strip() or f"s{idx}"
            target_words = int((planned or {}).get("target_words") or 0)
            body_sections.append(
                {
                    "section_id": section_id,
                    "title": title,
                    "role": normalize_section_role(str((planned or {}).get("role") or "").strip()),
                    "purpose": str((planned or {}).get("purpose") or "").strip(),
                    "key_points": [str(x).strip() for x in list((planned or {}).get("key_points") or []) if str(x).strip()][:8],
                    "evidence_focus": [str(x).strip() for x in list((planned or {}).get("evidence_focus") or []) if str(x).strip()][:8],
                    "must_cover_facts": _normalize_fact_specs((planned or {}).get("must_cover_facts"))[:12],
                    "allowed_claim_types": [str(x).strip() for x in list((planned or {}).get("allowed_claim_types") or []) if str(x).strip()][:8],
                    "disallowed_claim_types": [str(x).strip() for x in list((planned or {}).get("disallowed_claim_types") or []) if str(x).strip()][:8],
                    "open_questions": [str(x).strip() for x in list((planned or {}).get("open_questions") or []) if str(x).strip()][:8],
                    "target_words": target_words,
                }
            )

    out["sections"] = body_sections
    return out


def body_plan_titles(*, structure: Dict[str, Any], content_plan: Dict[str, Any]) -> List[str]:
    return [
        str(item.get("title") or "").strip()
        for item in list(build_body_plan(structure=structure, content_plan=content_plan).get("sections") or [])
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ]


def apply_content_plan_to_structure(*, structure: Dict[str, Any], content_plan: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(structure or {})
    planned_sections = [item for item in list(content_plan.get("sections") or []) if isinstance(item, dict)]
    if not planned_sections:
        return out
    out["blocks"] = [
        {
            "title": str(item.get("title") or "").strip(),
            "objective": str(item.get("purpose") or "").strip(),
            "key_points": [str(x).strip() for x in list(item.get("key_points") or []) if str(x).strip()][:8],
            "evidence_focus": [str(x).strip() for x in list(item.get("evidence_focus") or []) if str(x).strip()][:8],
            "visual_hint": str(item.get("visual_hint") or "none").strip().lower(),
        }
        for item in planned_sections
        if str(item.get("title") or "").strip()
    ]
    out["required_blocks"] = [
        str(item.get("title") or "").strip()
        for item in planned_sections
        if str(item.get("title") or "").strip()
    ]
    return out


def content_plan_titles(content_plan: Dict[str, Any]) -> List[str]:
    return [
        str(item.get("title") or "").strip()
        for item in list(content_plan.get("sections") or [])
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ]
