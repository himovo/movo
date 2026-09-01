"""Stable core API available to separately distributed product extensions.

The implementation remains owned by MOVO. Extensions import through this
module instead of reaching into endpoint-private helpers directly.
"""

from app.api.endpoints.auth import (
    ADMIN_ACCOUNT_COLLECTION,
    ADMIN_SESSION_COLLECTION,
    DEPARTMENT_COLLECTION,
    USER_COLLECTION,
    USER_INVITE_COLLECTION,
    USER_ORG_REL_COLLECTION,
    USER_SESSION_COLLECTION,
    ApiResponse,
    _assign_user_primary_department,
    _avatar_fields_from_user,
    _check_org_name_duplicate,
    _create_admin_token,
    _create_login_challenge,
    _create_session,
    _ensure_root_department,
    _is_valid_tenant_main_id,
    _load_available_tenants,
    _now,
    _profile_with_policy,
    _resolve_primary_department,
    _resolve_session_user,
    _space_type_from_user,
    _t,
)
from app.core.db import get_db
from app.core.tenant import resolve_main_id
from app.services.end_user_tenant_access import load_tenant_candidates, resolve_space_type

__all__ = [name for name in globals() if not name.startswith("__")]
