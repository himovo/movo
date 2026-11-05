"""Restrict host-wide package and image transfer to system operators."""

from __future__ import annotations

from fastapi import Depends, HTTPException

from app.api.deps import get_current_admin_user


async def get_system_operator(admin: dict = Depends(get_current_admin_user)) -> dict:
    if admin.get("group_code") != "system_admin":
        raise HTTPException(status_code=403, detail="system_operator_required")
    return admin
