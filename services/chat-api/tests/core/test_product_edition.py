from app.core.product_edition import billing_enabled, member_limit, product_edition_fields


def test_community_product_fields_are_unlimited_and_non_billable() -> None:
    org = {"edition": "community", "tier": "community", "user_limit": 5, "billing_enabled": True}

    assert member_limit(org) is None
    assert billing_enabled(org) is False
    assert product_edition_fields(org) == {
        "edition": "community",
        "billingEnabled": False,
        "memberLimit": None,
    }


def test_cloud_product_fields_preserve_limit() -> None:
    assert product_edition_fields({"tier": "pro", "user_limit": 50}) == {
        "edition": "cloud",
        "billingEnabled": True,
        "memberLimit": 50,
    }
