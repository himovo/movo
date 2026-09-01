from __future__ import annotations

import uuid
import os
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_settings


def _truncate(text: str, max_chars: int = 1200) -> str:
    raw = str(text or "").strip()
    if len(raw) <= max_chars:
        return raw
    return raw[: max(200, max_chars)] + " ..."


def _coerce_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    return []


class RemoteKnowledgeRAGService:
    """Internal KB retriever backed by the platform candidates API."""

    def _api_url(self) -> str:
        settings = get_settings()
        explicit = str(getattr(settings, "KNOWLEDGE_CANDIDATES_API_URL", "") or "").strip()
        if explicit:
            return explicit
        base = str(getattr(settings, "KNOWLEDGE_CANDIDATES_BASE_URL", "") or "").strip().rstrip("/")
        if not base:
            base = str(os.getenv("ASKBOT_APP_BASE_URL") or "").strip().rstrip("/")
        if not base:
            return ""
        return f"{base}/dialog-api/llm/bot/candidates-with-scope"

    @staticmethod
    def _payload(
        *,
        request_id: str,
        query: str,
        user_id: str,
        session_id: str,
        main_id: str,
        knowledge_ids: List[str],
        limit: int,
        top_n: int,
    ) -> Dict[str, Any]:
        payload = {
            "requestId": request_id,
            "query": query,
            "enableRewrite": True,
            "limit": limit,
            "topN": top_n,
            "knowledgeIds": knowledge_ids,
        }
        if user_id:
            payload["userId"] = user_id
        if session_id:
            payload["sessionId"] = session_id
        if main_id:
            payload["mainId"] = main_id
        return payload

    @staticmethod
    def _candidate_rows(raw: Any) -> List[Dict[str, Any]]:
        if isinstance(raw, dict):
            data = raw.get("data")
            if isinstance(data, dict):
                for key in ("candidates", "list", "records", "items"):
                    if isinstance(data.get(key), list):
                        return [x for x in data.get(key) or [] if isinstance(x, dict)]
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
            for key in ("candidates", "list", "records", "items"):
                if isinstance(raw.get(key), list):
                    return [x for x in raw.get(key) or [] if isinstance(x, dict)]
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
        return []

    @staticmethod
    def _normalize_candidate(candidate: Dict[str, Any], *, min_score: float) -> Optional[Dict[str, Any]]:
        content = str(
            candidate.get("content")
            or candidate.get("text")
            or candidate.get("chunk")
            or candidate.get("summary")
            or ""
        ).strip()
        if not content:
            return None
        raw_score = candidate.get("reRankScore")
        if raw_score is None:
            raw_score = candidate.get("rerank_score", candidate.get("score", 0))
        try:
            score = float(raw_score or 0)
        except Exception:
            score = 0.0
        if min_score > 0 and score < min_score:
            return None

        candidate_id = str(candidate.get("id") or candidate.get("candidate_id") or candidate.get("_id") or "").strip()
        title = str(
            candidate.get("title")
            or candidate.get("name")
            or candidate.get("documentName")
            or candidate.get("knowledgeName")
            or "内部知识"
        ).strip()
        meta: Dict[str, Any] = {
            "candidate_id": candidate_id,
            "provider": "remote_kb",
            "reRankScore": score,
        }
        multi = candidate.get("multiModalInfo") if isinstance(candidate.get("multiModalInfo"), dict) else {}
        if multi.get("oss_image_url"):
            meta["oss_image_url"] = multi.get("oss_image_url")
        for key in ("knowledgeId", "documentId", "chunkId", "source", "url"):
            value = candidate.get(key)
            if value:
                meta[key] = value

        return {
            "source": f"kb://{candidate_id or 'candidate'}",
            "title": title,
            "content": _truncate(content),
            "score": score,
            "meta": meta,
        }

    async def search(
        self,
        *,
        query: str,
        request_id: str = "",
        user_id: str = "",
        session_id: str = "",
        main_id: str = "",
        knowledge_ids: Any = None,
        limit: int = 40,
        top_k: int = 10,
    ) -> Dict[str, Any]:
        q = str(query or "").strip()
        if not q:
            return {"ok": False, "error": "missing_query", "results": []}
        api_url = self._api_url()
        if not api_url:
            return {
                "ok": False,
                "error": "knowledge_candidates_api_not_configured",
                "query": q,
                "results": [],
            }

        settings = get_settings()
        req_id = str(request_id or "").strip() or uuid.uuid4().hex
        ids = _coerce_list(knowledge_ids)
        lim = max(1, min(100, int(limit or 40)))
        top_n = max(1, min(50, int(top_k or 10)))
        payload = self._payload(
            request_id=req_id,
            query=q,
            user_id=str(user_id or "").strip(),
            session_id=str(session_id or "").strip(),
            main_id=str(main_id or "").strip(),
            knowledge_ids=ids,
            limit=lim,
            top_n=top_n,
        )
        timeout = float(getattr(settings, "KNOWLEDGE_CANDIDATES_TIMEOUT_SECONDS", 20.0) or 20.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(api_url, json=payload)
                resp.raise_for_status()
                raw = resp.json()
        except Exception as exc:
            return {
                "ok": False,
                "error": f"knowledge_candidates_request_failed: {type(exc).__name__}: {exc}",
                "query": q,
                "knowledge_ids": ids,
                "results": [],
            }

        rows = self._candidate_rows(raw)
        min_score = float(getattr(settings, "KNOWLEDGE_CANDIDATES_MIN_RERANK_SCORE", 10.0) or 0.0)
        results: List[Dict[str, Any]] = []
        for row in rows:
            item = self._normalize_candidate(row, min_score=min_score)
            if item:
                results.append(item)
            if len(results) >= top_n:
                break
        return {
            "ok": True,
            "query": q,
            "knowledge_ids": ids,
            "results": results,
            "total_candidates": len(rows),
            "provider": "remote_kb",
        }


remote_knowledge_rag_service = RemoteKnowledgeRAGService()
