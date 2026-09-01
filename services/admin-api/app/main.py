from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.router import api_router
from app.core.config import settings
from app.core.db import close_db, init_db
from app.core.product_edition import migrate_bootstrapped_community_organization
from app.repositories.model_repository import ensure_indexes as ensure_model_indexes
from app.api.routes.skills import ensure_indexes as ensure_skill_indexes
from app.api.routes.tools import ensure_indexes as ensure_tool_indexes
from app.api.routes.external_search import ensure_indexes as ensure_external_search_indexes
from app.api.routes.knowledge_documents import ensure_indexes as ensure_knowledge_document_indexes
from app.api.routes.knowledge_directories import ensure_indexes as ensure_knowledge_directory_indexes
from app.api.routes.knowledge_settings import ensure_indexes as ensure_knowledge_settings_indexes
from app.api.routes.page_collection import ensure_indexes as ensure_page_collection_indexes
from app.services.admin_bootstrap import bootstrap_admin_user
from app.services.directory_bootstrap import bootstrap_directory
from app.services.organization_tools import repair_role_referenced_personal_tools
from app.system_audit import SystemAuditMiddleware, SystemAuditRepository
from app.product.extensions import get_admin_product_extension


def create_app() -> FastAPI:
    app = FastAPI(
        title="MOVO Admin API",
        version="0.1.0",
        description="Control plane API for MOVO admin backend",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SystemAuditMiddleware)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "movo-admin-api"}

    @app.on_event("startup")
    async def on_startup() -> None:
        init_db()
        await bootstrap_admin_user()
        if get_admin_product_extension().edition == "community":
            await migrate_bootstrapped_community_organization()
        await bootstrap_directory()
        await SystemAuditRepository().ensure_indexes()
        await ensure_model_indexes()
        await ensure_skill_indexes()
        await ensure_tool_indexes()
        await repair_role_referenced_personal_tools()
        await ensure_external_search_indexes()
        await ensure_page_collection_indexes()
        await ensure_knowledge_settings_indexes()
        await ensure_knowledge_document_indexes()
        await ensure_knowledge_directory_indexes()


    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        close_db()

    app.include_router(api_router, prefix="/api")
    for extension_router in get_admin_product_extension().routers:
        app.include_router(extension_router, prefix="/api")
    static_dir = Path(settings.admin_static_dir).expanduser().resolve()
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return app


app = create_app()
