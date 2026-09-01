from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.llm.types import Message, Role


MAX_USER_REQUEST_CHARS = 20000
MAX_FACTS = 48
MAX_TEXT_CHARS = 500


class UserRequestFact(BaseModel):
    text: str = Field(default="", description="Near-verbatim business fact explicitly stated by the user.")
    evidence_span: str = Field(default="", description="Exact or near-exact source span from the current user request.")
    source: str = Field(default="current_user_request")
    confidence: str = Field(default="user_provided")


class UserRequestExtraction(BaseModel):
    facts: List[UserRequestFact] = Field(default_factory=list)
    instructions: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    uncertain_or_subjective: List[str] = Field(default_factory=list)


def _clean_text(value: Any, *, limit: int = 0) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if limit and len(text) > limit:
        return text[:limit].rstrip()
    return text


def _strip_embedded_source_sections(user_request: str) -> str:
    text = str(user_request or "").strip()
    if not text:
        return ""
    for marker in (
        "[文档Markdown]",
        "[文档语义摘要]",
        "[上传文档]",
        "[SOURCE_DOCUMENT]",
        "<SOURCE_DOCUMENT>",
        "[多模态识别结果]",
        "[多模态结构化事实]",
    ):
        idx = text.find(marker)
        if idx >= 0:
            text = text[:idx].strip()
    return text[:MAX_USER_REQUEST_CHARS].strip()


def _span_supported(source_text: str, text: str, span: str) -> bool:
    source_compact = _clean_text(source_text)
    text_compact = _clean_text(text)
    span_compact = _clean_text(span)
    if not source_compact:
        return False
    if span_compact and span_compact in source_compact:
        return True
    if text_compact and text_compact in source_compact:
        return True
    return False


def _coerce_valid_facts(extraction: UserRequestExtraction, *, source_text: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    for raw in list(extraction.facts or []):
        text = _clean_text(raw.text, limit=MAX_TEXT_CHARS)
        span = _clean_text(raw.evidence_span, limit=MAX_TEXT_CHARS)
        if not text and span:
            text = span
        if not text or not span:
            continue
        if not _span_supported(source_text, text, span):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "text": text,
                "evidence_span": span,
                "source": "current_user_request",
                "confidence": "user_provided",
            }
        )
        if len(out) >= MAX_FACTS:
            break
    return out


def _merge_user_facts_into_bundle(
    *,
    bundle: Dict[str, Any],
    facts: List[Dict[str, str]],
    extraction: UserRequestExtraction,
) -> Dict[str, Any]:
    if not facts:
        return dict(bundle or {})

    out = dict(bundle or {})
    existing_structured = [
        dict(item)
        for item in list(out.get("user_request_facts") or [])
        if isinstance(item, dict) and _clean_text(item.get("text"))
    ]
    existing_by_text = {_clean_text(item.get("text")).lower() for item in existing_structured}
    merged_structured = list(existing_structured)
    for fact in facts:
        key = _clean_text(fact.get("text")).lower()
        if key and key not in existing_by_text:
            existing_by_text.add(key)
            merged_structured.append(dict(fact))
    out["user_request_facts"] = merged_structured[:MAX_FACTS]

    confirmed_existing = [_clean_text(item, limit=MAX_TEXT_CHARS) for item in list(out.get("confirmed_facts") or [])]
    confirmed_existing = [item for item in confirmed_existing if item]
    user_fact_lines = [f"用户提供事实：{fact['text']}" for fact in out["user_request_facts"] if _clean_text(fact.get("text"))]

    seen_confirmed: set[str] = set()
    confirmed: List[str] = []
    for item in [*user_fact_lines, *confirmed_existing]:
        key = _clean_text(item).lower()
        if not key or key in seen_confirmed:
            continue
        seen_confirmed.add(key)
        confirmed.append(item)
    out["confirmed_facts"] = confirmed[:72]

    constraints = [_clean_text(item, limit=240) for item in list(extraction.constraints or []) if _clean_text(item)]
    instructions = [_clean_text(item, limit=240) for item in list(extraction.instructions or []) if _clean_text(item)]
    uncertain = [_clean_text(item, limit=240) for item in list(extraction.uncertain_or_subjective or []) if _clean_text(item)]
    if constraints:
        out["user_request_constraints"] = list(dict.fromkeys(constraints))[:16]
    if instructions:
        out["user_request_instructions"] = list(dict.fromkeys(instructions))[:16]
    if uncertain:
        out["user_request_uncertain_or_subjective"] = list(dict.fromkeys(uncertain))[:12]
    return out


async def enrich_evidence_with_user_request_facts(
    *,
    llm: Any,
    evidence_bundle: Dict[str, Any] | None,
    user_request: str,
    task_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Promote explicit current-turn user facts into the existing evidence bundle.

    The extractor classifies the user request but only `facts` enter
    confirmed_facts. Every accepted fact must be anchored to a source span from
    the current request; unsupported LLM output is discarded.
    """
    base = dict(evidence_bundle or {}) if isinstance(evidence_bundle, dict) else {}
    source_text = _strip_embedded_source_sections(user_request)
    if not source_text or llm is None:
        return base

    system = (
        "You extract explicit user-provided facts from the CURRENT user request.\n"
        "Return only information that is directly stated in the request.\n"
        "Classify content into facts, instructions, constraints, and uncertain_or_subjective.\n"
        "Facts are business/domain facts about entities, current state, quantities, dates, plans, problems, resources, limits, or known conditions.\n"
        "Instructions are things the user wants the assistant to do. Constraints are output/search/style limits.\n"
        "Do not infer, complete, verify, or invent facts. Do not treat writing requirements as facts.\n"
        "Every fact must include an evidence_span copied exactly or near-exactly from the current request.\n"
        "If a candidate fact cannot be anchored to a span, omit it."
    )
    payload = {
        "current_user_request": source_text,
        "task_context": dict(task_context or {}),
        "output_rules": {
            "facts_only_from_current_user_request": True,
            "fact_source": "current_user_request",
            "fact_confidence": "user_provided",
            "drop_facts_without_evidence_span": True,
        },
    }
    try:
        model = llm.with_structured_output(UserRequestExtraction, method="function_calling")
        result = await model.ainvoke(
            [
                Message(role=Role.SYSTEM, content=system),
                Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False, default=str)),
            ]
        )
        extraction = result if isinstance(result, UserRequestExtraction) else UserRequestExtraction.model_validate(result)
    except Exception:
        return base

    facts = _coerce_valid_facts(extraction, source_text=source_text)
    return _merge_user_facts_into_bundle(bundle=base, facts=facts, extraction=extraction)
