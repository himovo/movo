"""Keep internal ASKAI artifacts out of the browser navigation contract."""

from __future__ import annotations

from urllib.parse import urlparse


_INTERNAL_FILE_PREFIXES = ("/askai-api/api/files/", "/api/files/")


def reject_internal_artifact_target(target_url: str) -> None:
    value = str(target_url or "").strip()
    if not value:
        return
    path = str(urlparse(value).path or "")
    if any(path.startswith(prefix) for prefix in _INTERNAL_FILE_PREFIXES):
        raise ValueError(
            "MOVO internal artifacts cannot be opened with browser_task; "
            "pass their object_path to the matching document or image tool"
        )


__all__ = ["reject_internal_artifact_target"]
