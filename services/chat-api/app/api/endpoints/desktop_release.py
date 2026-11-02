"""Public, secret-free identity for desktop compatibility checks."""

from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(tags=["desktop-release"])


@router.get("/desktop/release")
def desktop_release() -> dict[str, str]:
    return {
        "source_revision": os.getenv("MOVO_SOURCE_REVISION", "").strip(),
        "source_version": os.getenv("MOVO_SOURCE_VERSION", "").strip(),
    }
