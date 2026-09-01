from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from app.llm.types import Message, Role
from pydantic import BaseModel, Field

from app.llm.factory import get_llm_client
from app.llm.decision_turn import DecisionOutput, DecisionTurnSpec, invoke_structured_decision


_CONTENT_ARTIFACT_WHITELIST: Tuple[str, ...] = (
    "selected_article",
    "news_bundle",
    "article_seed",
    "fetched_body",
    "selected_content",
    "article_body",
    "source_article",
    "news_item",
)

_RUNTIME_RESCAN_FALLBACK_KEYS: Tuple[str, ...] = (
    "answer",
    "content",
    "markdown",
    "body",
)

_SUBJECT_WORKFLOW_PHRASES: Tuple[str, ...] = (
    "保存草稿",
    "保存为草稿",
    "创建笔记",
    "新建笔记",
    "笔记创建",
    "创作后台草稿",
    "draft note creation",
    "draft creation workflow",
    "create draft note",
    # System trace / pipeline status strings that show up in upstream
    # `answer` artifacts when a research / collection step finishes. Without
    # this filter, the subject resolver picks them up as the document title
    # (e.g. "Completed research_collection_skill: All steps in current
    # frame completed" appearing as the canonical subject of a market
    # analysis report).
    "completed research_collection_skill",
    "all steps in current frame completed",
    "current frame completed",
    "subagent n_s",
    "subagent succeeded",
    "graph completed",
    "step status: succeeded",
)

_MIN_BODY_CHARS_FOR_SHORT_CIRCUIT = 40


class SubjectResolutionDecision(DecisionOutput):
    status: str = "unresolved"
    canonical_subject: str = ""
    article_goal_hint: str = ""
    rationale: str = ""
    selection_confidence: float = 0.0
    candidate_subjects: List[str] = Field(default_factory=list)
    supporting_facts: List[str] = Field(default_factory=list)


