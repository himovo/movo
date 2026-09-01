from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class ApprovalTicket:
    action_id: str
    resume_token: str
    actor_id: str
    reason_code: str
    human_prompt: str
    expires_at: datetime
    required_roles: List[str] | None = None
    used: bool = False
    created_at: datetime = datetime.utcnow()
    used_at: Optional[datetime] = None
    denied: bool = False


class ApprovalRuntime:
    """One-time approval token runtime."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tickets: Dict[str, ApprovalTicket] = {}

    async def issue(
        self,
        *,
        action_id: str,
        resume_token: str,
        actor_id: str,
        reason_code: str,
        human_prompt: str,
        expires_at: datetime,
        required_roles: Optional[List[str]] = None,
    ) -> ApprovalTicket:
        async with self._lock:
            ticket = ApprovalTicket(
                action_id=action_id,
                resume_token=resume_token,
                actor_id=actor_id,
                reason_code=reason_code,
                human_prompt=human_prompt,
                expires_at=expires_at,
                required_roles=list(required_roles or []),
            )
            self._tickets[action_id] = ticket
            return deepcopy(ticket)

    async def validate_and_consume(
        self,
        *,
        action_id: str,
        resume_token: str,
        actor_id: str,
        actor_roles: Optional[List[str]] = None,
    ) -> bool:
        async with self._lock:
            row = self._tickets.get(action_id)
            if not row:
                return False
            if row.used or row.denied:
                return False
            if row.resume_token != resume_token:
                return False
            if row.actor_id and row.actor_id != actor_id:
                return False
            if row.required_roles:
                roles = set(actor_roles or [])
                if not roles.intersection(set(row.required_roles)):
                    return False
            if row.expires_at < datetime.utcnow():
                return False
            row.used = True
            row.used_at = datetime.utcnow()
            self._tickets[action_id] = row
            return True

    async def deny(self, *, action_id: str, actor_id: str, actor_roles: Optional[List[str]] = None) -> bool:
        async with self._lock:
            row = self._tickets.get(action_id)
            if not row:
                return False
            if row.actor_id and row.actor_id != actor_id:
                return False
            if row.required_roles:
                roles = set(actor_roles or [])
                if not roles.intersection(set(row.required_roles)):
                    return False
            if row.used:
                return False
            row.denied = True
            self._tickets[action_id] = row
            return True
