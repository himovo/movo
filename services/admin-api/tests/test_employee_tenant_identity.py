from app.services.employee_tenant_identity import authoritative_tenant_names, employee_tenant_fields


def test_enterprise_employee_identity_uses_display_name() -> None:
    assert employee_tenant_fields("org_deadbeef", "示例科技") == {
        "org_name": "示例科技",
        "space_type": "enterprise",
    }


def test_personal_space_identity_is_preserved() -> None:
    assert employee_tenant_fields("personal_1", "个人空间")["space_type"] == "personal"


def test_admin_identity_wins_over_stale_billing_organization_name() -> None:
    names = authoritative_tenant_names(
        [{"main_id": "org_1", "org_name": "个人空间"}],
        [{"main_id": "org_1", "org_name": "示例科技"}],
    )
    assert names["org_1"] == "示例科技"
