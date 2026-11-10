"""Short-lived, scope-bound launch tickets for isolated plugin pages."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import hmac
import json
import time


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class PluginUiTicket:
    tenant_id: str
    user_id: str
    plugin_id: str
    plugin_version: str
    profile_version: str
    expires_at: int
    kernel_session_id: str | None = None


class PluginUiTickets:
    def __init__(self, secret: str, *, lifetime_seconds: int = 3600) -> None:
        if len(secret) < 32:
            raise ValueError("plugin UI signing secret must contain at least 32 characters")
        self._secret = secret.encode("utf-8")
        self.lifetime_seconds = lifetime_seconds

    def issue(self, *, tenant_id: str, user_id: str, plugin_id: str,
              plugin_version: str, profile_version: str,
              kernel_session_id: str | None = None) -> str:
        payload = {"t": tenant_id, "u": user_id, "p": plugin_id,
                   "v": plugin_version, "r": profile_version,
                   "e": int(time.time()) + self.lifetime_seconds}
        if kernel_session_id:
            payload["s"] = kernel_session_id
        encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        signature = _encode(hmac.digest(self._secret, encoded.encode("ascii"), hashlib.sha256))
        return f"{encoded}.{signature}"

    def verify(self, token: str) -> PluginUiTicket:
        try:
            encoded, signature = token.split(".", 1)
            expected = _encode(hmac.digest(self._secret, encoded.encode("ascii"), hashlib.sha256))
            if not hmac.compare_digest(signature, expected):
                raise ValueError("invalid plugin UI ticket")
            payload = json.loads(_decode(encoded))
            if not isinstance(payload, dict) or int(payload["e"]) <= time.time():
                raise ValueError("expired plugin UI ticket")
            values = [payload[key] for key in ("t", "u", "p", "v", "r")]
            if not all(isinstance(value, str) and value for value in values):
                raise ValueError("invalid plugin UI ticket")
            session_id = payload.get("s")
            if session_id is not None and (not isinstance(session_id, str) or not session_id):
                raise ValueError("invalid plugin UI ticket")
            return PluginUiTicket(*values, int(payload["e"]), session_id)
        except (binascii.Error, KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise ValueError("invalid or expired plugin UI ticket") from exc
