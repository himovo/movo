"""Short-lived least-privilege token for DSH tool and approval calls."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolGatewayClaims:
    tenant_id: str
    user_id: str
    profile_version: str
    tool_names: frozenset[str]
    scopes: frozenset[str]
    issued_at: int
    expires_at: int


class ToolGatewayTokenService:
    def __init__(self, secret: str, *, ttl_seconds: int = 900) -> None:
        if len(secret) < 16:
            raise ValueError("Tool Gateway token secret must contain at least 16 characters")
        self._key = hashlib.sha256(("tool:" + secret).encode()).digest()
        self._ttl = max(30, int(ttl_seconds))

    def issue(
        self,
        *,
        tenant_id: str,
        user_id: str,
        profile_version: str,
        tool_names: list[str],
        scopes: list[str],
    ) -> str:
        now = int(time.time())
        payload = {
            "aud": "askai-tool-gateway",
            "tenant_id": tenant_id,
            "user_id": user_id,
            "profile_version": profile_version,
            "tool_names": sorted(set(tool_names)),
            "scopes": sorted(set(scopes)),
            "iat": now,
            "exp": now + self._ttl,
            "jti": secrets.token_hex(8),
        }
        encoded = self._encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        signature = self._encode(hmac.new(self._key, encoded.encode(), hashlib.sha256).digest())
        return f"{encoded}.{signature}"

    def verify(self, token: str) -> ToolGatewayClaims:
        try:
            encoded, signature = token.split(".", 1)
            expected = self._encode(hmac.new(self._key, encoded.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            payload = json.loads(self._decode(encoded))
            if payload.get("aud") != "askai-tool-gateway" or int(payload.get("exp") or 0) <= int(time.time()):
                raise ValueError
            return ToolGatewayClaims(
                tenant_id=str(payload["tenant_id"]),
                user_id=str(payload["user_id"]),
                profile_version=str(payload["profile_version"]),
                tool_names=frozenset(str(item) for item in payload.get("tool_names", [])),
                scopes=frozenset(str(item) for item in payload.get("scopes", [])),
                issued_at=int(payload["iat"]),
                expires_at=int(payload["exp"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Tool Gateway token is invalid or expired") from exc

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

    @staticmethod
    def _decode(value: str) -> str:
        return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode()).decode()

