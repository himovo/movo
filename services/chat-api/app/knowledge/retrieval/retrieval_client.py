from __future__ import annotations

from typing import List

import httpx

from app.core.config import get_settings
from app.knowledge.retrieval.schemas import RetrievalChunkItem, RetrievalSearchPayload, RetrievalSearchResult


class KnowledgeRetrievalError(RuntimeError):
    pass


class KnowledgeRetrievalClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = str(getattr(settings, "DOCUMENT_PROCESSING_BASE_URL", "") or "http://127.0.0.1:8200").rstrip("/")
        self.service_token = str(getattr(settings, "DOCUMENT_PROCESSING_SERVICE_TOKEN", "") or "")
        self.timeout = float(getattr(settings, "DOCUMENT_PROCESSING_TIMEOUT_SECONDS", 30.0) or 30.0)

    async def search(
        self,
        *,
        query: str,
        main_id: str,
        knowledge_base_ids: List[str] | None = None,
        top_n: int = 8,
        rerank: bool | None = None,
    ) -> RetrievalSearchResult:
        if not query.strip():
            return RetrievalSearchResult(query=query, items=[], total=0)
        ids = [str(item).strip() for item in list(knowledge_base_ids or []) if str(item).strip()]
        if not ids:
            ids = [""]

        all_items: list[RetrievalChunkItem] = []
        mode = "vector"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for knowledge_base_id in ids:
                payload = RetrievalSearchPayload(
                    query=query,
                    mainId=main_id,
                    knowledgeBaseId=knowledge_base_id,
                    topN=top_n,
                    retrievalMode="vector",
                    rerank=rerank,
                )
                try:
                    resp = await client.post(
                        f"{self.base_url}/api/retrieval/search",
                        json=payload.model_dump(),
                        headers={
                            "Authorization": f"Bearer {self.service_token}",
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    raise KnowledgeRetrievalError(f"内部知识检索失败: {type(exc).__name__}: {exc}") from exc
                result = RetrievalSearchResult.model_validate(data)
                mode = result.retrievalMode or mode
                all_items.extend(result.items)

        all_items.sort(key=lambda item: float(item.rerankScore if item.rerankScore is not None else item.score or 0), reverse=True)
        return RetrievalSearchResult(
            query=query,
            retrievalMode=mode,
            topN=top_n,
            items=all_items[:top_n],
            total=len(all_items),
        )


knowledge_retrieval_client = KnowledgeRetrievalClient()
