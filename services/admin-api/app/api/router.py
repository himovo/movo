from fastapi import APIRouter

from app.api.routes import analytics, auth, dashboard, directory, external_search, knowledge_directories, knowledge_documents, knowledge_settings, models, organizations, page_collection, position_roles, presentation_settings, setup, skills, system, system_audit, tools, traffic_allocations

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(setup.router, prefix="/setup", tags=["setup"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
api_router.include_router(directory.router, prefix="/directory", tags=["directory"])
api_router.include_router(position_roles.router, prefix="/position-roles", tags=["position-roles"])
api_router.include_router(system_audit.router, prefix="/system-audit", tags=["system-audit"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(knowledge_directories.router, prefix="/knowledge/directories", tags=["knowledge-directories"])
api_router.include_router(knowledge_documents.router, prefix="/knowledge/documents", tags=["knowledge-documents"])
api_router.include_router(knowledge_settings.router, prefix="/settings/knowledge", tags=["knowledge-settings"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(traffic_allocations.router, prefix="/traffic-allocations", tags=["traffic-allocations"])
api_router.include_router(skills.router, prefix="/skills", tags=["skills"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
api_router.include_router(external_search.router, prefix="/settings/external-search", tags=["external-search"])
api_router.include_router(page_collection.router, prefix="/settings/page-collection", tags=["page-collection"])
api_router.include_router(presentation_settings.router, prefix="/settings/presentation", tags=["presentation-settings"])
