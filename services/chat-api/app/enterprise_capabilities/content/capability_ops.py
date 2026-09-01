from __future__ import annotations


def capability_family(capability_id: str) -> str:
    raw = str(capability_id or "").strip().lower()
    return raw.split(".", 1)[0] if "." in raw else raw