class SubjectResolutionResolver:
    def __init__(self) -> None:
        self._llm = None

    async def resolve(
        self,
        *,
        user_query: str,
        tool_observations: List[Dict[str, Any]],
        document_context: Optional[Dict[str, Any]] = None,
        subject_source: Optional[Dict[str, Any]] = None,
        upstream_artifacts: Optional[Dict[str, Any]] = None,
    ) -> SubjectResolutionDecision:
        contract_decision = self._resolve_from_contract(
            subject_source=subject_source,
            upstream_artifacts=upstream_artifacts,
        )
        if contract_decision is not None:
            return contract_decision
        semantic = await self._semantic_resolve(
            user_query=user_query,
            tool_observations=tool_observations,
            document_context=document_context,
        )
        if isinstance(semantic, SubjectResolutionDecision):
            return semantic
        return self._fallback_resolve(
            user_query=user_query,
            tool_observations=tool_observations,
            document_context=document_context,
        )

    @staticmethod
    def _resolve_from_contract(
        *,
        subject_source: Optional[Dict[str, Any]],
        upstream_artifacts: Optional[Dict[str, Any]],
    ) -> Optional[SubjectResolutionDecision]:
        if not isinstance(subject_source, dict):
            return None
        if str(subject_source.get("kind") or "").strip() != "from_artifact":
            return None
        artifacts = dict(upstream_artifacts or {}) if isinstance(upstream_artifacts, dict) else {}
        if not artifacts:
            return None
        declared_key = str(subject_source.get("artifact_key") or "").strip()
        extracted = SubjectResolutionResolver._extract_content_from_artifacts(
            artifacts=artifacts,
            declared_key=declared_key,
        )
        if extracted is None:
            return None
        title, body, used_key = extracted
        if not SubjectResolutionResolver._has_min_content_validity(title=title, body=body):
            return None
        canonical = str(title or "").strip() or str(body or "").strip().split("\n", 1)[0][:80]
        canonical = canonical.strip(" 　\t\r\n\"'“”‘’")
        if not canonical:
            return None
        lowered = canonical.lower()
        if any(phrase in canonical or phrase in lowered for phrase in _SUBJECT_WORKFLOW_PHRASES):
            return None
        supporting = SubjectResolutionResolver._supporting_facts_from_body(body)
        candidates = [canonical]
        return SubjectResolutionDecision(
            status="resolved_from_artifact_contract",
            canonical_subject=canonical,
            article_goal_hint=SubjectResolutionResolver._compose_goal_hint(
                subject=canonical,
                supporting_facts=supporting,
            ),
            rationale=f"subject_source_contract:{used_key}",
            selection_confidence=0.9,
            candidate_subjects=candidates,
            supporting_facts=supporting[:4],
        )

    @staticmethod
    def _extract_content_from_artifacts(
        *,
        artifacts: Dict[str, Any],
        declared_key: str,
    ) -> Optional[Tuple[str, str, str]]:
        tried_keys: List[str] = []
        if declared_key:
            tried_keys.append(declared_key)
        for key in _CONTENT_ARTIFACT_WHITELIST:
            if key not in tried_keys:
                tried_keys.append(key)
        for key in _RUNTIME_RESCAN_FALLBACK_KEYS:
            if key not in tried_keys:
                tried_keys.append(key)
        for key in tried_keys:
            if key not in artifacts:
                continue
            title, body = SubjectResolutionResolver._title_body_from_value(artifacts.get(key))
            if title or body:
                return title, body, key
        return None

    @staticmethod
    def _title_body_from_value(value: Any) -> Tuple[str, str]:
        if value is None:
            return "", ""
        if isinstance(value, dict):
            title = str(value.get("title") or value.get("headline") or value.get("name") or "").strip()
            body_candidate = (
                value.get("body")
                or value.get("summary")
                or value.get("content")
                or value.get("markdown")
                or value.get("text")
                or value.get("abstract")
                or ""
            )
            body = str(body_candidate or "").strip()
            return title[:160], body
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return "", ""
            try:
                parsed = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                parsed = None
            if isinstance(parsed, dict):
                return SubjectResolutionResolver._title_body_from_value(parsed)
            return "", text
        return "", ""

    @staticmethod
    def _has_min_content_validity(*, title: str, body: str) -> bool:
        if str(title or "").strip():
            return True
        if len(str(body or "").strip()) >= _MIN_BODY_CHARS_FOR_SHORT_CIRCUIT:
            return True
        return False

    @staticmethod
    def _supporting_facts_from_body(body: str) -> List[str]:
        text = str(body or "").strip()
        if not text:
            return []
        segments = re.split(r"(?<=[。!?！？])\s*|\n+", text)
        out: List[str] = []
        for seg in segments:
            token = str(seg or "").strip()
            if len(token) >= 8 and token not in out:
                out.append(token[:180])
            if len(out) >= 4:
                break
        return out

    async def _semantic_resolve(
        self,
        *,
        user_query: str,
        tool_observations: List[Dict[str, Any]],
        document_context: Optional[Dict[str, Any]],
    ) -> SubjectResolutionDecision | None:
        payload = {
            "user_query": str(user_query or "")[:600],
            "observations": self._compact_observations(tool_observations),
            "document_context": self._compact_context(document_context),
        }
        system = (
            "Resolve the single subject that best serves the requested deliverable.\n"
            "Return strict JSON with fields:\n"
            "- status: resolved_single_subject | resolved_multi_candidate | unresolved\n"
            "- canonical_subject\n"
            "- article_goal_hint\n"
            "- rationale\n"
            "- selection_confidence\n"
            "- candidate_subjects[]\n"
            "- supporting_facts[]\n"
            "Rules:\n"
            "1) The subject may be a product, system, workflow, feature set, organization, protocol, or concrete external entity.\n"
            "2) Prefer selecting the most likely subject for THIS task over merely listing all possible meanings of a term.\n"
            "3) Use resolved_single_subject whenever one candidate is the best fit for the user's writing goal, even if other dictionary meanings exist.\n"
            "4) Use resolved_multi_candidate or unresolved only when the request/context truly does not allow a responsible best-fit choice.\n"
            "5) selection_confidence is a 0-1 score for how safe it is to write a definitive article around canonical_subject.\n"
            "6) article_goal_hint must tell the downstream writer what document to produce next, even if the deliverable is not an article.\n"
            "7) For resolved_single_subject, article_goal_hint must bind the writing to the resolved subject and 2-4 supporting facts.\n"
        )
        try:
            llm = self._llm or get_llm_client(streaming=False, stage="planning")
            parsed = await invoke_structured_decision(
                llm,
                SubjectResolutionDecision,
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False, default=str)),
                ],
                spec=DecisionTurnSpec(
                    locale="zh" if re.search(r"[\u4e00-\u9fff]", user_query) else "en",
                    turn_id="writing.subject_resolution",
                ),
            )
            if isinstance(parsed, SubjectResolutionDecision):
                return parsed
        except Exception:
            return None
        return None

    def _fallback_resolve(
        self,
        *,
        user_query: str,
        tool_observations: List[Dict[str, Any]],
        document_context: Optional[Dict[str, Any]],
    ) -> SubjectResolutionDecision:
        context_candidates = self._candidate_subjects_from_context(document_context)
        supporting_facts = self._supporting_facts_from_context(document_context)
        subject = context_candidates[0] if context_candidates else self._extract_subject(user_query)
        candidates = self._candidate_titles(tool_observations)
        merged_candidates: List[str] = []
        for item in context_candidates + candidates:
            token = str(item or "").strip()
            if token and token not in merged_candidates:
                merged_candidates.append(token)
        if len(candidates) == 1:
            canonical = candidates[0]
            return SubjectResolutionDecision(
                status="resolved_single_subject",
                canonical_subject=canonical,
                article_goal_hint=self._compose_goal_hint(subject=canonical, supporting_facts=supporting_facts),
                rationale="fallback_single_candidate",
                selection_confidence=0.74,
                candidate_subjects=merged_candidates[:5],
                supporting_facts=supporting_facts[:4],
            )
        if subject and len(merged_candidates) <= 1:
            return SubjectResolutionDecision(
                status="resolved_single_subject",
                canonical_subject=subject,
                article_goal_hint=self._compose_goal_hint(subject=subject, supporting_facts=supporting_facts),
                rationale="fallback_context_subject",
                selection_confidence=0.62,
                candidate_subjects=merged_candidates[:5],
                supporting_facts=supporting_facts[:4],
            )
        if subject:
            return SubjectResolutionDecision(
                status="resolved_single_subject",
                canonical_subject=subject,
                article_goal_hint=self._compose_goal_hint(subject=subject, supporting_facts=supporting_facts),
                rationale="fallback_best_fit_subject",
                selection_confidence=0.52,
                candidate_subjects=[subject, *[item for item in merged_candidates if item != subject]][:5],
                supporting_facts=supporting_facts[:4],
            )
        return SubjectResolutionDecision(
            status="unresolved" if len(merged_candidates) <= 1 else "resolved_multi_candidate",
            canonical_subject="",
            article_goal_hint=(
                f"先明确当前文档真正围绕的核心对象，再围绕“{subject or '该主题'}”写作，"
                "说明当前信息中仍存在的歧义、可核验线索和边界条件。"
            ),
            rationale="fallback_ambiguous_subject",
            selection_confidence=0.0,
            candidate_subjects=merged_candidates[:5],
            supporting_facts=supporting_facts[:4],
        )

    @staticmethod
    def _compact_context(document_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        raw = dict(document_context or {}) if isinstance(document_context, dict) else {}
        multimodal = raw.get("multimodal") if isinstance(raw.get("multimodal"), dict) else {}
        image_facts = multimodal.get("image_facts") if isinstance(multimodal.get("image_facts"), dict) else {}
        uploaded_assets = [dict(x) for x in list(multimodal.get("uploaded_assets") or []) if isinstance(x, dict)]
        documents = raw.get("documents") if isinstance(raw.get("documents"), dict) else {}
        parsed_documents = [dict(x) for x in list(documents.get("parsed_documents") or []) if isinstance(x, dict)]
        compact_assets: List[Dict[str, Any]] = []
        for item in uploaded_assets[:6]:
            compact_assets.append(
                {
                    "summary": str(item.get("summary") or "")[:180],
                    "page_area": str(item.get("page_area") or "")[:80],
                    "tags": [str(x).strip() for x in list(item.get("tags") or [])[:8] if str(x).strip()],
                }
            )
        compact_documents: List[Dict[str, Any]] = []
        for item in parsed_documents[:4]:
            profile = item.get("profile") if isinstance(item.get("profile"), dict) else {}
            compact_documents.append(
                {
                    "title": str(profile.get("title") or item.get("filename") or "")[:120],
                    "summary": str(profile.get("summary") or "")[:220],
                    "key_points": [str(x).strip() for x in list(profile.get("key_points") or [])[:6] if str(x).strip()],
                }
            )
        return {
            "content_form": str(raw.get("content_form") or "")[:40],
            "required_sections": [str(x).strip() for x in list(raw.get("required_sections") or [])[:8] if str(x).strip()],
            "goal_outcome": str(raw.get("goal_outcome") or "")[:240],
            "subject_candidates": [
                str(x).strip()
                for x in list(image_facts.get("subject_candidates") or image_facts.get("entities") or [])[:8]
                if str(x).strip()
            ],
            "ui_terms": [str(x).strip() for x in list(image_facts.get("ui_terms") or [])[:12] if str(x).strip()],
            "uploaded_assets": compact_assets,
            "documents": compact_documents,
        }

    @staticmethod
    def _candidate_subjects_from_context(document_context: Optional[Dict[str, Any]]) -> List[str]:
        raw = dict(document_context or {}) if isinstance(document_context, dict) else {}
        out: List[str] = []
        multimodal = raw.get("multimodal") if isinstance(raw.get("multimodal"), dict) else {}
        image_facts = multimodal.get("image_facts") if isinstance(multimodal.get("image_facts"), dict) else {}
        documents = raw.get("documents") if isinstance(raw.get("documents"), dict) else {}
        for token in list(image_facts.get("subject_candidates") or image_facts.get("entities") or [])[:8]:
            value = str(token or "").strip()
            if value and value not in out:
                out.append(value)
        for item in list(documents.get("parsed_documents") or [])[:4]:
            if not isinstance(item, dict):
                continue
            profile = item.get("profile") if isinstance(item.get("profile"), dict) else {}
            for token in [profile.get("title"), *(profile.get("subject_candidates") or [])]:
                value = str(token or "").strip()
                if value and value not in out:
                    out.append(value)
        for item in list(multimodal.get("uploaded_assets") or [])[:6]:
            if not isinstance(item, dict):
                continue
            for token in [item.get("page_area"), item.get("summary")]:
                value = str(token or "").strip()
                if value and value not in out:
                    out.append(value)
        goal_outcome = str(raw.get("goal_outcome") or "").strip()
        if goal_outcome:
            guess = SubjectResolutionResolver._extract_subject(goal_outcome)
            if guess and guess not in out:
                out.append(guess)
        return out[:5]

    @staticmethod
    def _supporting_facts_from_context(document_context: Optional[Dict[str, Any]]) -> List[str]:
        raw = dict(document_context or {}) if isinstance(document_context, dict) else {}
        multimodal = raw.get("multimodal") if isinstance(raw.get("multimodal"), dict) else {}
        documents = raw.get("documents") if isinstance(raw.get("documents"), dict) else {}
        out: List[str] = []
        image_facts = multimodal.get("image_facts") if isinstance(multimodal.get("image_facts"), dict) else {}
        for item in list((image_facts.get("images") or []))[:4]:
            if not isinstance(item, dict):
                continue
            page_area = str(item.get("page_area") or "").strip()
            flow = str(item.get("flow_relationship") or "").strip()
            if page_area:
                out.append(f"界面涉及：{page_area}")
            if flow:
                out.append(f"流程关联：{flow}")
        for item in list(multimodal.get("uploaded_assets") or [])[:4]:
            if not isinstance(item, dict):
                continue
            summary = str(item.get("summary") or "").strip()
            if summary and summary not in out:
                out.append(summary)
        for item in list(documents.get("parsed_documents") or [])[:3]:
            if not isinstance(item, dict):
                continue
            profile = item.get("profile") if isinstance(item.get("profile"), dict) else {}
            for token in [profile.get("summary"), *(profile.get("key_points") or [])[:3]]:
                value = str(token or "").strip()
                if value and value not in out:
                    out.append(value)
        return out[:6]

    @staticmethod
    def _compose_goal_hint(*, subject: str, supporting_facts: List[str]) -> str:
        facts = [str(x).strip() for x in list(supporting_facts or []) if str(x).strip()][:3]
        if facts:
            return f"围绕“{subject}”完成当前文档，全文保持主题一致，并优先锚定这些事实：{'；'.join(facts)}。"
        return f"围绕“{subject}”完成当前文档，保持所有章节和论证都服务于这个核心对象。"

    @staticmethod
    def _compact_observations(tool_observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        compacted: List[Dict[str, Any]] = []
        for item in list(tool_observations or [])[:10]:
            if not isinstance(item, dict):
                continue
            sources = []
            for src in list(item.get("sources") or [])[:6]:
                if not isinstance(src, dict):
                    continue
                sources.append(
                    {
                        "title": str(src.get("title") or src.get("name") or "")[:160],
                        "url": str(src.get("url") or src.get("source_url") or "")[:300],
                    }
                )
            compacted.append(
                {
                    "query": str(item.get("query") or "")[:160],
                    "summary": str(item.get("summary") or "")[:600],
                    "sources": sources,
                }
            )
        return compacted

    @staticmethod
    def _extract_subject(user_query: str) -> str:
        text = str(user_query or "").strip()
        if not text:
            return "该主题"
        for pattern in [
            r"“([^”]{2,40})”",
            r"\"([^\"]{2,40})\"",
        ]:
            m = re.search(pattern, text)
            if m:
                return str(m.group(1) or "").strip()
        for pattern in [
            r"介绍\s*([A-Za-z0-9._\-]+)\s*是(什么|啥)",
            r"介绍\s*“([^”]+)”\s*是(什么|啥)",
            r"介绍\s*\"([^\"]+)\"\s*是(什么|啥)",
        ]:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                return str(m.group(1) or "").strip()
        token = re.findall(r"[A-Za-z][A-Za-z0-9._\-]{2,}", text)
        if token:
            return token[0]
        return text[:24]

    @staticmethod
    def _candidate_titles(tool_observations: List[Dict[str, Any]]) -> List[str]:
        out: List[str] = []
        seen = set()
        for item in list(tool_observations or [])[:10]:
            if not isinstance(item, dict):
                continue
            for src in list(item.get("sources") or [])[:8]:
                if not isinstance(src, dict):
                    continue
                title = str(src.get("title") or src.get("name") or "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                out.append(title)
        return out
