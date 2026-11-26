"""Tenant- and membership-protected native DSH context measurements."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.principal import ApiPrincipal, require_end_user_principal
from app.core.db import get_db
from app.dsh_runtime.application import dsh_runtime_application
from app.dsh_runtime.session_access import SessionReadAuthorizer, SessionReadDeniedError


router = APIRouter()


@router.get("/sessions/{session_id}/context")
async def context_usage(
    session_id: str, principal: ApiPrincipal = Depends(require_end_user_principal),
):
    authorizer = SessionReadAuthorizer(get_db())
    try:
        await authorizer.authorize_read(session_id, tenant_id=principal.main_id, user_id=principal.user_id)
        reader = dsh_runtime_application.context_usage
        if reader is None:
            raise HTTPException(status_code=503, detail="runtime_unavailable")
        result = await reader.read(session_id, tenant_id=principal.main_id, user_id=principal.user_id)
        await authorizer.authorize_read(session_id, tenant_id=principal.main_id, user_id=principal.user_id)
        return result
    except SessionReadDeniedError as exc:
        raise HTTPException(status_code=404, detail="session_not_found") from exc
