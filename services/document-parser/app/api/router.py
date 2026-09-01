from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import document_indexing, document_parsing, health, preview_conversion, retrieval, vector_maintenance

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(preview_conversion.router, tags=["preview-conversion"])
api_router.include_router(document_parsing.router, tags=["document-parsing"])
api_router.include_router(document_indexing.router, tags=["document-indexing"])
api_router.include_router(retrieval.router, tags=["retrieval"])
api_router.include_router(vector_maintenance.router, tags=["vector-maintenance"])
