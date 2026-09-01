from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.core.config import settings
from app.core.security import decode_access_token
from app.repositories.org_user_repository import find_account_by_username
from app.repositories.admin_session_repository import find_session


async def get_current_admin_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.replace("Bearer ", "", 1).strip()
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    subject = payload.get("sub") or {}
    username = subject.get("username")
    session_id = subject.get("session_id")
    main_id = str(subject.get("main_id") or settings.bootstrap_main_id)
    if not username or not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    session = await find_session(str(session_id))
    if session is None or session.get("status") != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is not active")

    user = await find_account_by_username(str(username), main_id)
    if user is None or user.get("status") != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin user is not available")

    role_name = user.get("role_name") or "组织管理员"
    org_name = user.get("org_name") or user.get("group_code") or "组织账户"
    return {
        **user,
        "main_id": main_id,
        "role_name": role_name,
        "org_name": org_name,
        "display_name": user.get("display_name") or user.get("username") or "",
    }
