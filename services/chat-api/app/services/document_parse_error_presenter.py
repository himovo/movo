from __future__ import annotations

import re
from typing import Any


def user_facing_parse_error(
    *,
    parse_error: Any,
    filename: str = "",
    has_object_path: bool = False,
    has_signed_url: bool = False,
) -> str:
    """Return a user-safe document parse failure reason.

    Raw parser errors often describe internal transport details, such as a
    signed URL returning HTTP 404 after a fallback attempt. Those details are
    useful in logs but misleading as user guidance because the uploaded file may
    still be valid while the parser service or fallback source failed.
    """
    error = re.sub(r"\s+", " ", str(parse_error or "")).strip()
    if not error:
        return "文件解析失败，未返回明确错误原因。请稍后重试或重新上传文件。"

    lowered = error.lower()
    if "404" in lowered or "not found" in lowered or "no such key" in lowered:
        if has_object_path or has_signed_url:
            return "文件已收到，但解析服务读取文件内容失败。请稍后重试；如果仍失败，请重新上传文件。"
        return "文件解析服务未能读取到文件内容。请重新上传文件后再试。"

    if any(token in lowered for token in ("timeout", "timed out", "connection", "network")):
        return "文件解析服务暂时不可用或网络超时。请稍后重试。"

    if any(token in lowered for token in ("unsupported", "not supported", "format")):
        return "当前文件格式暂不支持解析。请转换为支持的文档格式后再试。"

    if any(token in lowered for token in ("permission", "forbidden", "unauthorized", "403", "401")):
        return "文件解析服务暂时没有权限读取该文件。请重新上传文件或稍后重试。"

    prefix = f"文件《{filename}》" if filename else "文件"
    return f"{prefix}解析失败。请稍后重试或重新上传文件。"
