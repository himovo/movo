"""Generic browser authentication assessment and transition helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict
from urllib.parse import urlparse


BLOCKING_STATES = {"required", "registration_required", "authenticating", "failed"}


def site_scope(url: str) -> str:
    """Return a conservative registrable-domain-like scope without site rules."""
    try:
        host = (urlparse(str(url or "")).hostname or "").lower().strip(".")
    except Exception:
        return ""
    if not host or host == "localhost" or host.replace(".", "").isdigit():
        return host
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    second_level_namespaces = {"ac", "co", "com", "edu", "gov", "net", "org"}
    if len(labels[-1]) == 2 and labels[-2] in second_level_namespaces:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def assessment_from_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"state": "unknown", "confidence": 0.0, "signals": []}
    nested = payload.get("observation")
    source = nested if isinstance(nested, dict) else payload
    auth = source.get("auth")
    if not isinstance(auth, dict):
        return {
            "state": "required" if bool(source.get("loginDetected")) else "unknown",
            "confidence": 0.7 if bool(source.get("loginDetected")) else 0.0,
            "signals": ["legacy_login_detected"] if bool(source.get("loginDetected")) else [],
        }
    state = str(auth.get("state") or "unknown").strip().lower()
    if state not in BLOCKING_STATES | {"authenticated", "unknown"}:
        state = "unknown"
    return {
        "state": state,
        "confidence": max(0.0, min(1.0, float(auth.get("confidence") or 0.0))),
        "signals": [str(item) for item in list(auth.get("signals") or [])[:16]],
    }


@dataclass
class AuthTransitionTracker:
    """Recognize stable login completion without relying on a specific site."""

    scope: str = ""
    blocking_seen: bool = False
    stable_success_observations: int = 0

    def observe(self, *, url: str, assessment: Dict[str, Any], has_page_evidence: bool) -> str:
        state = str(assessment.get("state") or "unknown")
        current_scope = site_scope(url)
        if not self.scope and current_scope:
            self.scope = current_scope
        if state in BLOCKING_STATES:
            self.blocking_seen = True
            self.stable_success_observations = 0
            return state
        same_site = not self.scope or not current_scope or current_scope == self.scope
        success_signal = state == "authenticated" or (
            self.blocking_seen and same_site and has_page_evidence and state == "unknown"
        )
        if success_signal:
            self.stable_success_observations += 1
            if self.stable_success_observations >= 2:
                return "authenticated"
            return "verifying"
        self.stable_success_observations = 0
        return state
