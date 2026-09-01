"""Browser-session identity shared by the DSH adapter and desktop surface."""

from __future__ import annotations

from typing import Any


def resolve_browser_session_id(*, conversation_id: str, resume: dict[str, Any]) -> str:
    """Keep Browser Agent work visible in the ASKAI conversation surface.

    DSH kernel sessions are execution identities and must never become desktop
    browser identities. A trusted resume record may preserve an older browser
    session; new missions always use the ASKAI conversation identifier that the
    Electron renderer selects.
    """
    resumed = str(resume.get("browser_session_id") or "").strip()
    visible = str(conversation_id or "").strip()
    return resumed or visible or "default"


__all__ = ["resolve_browser_session_id"]
