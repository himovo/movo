from __future__ import annotations

from fastapi import FastAPI

from app.api.router import api_router
from app.core.db import close_db
from app.repositories.job_repository import ensure_job_indexes


def create_app() -> FastAPI:
    app = FastAPI(
        title="MOVO Document Processing Service",
        version="0.1.0",
        description="Async document preview conversion, parsing, chunking and indexing service for MOVO.",
    )
    app.include_router(api_router, prefix="/api")

    @app.on_event("startup")
    def startup() -> None:
        ensure_job_indexes()

    @app.on_event("shutdown")
    def shutdown() -> None:
        close_db()

    return app


app = create_app()
