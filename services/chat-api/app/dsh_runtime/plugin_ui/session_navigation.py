"""Resolve a DSH plugin page's Session selection to an authorized conversation."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.dsh_runtime.bindings.repository import KernelBindingRepository
from app.dsh_runtime.session_access import SessionReadAuthorizer, SessionReadDeniedError


async def resolve_conversation(db: Any, *, tenant_id: str, user_id: str,
                               kernel_session_id: str) -> str:
    binding = await KernelBindingRepository(db).by_kernel_session_for_tenant(
        kernel_session_id, tenant_id=tenant_id,
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="plugin_ui_session_not_found")
    conversation_id = str(binding["conversation_id"])
    try:
        await SessionReadAuthorizer(db).authorize_read(
            conversation_id, tenant_id=tenant_id, user_id=user_id,
        )
    except SessionReadDeniedError as exc:
        raise HTTPException(status_code=404, detail="plugin_ui_session_not_found") from exc
    return conversation_id


async def resolve_owned_kernel_session(db: Any, *, tenant_id: str, user_id: str,
                                       conversation_id: str) -> str:
    try:
        access = await SessionReadAuthorizer(db).authorize_read(
            conversation_id, tenant_id=tenant_id, user_id=user_id,
        )
    except SessionReadDeniedError as exc:
        raise HTTPException(status_code=404, detail="plugin_ui_session_not_found") from exc
    binding = await KernelBindingRepository(db).current(
        conversation_id, tenant_id=tenant_id, user_id=user_id,
    )
    if (access.role != "owner" or binding is None or
            binding.get("execution_location") != "server"):
        raise HTTPException(status_code=404, detail="plugin_ui_session_not_found")
    return binding["kernel_session_id"]
