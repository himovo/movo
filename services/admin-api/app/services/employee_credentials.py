from __future__ import annotations

from typing import Any


MIN_PASSWORD_LENGTH = 10


def normalize_employee_credentials(
    *,
    source: str,
    login_name: str,
    password: str,
    creating: bool,
    has_existing_password: bool = False,
) -> tuple[str, str]:
    """Validate local credentials and remove them for externally managed users."""
    normalized_login = login_name.strip()

    if source != "local":
        if password:
            raise ValueError("外部身份用户不能设置本地密码")
        return "", ""

    if not normalized_login:
        raise ValueError("请填写登录名")

    password_is_required = creating or not has_existing_password
    if password_is_required and not password:
        raise ValueError("请设置至少 10 位密码")
    if password and len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError("密码至少 10 位")

    return normalized_login, password


def redact_credential_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Prevent plaintext passwords from entering audit logs."""
    result = dict(payload)
    for key in ("initialPassword", "resetPassword", "password"):
        if key in result:
            result[key] = "***" if result[key] else ""
    return result
