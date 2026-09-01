from __future__ import annotations

import re
from typing import Any


REQUEST_STATUS_COMPLETED = "completed"
REQUEST_STATUS_USER_CANCELLED = "user_cancelled"
REQUEST_STATUS_RUNTIME_ERROR = "runtime_error"
REQUEST_STATUS_NETWORK_ERROR = "network_error"

REQUEST_STATUS_VALUES = {
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_USER_CANCELLED,
    REQUEST_STATUS_RUNTIME_ERROR,
    REQUEST_STATUS_NETWORK_ERROR,
}

_NETWORK_ERROR_RE = re.compile(
    r"network|connection|connect|timeout|timed out|read timeout|socket|ssl|dns|"
    r"gateway|502|503|504|upstream|temporarily unavailable",
    re.I,
)


def normalize_request_status(
    *,
    execution_status: Any = "",
    failed_count: Any = 0,
    error_text: Any = "",
) -> str:
    status = str(execution_status or "").strip().lower()
    failures = int(failed_count or 0)
    error = str(error_text or "")
    if status == "cancelled":
        return REQUEST_STATUS_USER_CANCELLED
    if status == "failed":
        return REQUEST_STATUS_NETWORK_ERROR if _NETWORK_ERROR_RE.search(error) else REQUEST_STATUS_RUNTIME_ERROR
    if failures > 0:
        return REQUEST_STATUS_NETWORK_ERROR if _NETWORK_ERROR_RE.search(error) else REQUEST_STATUS_RUNTIME_ERROR
    return REQUEST_STATUS_COMPLETED
