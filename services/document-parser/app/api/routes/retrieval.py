from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import verify_service_token
from app.domain.jobs import RetrievalSearchRequest
from app.services.embedding_provider import EmbeddingProviderError
from app.services.retrieval_service import search_knowledge
from app.services.vector_store import VectorStoreError

router = APIRouter()


@router.post("/retrieval/search")
async def search_retrieval(
    payload: RetrievalSearchRequest,
    _: None = Depends(verify_service_token),
) -> dict:
    try:
        return search_knowledge(payload)
    except EmbeddingProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except VectorStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
