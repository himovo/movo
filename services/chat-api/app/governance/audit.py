from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from app.core.db import get_db


async def record_position_policy_event(
    *, tenant_id: str, user_id: str, action: str, target: str, details: dict[str, Any] | None = None,
) -> None:
    await get_db().position_role_audit_logs.insert_one({
        "_id": uuid.uuid4().hex,
        "main_id": tenant_id,
        "actor": user_id,
        "action": action,
        "target_type": "employee",
        "target_id": user_id,
        "details": {"target": target, **dict(details or {})},
        "created_at": datetime.now(timezone.utc),
    })
