from __future__ import annotations

import asyncio
import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Dict, Optional

from pydantic import BaseModel, Field


class EnvSession(BaseModel):
    env_session_id: str
    user_id: str
    status: str = "ACTIVE"
    leased_by: str = ""
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(minutes=30))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class EnvManager:
    def __init__(self, max_sessions_per_user: int = 3) -> None:
        self.max_sessions_per_user = max(1, int(max_sessions_per_user))
        self._lock = asyncio.Lock()
        self._sessions: Dict[str, EnvSession] = {}

    async def create(self, user_id: str, leased_by: str) -> EnvSession:
        async with self._lock:
            active = [s for s in self._sessions.values() if s.user_id == user_id and s.status == "ACTIVE"]
            if len(active) >= self.max_sessions_per_user:
                oldest = sorted(active, key=lambda x: x.created_at)[0]
                oldest.status = "RECLAIMED"
                oldest.updated_at = datetime.utcnow()
                self._sessions[oldest.env_session_id] = oldest
            sid = f"env_{uuid.uuid4().hex[:12]}"
            session = EnvSession(env_session_id=sid, user_id=user_id, leased_by=leased_by)
            self._sessions[sid] = session
            return deepcopy(session)

    async def renew(self, env_session_id: str, minutes: int = 15) -> Optional[EnvSession]:
        async with self._lock:
            row = self._sessions.get(env_session_id)
            if not row:
                return None
            row.expires_at = datetime.utcnow() + timedelta(minutes=max(1, int(minutes)))
            row.updated_at = datetime.utcnow()
            self._sessions[env_session_id] = row
            return deepcopy(row)

    async def freeze(self, env_session_id: str) -> Optional[EnvSession]:
        async with self._lock:
            row = self._sessions.get(env_session_id)
            if not row:
                return None
            row.status = "FROZEN"
            row.updated_at = datetime.utcnow()
            self._sessions[env_session_id] = row
            return deepcopy(row)

    async def release(self, env_session_id: str, status: str = "RECLAIMED") -> None:
        async with self._lock:
            row = self._sessions.get(env_session_id)
            if not row:
                return
            row.status = status
            row.updated_at = datetime.utcnow()
            self._sessions[env_session_id] = row

    async def get(self, env_session_id: str) -> Optional[EnvSession]:
        async with self._lock:
            row = self._sessions.get(env_session_id)
            return deepcopy(row) if row else None

    async def gc_expired(self) -> int:
        async with self._lock:
            now = datetime.utcnow()
            count = 0
            for sid, row in list(self._sessions.items()):
                if row.status in {"ACTIVE", "FROZEN"} and row.expires_at <= now:
                    row.status = "RECLAIMED"
                    row.updated_at = now
                    self._sessions[sid] = row
                    count += 1
            return count

    async def metrics(self) -> Dict[str, int]:
        async with self._lock:
            counts = {"ACTIVE": 0, "FROZEN": 0, "RECLAIMED": 0}
            for row in self._sessions.values():
                st = row.status if row.status in counts else "RECLAIMED"
                counts[st] += 1
            return counts
