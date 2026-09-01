from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

from app.core.db import get_db
from app.core.tenant import add_main_scope, resolve_main_id


def _tokens(text: str) -> List[str]:
    raw = str(text or "").lower()
    out: List[str] = []
    for tok in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9_]{2,}", raw):
        if tok not in out:
            out.append(tok)
    return out


def _score(query_tokens: List[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    low = str(text or "").lower()
    return sum(1.0 for t in query_tokens if t in low) / float(len(query_tokens))


@dataclass
class ProjectMemory:
    key: str
    content: str
    memory_type: str
    score: float
    metadata: Dict[str, Any]


class ProjectMemoryService:
    collection_name = "project_memories"

    async def retrieve(
        self,
        *,
        query: str,
        output_spec: Dict[str, Any],
        limit: int = 6,
    ) -> List[ProjectMemory]:
        user_id = str(output_spec.get("user_id") or "").strip()
        if not user_id:
            return []
        project_id = self._project_id(output_spec)
        main_id = resolve_main_id(output_spec.get("main_id") or output_spec.get("mainId"))
        query_tokens = _tokens(query)
        try:
            db = get_db()
            project_filter = [project_id, "default"] if project_id != "default" else ["default"]
            raw = await db[self.collection_name].find(
                add_main_scope({
                    "user_id": user_id,
                    "$or": [
                        {"project_id": {"$in": project_filter}},
                        {"scope": "global"},
                    ],
                }, main_id)
            ).sort("updated_at", -1).limit(80).to_list(length=80)
        except Exception:
            return []
        ranked: List[ProjectMemory] = []
        for row in raw:
            content = str(row.get("content") or "").strip()
            if not content:
                continue
            s = _score(query_tokens, content)
            if not query_tokens:
                s = 0.25
            if s <= 0.0 and str(row.get("pinned") or "").lower() != "true":
                continue
            ranked.append(
                ProjectMemory(
                    key=str(row.get("key") or row.get("_id") or "").strip(),
                    content=content[:1200],
                    memory_type=str(row.get("memory_type") or "note").strip(),
                    score=s + (0.2 if row.get("pinned") else 0.0),
                    metadata={
                        "project_id": str(row.get("project_id") or ""),
                        "scope": str(row.get("scope") or "project"),
                        "source": str(row.get("source") or ""),
                    },
                )
            )
        return sorted(ranked, key=lambda x: x.score, reverse=True)[: max(1, min(int(limit or 6), 20))]

    async def upsert_memories(
        self,
        *,
        user_id: str,
        project_id: str,
        memories: List[Dict[str, Any]],
        source: str,
        main_id: str = "default",
    ) -> None:
        uid = str(user_id or "").strip()
        if not uid:
            return
        pid = str(project_id or "default").strip() or "default"
        mid = resolve_main_id(main_id)
        now = datetime.utcnow()
        try:
            db = get_db()
            for item in list(memories or []):
                if not isinstance(item, dict):
                    continue
                content = str(item.get("content") or "").strip()
                if not content:
                    continue
                memory_type = str(item.get("memory_type") or item.get("type") or "note").strip() or "note"
                key = str(item.get("key") or self._make_key(memory_type, content)).strip()
                await db[self.collection_name].update_one(
                    {"user_id": uid, "main_id": mid, "project_id": pid, "key": key},
                    {
                        "$set": {
                            "user_id": uid,
                            "main_id": mid,
                            "project_id": pid,
                            "scope": str(item.get("scope") or "project"),
                            "key": key,
                            "memory_type": memory_type,
                            "content": content[:2400],
                            "source": source,
                            "updated_at": now,
                        },
                        "$setOnInsert": {"created_at": now, "pinned": bool(item.get("pinned") or False)},
                    },
                    upsert=True,
                )
        except Exception:
            return

    def format_memories(self, memories: List[ProjectMemory]) -> str:
        if not memories:
            return ""
        lines = [
            "<project_memory>",
            "Stable project-level facts, preferences, decisions, and constraints. Prefer newer user instructions if they conflict.",
        ]
        for idx, item in enumerate(memories, 1):
            lines.append(f"- [{idx}] {item.memory_type}: {item.content}")
        lines.append("</project_memory>")
        return "\n".join(lines).strip()

    def _project_id(self, output_spec: Dict[str, Any]) -> str:
        explicit = str(output_spec.get("project_id") or output_spec.get("workspace_id") or "").strip()
        if explicit:
            return explicit
        return "default"

    def _make_key(self, memory_type: str, content: str) -> str:
        compact = re.sub(r"\s+", " ", str(content or "").strip().lower())
        safe = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", compact)[:80].strip("_")
        return f"{memory_type}:{safe or 'memory'}"


project_memory_service = ProjectMemoryService()
