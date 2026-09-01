from __future__ import annotations

from app.core.db import get_db


SETUP_SCOPED_COLLECTIONS = (
    "admin_account_groups",
    "admin_accounts",
    "admin_model_instances",
    "departments",
    "end_users",
    "end_user_org_relations",
    "end_user_position_roles",
    "position_roles",
    "position_role_migrations",
    "position_role_audit_logs",
    "org_quota_policies",
    "user_quota_policies",
    "user_token_allocation_logs",
    "external_search_configs",
    "knowledge_document_settings",
    "organizations",
)


async def cleanup_failed_setup(main_id: str) -> None:
    """Compensate a failed first-time setup for its newly generated tenant only."""
    if not main_id or len(main_id) < 20:
        raise ValueError("refusing to clean an invalid setup tenant id")
    db = get_db()
    for collection_name in SETUP_SCOPED_COLLECTIONS:
        await db[collection_name].delete_many({"main_id": main_id})
