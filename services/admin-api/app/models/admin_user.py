from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AdminUser:
    username: str
    password_hash: str
    password_salt: str
    display_name: str
    role_name: str
    org_name: str
    status: str = "active"
    is_super_admin: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: datetime | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "password_salt": self.password_salt,
            "display_name": self.display_name,
            "role_name": self.role_name,
            "org_name": self.org_name,
            "status": self.status,
            "is_super_admin": self.is_super_admin,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_login_at": self.last_login_at,
        }
