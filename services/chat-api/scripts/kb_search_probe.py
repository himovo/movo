from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _preview(result: dict[str, Any], *, max_items: int = 3, max_chars: int = 500) -> list[dict[str, Any]]:
    rows = result.get("results") if isinstance(result.get("results"), list) else []
    out: list[dict[str, Any]] = []
    for row in rows[:max_items]:
        if not isinstance(row, dict):
            continue
        content = str(row.get("content") or row.get("text") or row.get("snippet") or "").strip()
        out.append(
            {
                "title": row.get("title"),
                "source": row.get("source"),
                "score": row.get("score"),
                "content_preview": content[:max_chars] + (" ..." if len(content) > max_chars else ""),
                "meta": row.get("meta") if isinstance(row.get("meta"), dict) else {},
            }
        )
    return out


async def main() -> int:
    parser = argparse.ArgumentParser(description="Probe remote KB search directly, bypassing graph/runtime.")
    parser.add_argument("--query", default=os.getenv("E2E_KB_QUERY", ""), help="Search query.")
    parser.add_argument("--user-id", default=os.getenv("E2E_KB_USER_ID", ""), help="User id.")
    parser.add_argument("--main-id", default=os.getenv("E2E_KB_MAIN_ID", ""), help="Bot/main id.")
    parser.add_argument("--session-id", default=os.getenv("E2E_KB_SESSION_ID", ""), help="Upstream dialog session id.")
    parser.add_argument("--request-id", default=os.getenv("E2E_KB_REQUEST_ID", ""), help="Upstream request id.")
    parser.add_argument("--knowledge-ids", default=os.getenv("E2E_KB_KNOWLEDGE_IDS", ""), help="Comma-separated knowledge ids.")
    parser.add_argument("--limit", type=int, default=int(os.getenv("E2E_KB_LIMIT", "40")))
    parser.add_argument("--top-k", type=int, default=int(os.getenv("E2E_KB_TOP_K", "10")))
    parser.add_argument("--fail-empty", action="store_true", help="Exit 2 when ok=true but results are empty.")
    args = parser.parse_args()

    if not str(args.query or "").strip():
        parser.error("--query is required")

    from app.services.rag_service.remote_knowledge_rag_service import remote_knowledge_rag_service

    result = await remote_knowledge_rag_service.search(
        query=str(args.query or "").strip(),
        request_id=str(args.request_id or "").strip(),
        user_id=str(args.user_id or "").strip(),
        session_id=str(args.session_id or "").strip(),
        main_id=str(args.main_id or "").strip(),
        knowledge_ids=_split_csv(args.knowledge_ids),
        limit=args.limit,
        top_k=args.top_k,
    )
    rows = result.get("results") if isinstance(result.get("results"), list) else []
    summary = {
        "ok": result.get("ok"),
        "error": result.get("error"),
        "query": result.get("query"),
        "provider": result.get("provider"),
        "result_count": len(rows),
        "total_candidates": result.get("total_candidates"),
        "knowledge_ids": result.get("knowledge_ids"),
        "preview": _preview(result),
    }
    print("=== KB SEARCH SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("=== KB SEARCH RAW_RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:20000])

    if not result.get("ok"):
        return 1
    if args.fail_empty and not rows:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
