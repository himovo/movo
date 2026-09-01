"""Interpret user-selected media delivery methods independently of websites."""
from __future__ import annotations

import re


_IMAGE_TERMS = re.compile(
    r"(?:图片|图像|配图|插图|照片|image|picture|photo)",
    re.I,
)
_PASTE_TERMS = re.compile(
    r"(?:复制|拷贝|粘贴|贴入|copy|paste)",
    re.I,
)
_NEGATED_PASTE = re.compile(
    r"(?:(?:不要|禁止|无需|不能|不使用).{0,10}(?:复制|拷贝|粘贴|贴入)|"
    r"(?:do not|don't|must not|without).{0,12}(?:copy|paste))",
    re.I,
)


def prefers_media_paste(original_request: str) -> bool:
    """Recognize an explicit delivery instruction, not a site or UI label."""

    request = str(original_request or "")
    return bool(
        not _NEGATED_PASTE.search(request)
        and _IMAGE_TERMS.search(request)
        and _PASTE_TERMS.search(request)
    )


__all__ = ["prefers_media_paste"]
