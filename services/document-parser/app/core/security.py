from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.core.config import settings


async def verify_service_token(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.replace("Bearer ", "", 1).strip()
    if token != settings.service_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid service token")
