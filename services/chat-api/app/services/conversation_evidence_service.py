from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from bson import ObjectId
from pydantic import BaseModel, Field

from app.core.db import get_db
from app.core.tenant import add_main_scope, resolve_main_id
from app.llm.factory import get_llm_client
from app.llm.types import Message, Role
from app.enterprise_capabilities.evidence.foundation import normalize_evidence_bundle


logger = logging.getLogger(__name__)


class ConversationEvidenceSelection(BaseModel):
    selected_seqs: List[int] = Field(default_factory=list)
    canonical_subject: str = ""
    rationale: str = ""
    sufficient: bool = False


class ConversationEvidenceUnavailable(LookupError):
    def __init__(self, reason: str, *, details: Dict[str, Any] | None = None) -> None:
        self.reason = str(reason or "conversation_evidence_unavailable")
        self.details = dict(details or {})
        super().__init__(self.reason)


class ConversationEvidenceService:
    async def collect(
        self,
        *,
        session_id: str,
        user_id: str,
        main_id: str,
        current_request: str,
        evidence_requirement: str = "",
    ) -> Dict[str, Any]:
        rows = await self._load_rows(
            session_id=session_id,
            user_id=user_id,
            main_id=main_id,
        )
        prior_rows = self._exclude_current_request(rows, current_request=current_request)
        if not prior_rows:
            raise ConversationEvidenceUnavailable(
                "No prior conversation messages are available",
                details={"reason": "no_prior_messages"},
            )

        selection: ConversationEvidenceSelection | None = None
        selected: List[Dict[str, Any]] = []
        for attempt in range(1, 3):
            selection = await self._select_rows(
                rows=prior_rows,
                current_request=current_request,
                evidence_requirement=evidence_requirement,
                attempt=attempt,
            )
            selected_seq_set = {
                int(seq)
                for seq in list(selection.selected_seqs or [])
                if int(seq) > 0
            }
            selected = [
                row
                for row in prior_rows
                if int(row.get("seq") or 0) in selected_seq_set
            ]
            logger.info(
                "conversation evidence selection completed",
                extra={
                    "event": "conversation_evidence.selection_completed",
                    "attempt": attempt,
                    "candidate_seqs": [int(row.get("seq") or 0) for row in prior_rows],
                    "selected_seqs": sorted(selected_seq_set),
                    "resolved_seqs": [int(row.get("seq") or 0) for row in selected],
                    "sufficient": bool(selection.sufficient),
                    "rationale": str(selection.rationale or "")[:500],
                },
            )
            if selection.sufficient and selected:
                break
        if selection is None or not selection.sufficient or not selected:
            raise ConversationEvidenceUnavailable(
                "No relevant prior conversation evidence was resolved",
                details={
                    "reason": "relevant_evidence_unresolved",
                    "candidate_seqs": [int(row.get("seq") or 0) for row in prior_rows],
                    "selected_seqs": list(selection.selected_seqs or []) if selection else [],
                    "sufficient": bool(selection.sufficient) if selection else False,
                },
            )
        return self._build_artifacts(
            selected=selected,
            current_request=current_request,
            canonical_subject=selection.canonical_subject,
        )

    @staticmethod
    def _exclude_current_request(
        rows: List[Dict[str, Any]],
        *,
        current_request: str,
    ) -> List[Dict[str, Any]]:
        """Remove the persisted current user turn from prior-turn candidates."""
        normalized_request = " ".join(str(current_request or "").split())
        out = [dict(row) for row in rows]
        if not normalized_request:
            return out
        for index in range(len(out) - 1, -1, -1):
            row = out[index]
            if str(row.get("role") or "").strip().lower() != "user":
                continue
            normalized_content = " ".join(str(row.get("content") or "").split())
            if normalized_content == normalized_request:
                del out[index]
                break
        return out

    async def _load_rows(self, *, session_id: str, user_id: str, main_id: str) -> List[Dict[str, Any]]:
        try:
            oid = ObjectId(str(session_id))
        except Exception as exc:
            raise LookupError("Invalid conversation session id") from exc
        query = add_main_scope(
            {
                "session_id": oid,
                "user_id": str(user_id),
                "$or": [
                    {"message_type": "normal"},
                    {"runtime_owner": "dsh"},
                ],
            },
            resolve_main_id(main_id),
        )
        cursor = get_db().chat_messages.find(query).sort("seq", -1).limit(30)
        rows = await cursor.to_list(length=30)
        rows.reverse()
        return [dict(row) for row in rows]

    async def _select_rows(
        self,
        *,
        rows: List[Dict[str, Any]],
        current_request: str,
        evidence_requirement: str = "",
        attempt: int = 1,
    ) -> ConversationEvidenceSelection:
        candidates = []
        for row in rows:
            content = str(row.get("content") or "").strip()
            evidence = self._compact_evidence(list(row.get("evidence_bundles") or []))
            if not content and not evidence:
                continue
            candidates.append(
                {
                    "seq": int(row.get("seq") or 0),
                    "role": str(row.get("role") or ""),
                    "content": content[:2400],
                    "evidence": evidence,
                }
            )
        system = (
            "Select the prior conversation turns that provide the factual or source basis required by the current request. "
            "The current user turn has already been excluded from the candidates; never treat the current request itself as prior evidence. "
            "Resolve references semantically from the whole conversation, independent of wording or language. "
            "Do not select unrelated turns and do not add facts from model knowledge. "
            "Return selected_seqs, canonical_subject, rationale, and sufficient. "
            "Set sufficient=false when the conversation does not contain a responsible basis for the requested task."
        )
        llm = get_llm_client(streaming=False, stage="conversation_evidence", intent="task")
        model = llm.with_structured_output(ConversationEvidenceSelection, method="function_calling")
        parsed = await model.ainvoke(
            [
                Message(role=Role.SYSTEM, content=system),
                Message(
                    role=Role.USER,
                    content=json.dumps(
                        {
                            "current_request": current_request,
                            "evidence_requirement": evidence_requirement,
                            "selection_attempt": int(attempt),
                            "prior_conversation": candidates,
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                ),
            ]
        )
        if isinstance(parsed, ConversationEvidenceSelection):
            return parsed
        if isinstance(parsed, dict):
            return ConversationEvidenceSelection.model_validate(parsed)
        raise LookupError("Conversation evidence selection returned no result")

    @staticmethod
    def _compact_evidence(bundles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        compact: List[Dict[str, Any]] = []
        for bundle in bundles[:6]:
            if not isinstance(bundle, dict):
                continue
            compact.append(
                {
                    "confirmed_facts": [str(item)[:360] for item in list(bundle.get("confirmed_facts") or [])[:8]],
                    "sources": [
                        {
                            "title": str(item.get("title") or "")[:180],
                            "snippet": str(item.get("snippet") or item.get("content") or "")[:520],
                            "source_type": str(item.get("source_type") or ""),
                            "source_url": str(item.get("source_url") or "")[:800],
                        }
                        for item in list(bundle.get("sources") or bundle.get("results") or [])[:8]
                        if isinstance(item, dict)
                    ],
                }
            )
        return compact

    @classmethod
    def _build_artifacts(
        cls,
        *,
        selected: List[Dict[str, Any]],
        current_request: str,
        canonical_subject: str,
    ) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        facts: List[str] = []
        source_message_ids: List[str] = []
        selected_contents: List[str] = []
        fallback_rows: List[Dict[str, str]] = []
        seen_results: set[str] = set()

        for row in selected:
            message_id = str(row.get("message_id") or f"seq:{int(row.get('seq') or 0)}")
            source_message_ids.append(message_id)
            content = str(row.get("content") or "").strip()
            role = str(row.get("role") or "").strip().lower()
            if content:
                fallback_rows.append({"message_id": message_id, "role": role, "content": content})
            if str(row.get("role") or "").lower() == "assistant" and content:
                selected_contents.append(content)
            for bundle in list(row.get("evidence_bundles") or []):
                if not isinstance(bundle, dict):
                    continue
                facts.extend(str(item).strip() for item in list(bundle.get("confirmed_facts") or []) if str(item).strip())
                for source in list(bundle.get("sources") or bundle.get("results") or []):
                    if not isinstance(source, dict):
                        continue
                    result = {
                        "title": str(source.get("title") or "Conversation source"),
                        "summary": str(source.get("snippet") or source.get("summary") or source.get("content") or ""),
                        "content": str(source.get("content") or source.get("snippet") or source.get("summary") or ""),
                        "source": str(source.get("source_name") or source.get("source_type") or "conversation"),
                        "source_url": str(source.get("source_url") or ""),
                        "meta": {"conversation_message_id": message_id, "provenance": "persisted_evidence"},
                    }
                    key = "|".join([result["title"], result["source_url"], result["summary"][:120]])
                    if key not in seen_results and (result["summary"] or result["content"]):
                        seen_results.add(key)
                        results.append(result)

        if not results:
            for index, fallback in enumerate(fallback_rows, start=1):
                content = fallback["content"]
                role = fallback["role"]
                results.append(
                    {
                        "title": canonical_subject or f"Prior assistant response {index}",
                        "summary": content[:1200],
                        "content": content[:6000],
                        "source": "conversation",
                        "meta": {
                            "conversation_message_id": fallback["message_id"],
                            "provenance": "derived_assistant_summary" if role == "assistant" else "historical_user_statement",
                        },
                    }
                )

        bundle = normalize_evidence_bundle(
            {
                "query": current_request,
                "tools_used": ["conversation_history"],
                "results": results,
                "confirmed_facts": list(dict.fromkeys(facts)),
                "source_message_ids": list(dict.fromkeys(source_message_ids)),
                "source_scope": "conversation",
            }
        )
        body = "\n\n".join(selected_contents).strip()
        source_material = {
            "query": current_request,
            "source_scope": "conversation",
            "confirmed_facts": list(bundle.get("confirmed_facts") or []),
            "results": list(bundle.get("results") or []),
            "source_message_ids": list(bundle.get("source_message_ids") or []),
        }
        return {
            "source_material": source_material,
            "evidence_bundle": bundle,
            "selected_content": {
                "title": canonical_subject,
                "body": body,
                "source_message_ids": list(bundle.get("source_message_ids") or []),
            },
        }


conversation_evidence_service = ConversationEvidenceService()
