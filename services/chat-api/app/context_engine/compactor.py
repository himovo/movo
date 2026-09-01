from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.llm.factory import get_llm_client
from app.llm.types import Message, Role


@dataclass
class CompactionResult:
    summary: str
    memories: List[Dict[str, Any]] = field(default_factory=list)
    source: str = "heuristic"


class ContextCompactor:
    async def compact_messages(
        self,
        rows: List[Dict[str, Any]],
        *,
        output_spec: Dict[str, Any] | None = None,
    ) -> CompactionResult:
        heuristic = self.heuristic_summary(rows)
        if not rows:
            return CompactionResult(summary=heuristic, memories=[], source="heuristic")
        try:
            llm = get_llm_client(streaming=False, stage="context_compaction", intent="chat", output_spec=output_spec or {})
            resp = await llm.ainvoke(
                [
                    Message(role=Role.SYSTEM, content=self._system_prompt()),
                    Message(role=Role.USER, content=self._user_payload(rows, heuristic)),
                ]
            )
            data = self._parse_json(str(getattr(resp, "content", "") or ""))
            summary = str(data.get("summary") or "").strip()
            memories = [m for m in list(data.get("memories") or []) if isinstance(m, dict)]
            if summary:
                return CompactionResult(summary=summary[:6000], memories=memories[:12], source="llm")
        except Exception:
            pass
        return CompactionResult(summary=heuristic, memories=self.heuristic_memories(rows), source="heuristic")

    def heuristic_summary(self, rows: List[Dict[str, Any]]) -> str:
        user_goals: List[str] = []
        assistant_outputs: List[str] = []
        decisions: List[str] = []
        constraints: List[str] = []
        deliverables: List[str] = []
        open_issues: List[str] = []
        rejected: List[str] = []
        for msg in list(rows or []):
            role = str(msg.get("role") or "").lower()
            content = self._one_line(str(msg.get("content") or ""))
            low = content.lower()
            if role == "user" and content:
                user_goals.append(content[:280])
                if any(k in low for k in ["必须", "不要", "不能", "should", "must", "never", "保留", "兼容"]):
                    constraints.append(content[:260])
            elif role == "assistant" and content:
                assistant_outputs.append(content[:360])
                if any(k in low for k in ["决定", "建议", "结论", "decision", "recommend"]):
                    decisions.append(content[:300])
                if any(k in low for k in ["不要", "不建议", "rejected", "否掉", "不适合"]):
                    rejected.append(content[:260])
                if any(k in low for k in ["error", "failed", "失败", "错误", "未完成", "blocked"]):
                    open_issues.append(content[:240])
            for d in list(msg.get("documents") or []):
                if not isinstance(d, dict):
                    continue
                op = str(d.get("object_path") or d.get("url") or "").strip()
                if not op:
                    continue
                title = str(d.get("title") or d.get("filename") or d.get("type") or "").strip()
                deliverables.append(f"{title}: {op}" if title else op)
        lines = ["context_summary_v2"]
        self._section(lines, "user_goals", user_goals[-10:])
        self._section(lines, "decisions", decisions[-8:])
        self._section(lines, "constraints", constraints[-8:])
        self._section(lines, "assistant_outputs", assistant_outputs[-10:])
        self._section(lines, "deliverables", list(dict.fromkeys(deliverables))[-10:])
        self._section(lines, "rejected_approaches", rejected[-6:])
        self._section(lines, "open_issues", open_issues[-6:])
        return "\n".join(lines).strip()[:6000]

    def heuristic_memories(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        memories: List[Dict[str, Any]] = []
        for msg in list(rows or []):
            role = str(msg.get("role") or "").lower()
            if role != "user":
                continue
            content = self._one_line(str(msg.get("content") or ""))
            low = content.lower()
            if any(k in low for k in ["以后", "后续", "长期", "必须", "不要", "偏好", "架构", "兼容", "should", "must", "never"]):
                memories.append(
                    {
                        "memory_type": "preference_or_constraint",
                        "content": content[:500],
                        "scope": "project",
                    }
                )
        return memories[-8:]

    def _system_prompt(self) -> str:
        return (
            "You are a context compaction engine. Return strict JSON only.\n"
            "Schema: {\"summary\":\"context_summary_v2...\", \"memories\":[{\"memory_type\":\"preference|constraint|decision|project_fact\", \"content\":\"...\", \"scope\":\"project|global\", \"key\":\"optional\"}]}.\n"
            "The summary must preserve user goals, decisions, constraints, deliverables, rejected approaches, open issues, and next actions.\n"
            "Do not invent facts. Prefer concise, stable facts over narration."
        )

    def _user_payload(self, rows: List[Dict[str, Any]], fallback_summary: str) -> str:
        payload = []
        for row in list(rows or [])[-80:]:
            payload.append(
                {
                    "seq": row.get("seq"),
                    "role": row.get("role"),
                    "content": str(row.get("content") or "")[:1800],
                    "documents": row.get("documents") or [],
                }
            )
        return json.dumps(
            {
                "messages": payload,
                "fallback_summary_format": fallback_summary,
            },
            ensure_ascii=False,
        )

    def _parse_json(self, text: str) -> Dict[str, Any]:
        raw = str(text or "").strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end >= start:
            raw = raw[start : end + 1]
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}

    def _section(self, lines: List[str], title: str, items: List[str]) -> None:
        lines.append(f"{title}:")
        if items:
            lines.extend(f"- {self._one_line(x)}" for x in items if str(x or "").strip())
        else:
            lines.append("- none")

    def _one_line(self, text: str) -> str:
        return " ".join(str(text or "").split())


context_compactor = ContextCompactor()
