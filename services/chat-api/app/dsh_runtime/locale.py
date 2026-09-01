"""Locale resolution owned by the DSH boundary."""

from __future__ import annotations

import re


def resolve_turn_locale(text: str, explicit: str | None = None) -> str:
    requested = str(explicit or "").strip().lower().replace("_", "-")
    if requested.startswith("zh"):
        return "zh-CN"
    if requested.startswith("en"):
        return "en-US"
    return "zh-CN" if re.search(r"[\u4e00-\u9fff]", str(text or "")) else "en-US"


__all__ = ["resolve_turn_locale"]
