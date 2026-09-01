from __future__ import annotations

import re
import json
from datetime import datetime, timedelta
from typing import Any, Dict

from app.core.db import get_db
from app.core.tenant import add_main_scope, resolve_main_id
from app.token_usage.status import REQUEST_STATUS_VALUES, normalize_request_status


class TokenUsageService:
    async def list_logs(
        self,
        *,
        user_id: str,
        main_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
        query: str = "",
        stage: str = "",
        status: str = "",
    ) -> Dict[str, Any]:
        db = get_db()
        coll = db.token_usage_logs
        session_ids = await self._load_visible_session_ids(user_id=user_id, main_id=main_id)
        if not session_ids:
            return {
                "summary": self._summary_defaults(),
                "items": [],
                "offset": max(int(offset or 0), 0),
                "limit": max(min(int(limit or 20), 100), 1),
                "total": 0,
                "has_more": False,
            }
        match = self._build_match(
            user_id=user_id,
            main_id=main_id,
            session_ids=session_ids,
            query=query,
            stage=stage,
            status=status,
        )
        group_id = self._request_group_id_expr()
        page_offset = max(int(offset or 0), 0)
        page_limit = max(min(int(limit or 20), 100), 1)
        rows = await coll.aggregate(
            [
                {"$match": match},
                {"$sort": {"created_at": 1, "start_time": 1}},
                {
                    "$group": {
                        "_id": group_id,
                        "request_id": {"$first": "$request_id"},
                        "main_id": {"$first": "$main_id"},
                        "user_id": {"$first": "$user_id"},
                        "session_id": {"$first": "$session_id"},
                        "trace_id": {"$first": "$trace_id"},
                        "stage": {"$first": "$stage"},
                        "intent": {"$first": "$intent"},
                        "node_id": {"$first": "$node_id"},
                        "status": {"$first": "$status"},
                        "failed_count": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
                        "error_text": {"$first": {"$ifNull": ["$response_payload.error", "$push_error"]}},
                        "model_name": {"$first": "$model_name"},
                        "model_names": {"$addToSet": "$model_name"},
                        "model_id": {"$first": "$model_id"},
                        "prompt": {"$first": "$prompt"},
                        "request_title_zh": {"$first": "$request_title_zh"},
                        "request_title_en": {"$first": "$request_title_en"},
                        "start_time": {"$min": "$start_time"},
                        "end_time": {"$max": "$end_time"},
                        "total_tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}},
                        "prompt_tokens": {"$sum": {"$ifNull": ["$prompt_tokens", 0]}},
                        "completion_tokens": {"$sum": {"$ifNull": ["$completion_tokens", 0]}},
                        "created_at": {"$min": "$created_at"},
                        "updated_at": {"$max": "$updated_at"},
                        "calls": {"$sum": 1},
                    }
                },
                {"$sort": {"created_at": -1}},
            ]
        ).to_list(length=50000)
        execution_statuses = await self._load_execution_statuses(rows, main_id=main_id)
        for row in rows:
            group_key = str(row.get("_id") or "").strip()
            row["request_status"] = normalize_request_status(
                execution_status=execution_statuses.get(group_key, ""),
                failed_count=row.get("failed_count"),
                error_text=row.get("error_text"),
            )
        requested_status = str(status or "").strip()
        if requested_status in REQUEST_STATUS_VALUES:
            rows = [row for row in rows if str(row.get("request_status") or "") == requested_status]
        total = len(rows)
        page_rows = rows[page_offset : page_offset + page_limit]
        request_texts = await self._load_request_texts(page_rows, main_id=main_id)
        items = [self._serialize_item(row, request_texts=request_texts) for row in page_rows]
        summary = self._summary_from_rows(rows)
        return {
            "summary": summary,
            "items": items,
            "offset": page_offset,
            "limit": page_limit,
            "total": int(total or 0),
            "has_more": page_offset + len(items) < int(total or 0),
        }

    def _build_match(
        self,
        *,
        user_id: str,
        main_id: str | None,
        session_ids: list[str],
        query: str,
        stage: str,
        status: str,
    ) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            "user_id": str(user_id or "").strip(),
            "session_id": {"$in": session_ids},
        }
        if str(stage or "").strip():
            base["stage"] = str(stage).strip()
        match = add_main_scope(base, resolve_main_id(main_id))
        keyword = str(query or "").strip()
        if keyword:
            escaped = re.escape(keyword)
            regex = {"$regex": escaped, "$options": "i"}
            return {
                "$and": [
                    match,
                    {
                        "$or": [
                            {"prompt": regex},
                            {"model_name": regex},
                            {"model_id": regex},
                            {"stage": regex},
                            {"request_title_zh": regex},
                            {"request_title_en": regex},
                            {"trace_id": regex},
                        ]
                    },
                ]
            }
        return match

    async def _load_visible_session_ids(self, *, user_id: str, main_id: str | None) -> list[str]:
        db = get_db()
        match = add_main_scope({"user_id": str(user_id or "").strip()}, resolve_main_id(main_id))
        rows = await db.chat_sessions.find(match, {"_id": 1}).to_list(length=5000)
        return [str(row.get("_id") or "") for row in rows if str(row.get("_id") or "").strip()]

    async def _load_request_texts(self, rows: list[Dict[str, Any]], *, main_id: str | None) -> Dict[str, str]:
        ids = [
            str(row.get("_id") or "").strip()
            for row in rows
            if str(row.get("_id") or "").strip()
        ]
        if not ids:
            return {}
        db = get_db()
        assistant_rows = await db.chat_messages.find(
            add_main_scope({"message_id": {"$in": ids}, "message_type": {"$ne": "context_summary"}}, resolve_main_id(main_id)),
            {"message_id": 1, "session_id": 1, "seq": 1},
        ).to_list(length=len(ids))
        result: Dict[str, str] = {}
        for assistant in assistant_rows:
            message_id = str(assistant.get("message_id") or "").strip()
            session_id = assistant.get("session_id")
            seq = int(assistant.get("seq") or 0)
            if not message_id or not session_id or seq <= 0:
                continue
            user_msg = await db.chat_messages.find_one(
                add_main_scope(
                    {
                        "session_id": session_id,
                        "role": "user",
                        "message_type": {"$ne": "context_summary"},
                        "seq": {"$lt": seq},
                    },
                    resolve_main_id(main_id),
                ),
                {"content": 1},
                sort=[("seq", -1)],
            )
            content = str((user_msg or {}).get("content") or "").strip()
            if content:
                result[message_id] = content
        return result

    async def _load_execution_statuses(self, rows: list[Dict[str, Any]], *, main_id: str | None) -> Dict[str, str]:
        ids = [str(row.get("_id") or "").strip() for row in rows if str(row.get("_id") or "").strip()]
        if not ids:
            return {}
        db = get_db()
        docs = await db.execution_logs.find(
            add_main_scope({"message_id": {"$in": ids}}, resolve_main_id(main_id)),
            {"message_id": 1, "status": 1},
        ).to_list(length=len(ids))
        return {
            str(row.get("message_id") or "").strip(): str(row.get("status") or "").strip()
            for row in docs
            if str(row.get("message_id") or "").strip()
        }

    async def _summary(self, match: Dict[str, Any]) -> Dict[str, Any]:
        db = get_db()
        coll = db.token_usage_logs
        now = datetime.utcnow()
        recent_threshold = now - timedelta(days=1)
        group_id = self._request_group_id_expr()
        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": group_id,
                    "total_tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}},
                    "prompt_tokens": {"$sum": {"$ifNull": ["$prompt_tokens", 0]}},
                    "completion_tokens": {"$sum": {"$ifNull": ["$completion_tokens", 0]}},
                    "calls": {"$sum": 1},
                    "created_at": {"$min": "$created_at"},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_calls": {"$sum": 1},
                    "total_tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}},
                    "prompt_tokens": {"$sum": {"$ifNull": ["$prompt_tokens", 0]}},
                    "completion_tokens": {"$sum": {"$ifNull": ["$completion_tokens", 0]}},
                    "avg_tokens": {"$avg": {"$ifNull": ["$total_tokens", 0]}},
                    "internal_calls": {"$sum": {"$ifNull": ["$calls", 0]}},
                    "last_called_at": {"$max": "$created_at"},
                }
            },
        ]
        rows = await coll.aggregate(pipeline).to_list(length=1)
        summary = rows[0] if rows else {}
        last_24h = await coll.aggregate(
            [
                {"$match": {"$and": [match, {"created_at": {"$gte": recent_threshold}}]}},
                {
                    "$group": {
                        "_id": group_id,
                        "tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}},
                        "calls": {"$sum": 1},
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "calls": {"$sum": 1},
                        "tokens": {"$sum": {"$ifNull": ["$tokens", 0]}},
                        "internal_calls": {"$sum": {"$ifNull": ["$calls", 0]}},
                    }
                },
            ]
        ).to_list(length=1)
        recent = last_24h[0] if last_24h else {}
        top_models = await coll.aggregate(
            [
                {"$match": match},
                {
                    "$group": {
                        "_id": "$model_name",
                        "calls": {"$sum": 1},
                        "tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}},
                    }
                },
                {"$sort": {"tokens": -1, "calls": -1}},
                {"$limit": 4},
            ]
        ).to_list(length=4)
        return {
            "total_calls": int(summary.get("total_calls") or 0),
            "total_tokens": int(summary.get("total_tokens") or 0),
            "prompt_tokens": int(summary.get("prompt_tokens") or 0),
            "completion_tokens": int(summary.get("completion_tokens") or 0),
            "avg_tokens": round(float(summary.get("avg_tokens") or 0), 1),
            "internal_calls": int(summary.get("internal_calls") or 0),
            "last_called_at": summary.get("last_called_at"),
            "last_24h_calls": int(recent.get("calls") or 0),
            "last_24h_tokens": int(recent.get("tokens") or 0),
            "last_24h_internal_calls": int(recent.get("internal_calls") or 0),
            "top_models": [
                {
                    "model_name": str(item.get("_id") or "unknown"),
                    "calls": int(item.get("calls") or 0),
                    "tokens": int(item.get("tokens") or 0),
                }
                for item in top_models
            ],
        }

    @staticmethod
    def _summary_from_rows(rows: list[Dict[str, Any]]) -> Dict[str, Any]:
        now = datetime.utcnow()
        recent_threshold = now - timedelta(days=1)
        total_tokens = 0
        prompt_tokens = 0
        completion_tokens = 0
        internal_calls = 0
        last_called_at = None
        recent_calls = 0
        recent_tokens = 0
        recent_internal_calls = 0
        model_map: Dict[str, Dict[str, int]] = {}
        for row in rows:
            row_total = int(row.get("total_tokens") or 0)
            row_prompt = int(row.get("prompt_tokens") or 0)
            row_completion = int(row.get("completion_tokens") or 0)
            row_calls = int(row.get("calls") or 0)
            created_at = row.get("created_at")
            total_tokens += row_total
            prompt_tokens += row_prompt
            completion_tokens += row_completion
            internal_calls += row_calls
            if created_at and (last_called_at is None or created_at > last_called_at):
                last_called_at = created_at
            if isinstance(created_at, datetime) and created_at >= recent_threshold:
                recent_calls += 1
                recent_tokens += row_total
                recent_internal_calls += row_calls
            for model_name in list(row.get("model_names") or []):
                key = str(model_name or "unknown").strip() or "unknown"
                bucket = model_map.setdefault(key, {"calls": 0, "tokens": 0})
                bucket["calls"] += 1
                bucket["tokens"] += row_total
        top_models = sorted(
            [
                {"model_name": model_name, "calls": data["calls"], "tokens": data["tokens"]}
                for model_name, data in model_map.items()
            ],
            key=lambda item: (item["tokens"], item["calls"]),
            reverse=True,
        )[:4]
        request_count = len(rows)
        return {
            "total_calls": request_count,
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "avg_tokens": round(float(total_tokens) / request_count, 1) if request_count else 0,
            "internal_calls": internal_calls,
            "last_called_at": last_called_at,
            "last_24h_calls": recent_calls,
            "last_24h_tokens": recent_tokens,
            "last_24h_internal_calls": recent_internal_calls,
            "top_models": top_models,
        }

    @staticmethod
    def _request_group_id_expr() -> Dict[str, Any]:
        return {
            "$let": {
                "vars": {
                    "userReq": {"$ifNull": ["$user_request_id", ""]},
                },
                "in": {
                    "$cond": [
                        {"$ne": ["$$userReq", ""]},
                        "$$userReq",
                        "$request_id",
                    ]
                },
            }
        }

    @staticmethod
    def _summary_defaults() -> Dict[str, Any]:
        return {
            "total_calls": 0,
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "avg_tokens": 0,
            "internal_calls": 0,
            "last_called_at": None,
            "last_24h_calls": 0,
            "last_24h_tokens": 0,
            "last_24h_internal_calls": 0,
            "top_models": [],
        }

    @staticmethod
    def _serialize_item(row: Dict[str, Any], *, request_texts: Dict[str, str] | None = None) -> Dict[str, Any]:
        failed_count = int(row.get("failed_count") or 0)
        group_id = str(row.get("_id") or "").strip()
        request_text = str((request_texts or {}).get(group_id) or "").strip()
        prompt_text = request_text or TokenUsageService._display_prompt(row.get("prompt"))
        model_names = [
            str(item or "").strip()
            for item in list(row.get("model_names") or [])
            if str(item or "").strip()
        ]
        return {
            "request_id": str(row.get("request_id") or ""),
            "user_request_id": group_id or str(row.get("user_request_id") or ""),
            "main_id": resolve_main_id(row.get("main_id")),
            "user_id": str(row.get("user_id") or ""),
            "session_id": str(row.get("session_id") or ""),
            "trace_id": str(row.get("trace_id") or ""),
            "stage": str(row.get("stage") or ""),
            "intent": str(row.get("intent") or ""),
            "node_id": str(row.get("node_id") or ""),
            "status": str(row.get("request_status") or ("failed" if failed_count > 0 else "completed")),
            "model_name": str(row.get("model_name") or ""),
            "model_names": model_names,
            "model_id": str(row.get("model_id") or ""),
            "prompt": prompt_text,
            "request_title_zh": "" if prompt_text else str(row.get("request_title_zh") or ""),
            "request_title_en": "" if prompt_text else str(row.get("request_title_en") or ""),
            "start_time": int(row.get("start_time") or 0),
            "end_time": int(row.get("end_time") or 0),
            "total_tokens": int(row.get("total_tokens") or 0),
            "prompt_tokens": int(row.get("prompt_tokens") or 0),
            "completion_tokens": int(row.get("completion_tokens") or 0),
            "push_status": str(row.get("push_status") or ""),
            "push_error": str(row.get("push_error") or ""),
            "calls": int(row.get("calls") or 1),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    @staticmethod
    def _display_prompt(raw_prompt: Any) -> str:
        text = str(raw_prompt or "").strip()
        if not text:
            return ""
        if text.startswith("{"):
            try:
                payload = json.loads(text)
            except Exception:
                payload = None
            if isinstance(payload, dict):
                for key in ("user_request", "latest_user_request", "request", "query", "question", "content"):
                    value = str(payload.get(key) or "").strip()
                    if value:
                        return value
        match = re.search(r'"user_request"\s*:\s*"([^"]+)"', text)
        if match:
            value = match.group(1)
            try:
                return TokenUsageService._repair_mojibake(json.loads(f'"{value}"')).strip()
            except Exception:
                return TokenUsageService._repair_mojibake(value).strip()
        question_match = re.search(r"用户问题：\s*(.*?)\s*(?:内部知识候选：|$)", text, flags=re.S)
        if question_match:
            return TokenUsageService._repair_mojibake(question_match.group(1)).strip()
        return TokenUsageService._repair_mojibake(text)

    @staticmethod
    def _repair_mojibake(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if any(marker in text for marker in ("è", "å", "æ", "ä")):
            try:
                repaired = text.encode("latin1").decode("utf-8")
                if repaired and repaired != text:
                    return repaired
            except Exception:
                pass
        return text


token_usage_service = TokenUsageService()
