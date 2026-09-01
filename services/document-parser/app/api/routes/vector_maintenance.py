from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import verify_service_token
from app.domain.jobs import DeleteDocumentVectorsRequest
from app.services.vector_store import get_vector_store

router = APIRouter()


@router.post("/vectors/documents/delete")
async def delete_document_vectors(
    payload: DeleteDocumentVectorsRequest,
    _: None = Depends(verify_service_token),
) -> dict[str, int | str]:
    config = dict(payload.config or {})
    vector_store = get_vector_store(config)
    deleted = vector_store.delete_document_chunks(
        main_id=payload.mainId,
        document_id=payload.documentId,
    )
    return {
        "documentId": payload.documentId,
        "deleted": deleted,
        "vectorStoreType": "weaviate",
        "collectionName": vector_store.collection,
    }
