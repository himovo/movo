"""Stable model-facing semantics for internal knowledge retrieval outcomes."""

from __future__ import annotations

from typing import Any


def available_result(*, query: str, retrieval_mode: str, total: int, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "success": True,
        "retrieval_status": "completed" if items else "empty",
        "evidence_available": bool(items),
        "query": query,
        "retrieval_mode": retrieval_mode,
        "total": total,
        "items": items,
        "message": "内部知识检索完成。" if items else "内部知识检索已完成，但没有命中授权范围内的内容。",
    }


def unavailable_result(*, query: str, error: Exception) -> dict[str, Any]:
    return {
        # The tool invocation completed and returned a governed availability
        # observation. This is deliberately not represented as an empty search.
        "success": True,
        "retrieval_status": "service_unavailable",
        "evidence_available": False,
        "query": query,
        "retrieval_mode": "unavailable",
        "total": None,
        "items": [],
        "message": "内部知识服务暂不可用；该状态不代表知识库没有命中结果。",
        "error": {"code": "knowledge_service_unavailable", "detail": str(error)},
    }
