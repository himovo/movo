from app.services.organization_tools import (
    organization_scope_clause,
    organization_tool_fields,
    organization_tool_query,
    replace_tool_id,
)


def test_organization_query_accepts_explicit_and_legacy_organization_tools() -> None:
    assert organization_tool_query("tenant-a", status="active") == {
        "main_id": "tenant-a",
        "status": "active",
        **organization_scope_clause(),
    }


def test_admin_created_tool_has_explicit_enterprise_ownership() -> None:
    assert organization_tool_fields() == {"scope": "organization", "owner_user_id": ""}


def test_role_rewire_preserves_order_and_deduplicates() -> None:
    assert replace_tool_id(["personal-crm", "search", "org-crm"], "personal-crm", "org-crm") == [
        "org-crm",
        "search",
    ]
