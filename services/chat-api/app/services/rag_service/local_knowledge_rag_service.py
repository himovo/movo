from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId

from app.core.db import get_db
from app.core.tenant import add_main_scope
from app.utils import storage_utils


@dataclass
class KnowledgeChunk:
    source: str
    title: str
    content: str
    score: float
    meta: Dict[str, Any]


def _tokenize(text: str) -> List[str]:
    raw = str(text or "").lower()
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9_]{2,}", raw)
    stop = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "you",
        "your",
        "are",
        "请",
        "一下",
        "帮我",
        "生成",
        "关于",
        "需要",
        "一个",
        "一些",
    }
    out: List[str] = []
    for t in tokens:
        if t in stop:
            continue
        if t not in out:
            out.append(t)
    return out


def _score_text(query_tokens: List[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    low = str(text or "").lower()
    hit = 0.0
    for tok in query_tokens:
        if tok in low:
            hit += 1.0
    return hit / max(1.0, float(len(query_tokens)))


def _truncate(text: str, max_chars: int = 900) -> str:
    raw = str(text or "").strip()
    if len(raw) <= max_chars:
        return raw
    return raw[: max(200, max_chars)] + " ..."


class LocalKnowledgeRAGService:
    """Lightweight local knowledge retriever based on persisted chat/session artifacts."""

    async def search(
        self,
        *,
        query: str,
        user_id: str,
        main_id: str = "default",
        session_id: str = "",
        top_k: int = 8,
        fetch_artifacts: bool = True,
    ) -> Dict[str, Any]:
        db = get_db()
        uid = str(user_id or "").strip()
        if not uid:
            return {"ok": False, "error": "missing_user_id", "results": []}

        query_tokens = _tokenize(query)
        candidates: List[KnowledgeChunk] = []
        now = datetime.utcnow()
        artifact_cache: Dict[str, str] = {}

        async def _load_artifact_text_cached(object_path: str) -> str:
            key = str(object_path or "").strip()
            if not key:
                return ""
            cached = artifact_cache.get(key)
            if cached is not None:
                return cached
            try:
                text = await storage_utils.download_text(key, timeout_s=12.0)
            except Exception:
                text = ""
            artifact_cache[key] = str(text or "")
            return artifact_cache[key]

        # 1) Candidate set from chat messages.
        msg_filter: Dict[str, Any] = {
            "user_id": uid,
        }
        sid = str(session_id or "").strip()
        if sid:
            try:
                msg_filter["session_id"] = ObjectId(sid)
            except Exception:
                pass
        rows = (
            await db.chat_messages.find(add_main_scope(msg_filter, main_id))
            .sort("created_at", -1)
            .limit(240)
            .to_list(length=240)
        )
        for row in rows:
            content = str(row.get("content") or "").strip()
            if not content:
                continue
            score = _score_text(query_tokens, content)
            if score <= 0.0:
                continue
            created_at = row.get("created_at")
            recency_bonus = 0.0
            if isinstance(created_at, datetime):
                delta_h = max(0.0, (now - created_at).total_seconds() / 3600.0)
                recency_bonus = max(0.0, 1.0 - min(delta_h / (24.0 * 14.0), 1.0)) * 0.08
            final_score = score + recency_bonus
            if str(row.get("message_type") or "") == "context_summary":
                final_score += 0.03
            candidates.append(
                KnowledgeChunk(
                    source=f"chat_message://{str(row.get('_id') or '')}",
                    title=f"{str(row.get('role') or 'message')} message",
                    content=_truncate(content),
                    score=final_score,
                    meta={
                        "role": str(row.get("role") or ""),
                        "session_id": str(row.get("session_id") or ""),
                        "seq": int(row.get("seq") or 0),
                    },
                )
            )

            # 1.1) Candidate set from message-attached documents/artifacts.
            for doc in (row.get("documents") or []):
                if not isinstance(doc, dict):
                    continue
                object_path = str(doc.get("object_path") or "").strip()
                if not object_path or not fetch_artifacts:
                    continue
                artifact_text = await _load_artifact_text_cached(object_path)
                if not artifact_text:
                    continue
                a_score = _score_text(query_tokens, artifact_text)
                if a_score <= 0.0:
                    continue
                title = str(doc.get("title") or doc.get("filename") or "message_document")
                candidates.append(
                    KnowledgeChunk(
                        source=f"artifact://{object_path}",
                        title=title,
                        content=_truncate(artifact_text, max_chars=1200),
                        score=a_score + 0.04,
                        meta={
                            "session_id": str(row.get("session_id") or ""),
                            "message_id": str(row.get("_id") or ""),
                            "type": str(doc.get("type") or ""),
                            "from": "chat_message.documents",
                        },
                    )
                )

        # 2) Candidate set from latest persisted artifacts in sessions.
        sess_filter: Dict[str, Any] = {"user_id": uid, "latest_artifact_ref": {"$exists": True}}
        if sid:
            try:
                sess_filter["_id"] = ObjectId(sid)
            except Exception:
                pass
        sessions = (
            await db.chat_sessions.find(add_main_scope(sess_filter, main_id))
            .sort("updated_at", -1)
            .limit(30)
            .to_list(length=30)
        )
        for sess in sessions:
            ref = sess.get("latest_artifact_ref")
            if not isinstance(ref, dict):
                continue
            object_path = str(ref.get("object_path") or "").strip()
            if not object_path or not fetch_artifacts:
                continue
            text = await _load_artifact_text_cached(object_path)
            if not text:
                continue
            score = _score_text(query_tokens, text)
            if score <= 0.0:
                continue
            title = str(ref.get("title") or ref.get("filename") or "artifact")
            candidates.append(
                KnowledgeChunk(
                    source=f"artifact://{object_path}",
                    title=title,
                    content=_truncate(text, max_chars=1200),
                    score=score + 0.05,
                    meta={
                        "session_id": str(sess.get("_id") or ""),
                        "object_path": object_path,
                        "type": str(ref.get("type") or ""),
                    },
                )
            )

        # 3) Rerank and dedupe by source.
        ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
        dedup: List[KnowledgeChunk] = []
        seen: set[str] = set()
        for item in ranked:
            if item.source in seen:
                continue
            seen.add(item.source)
            dedup.append(item)
        top = dedup[: max(1, min(int(top_k or 8), 20))]
        return {
            "ok": True,
            "query": str(query or ""),
            "results": [
                {
                    "source": x.source,
                    "title": x.title,
                    "content": x.content,
                    "score": round(float(x.score), 6),
                    "meta": x.meta,
                }
                for x in top
            ],
            "total_candidates": len(dedup),
        }


local_knowledge_rag_service = LocalKnowledgeRAGService()
