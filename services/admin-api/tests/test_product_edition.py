from app.core.product_edition import (
    billing_enabled,
    community_organization_fields,
    is_community_organization,
    member_limit,
)


def test_community_edition_has_no_member_or_billing_limit() -> None:
    org = community_organization_fields(
        main_id="tenant-community",
        org_name="MOVO Team",
        owner_user_id="owner-1",
        total_points=2_000_000,
    )

    assert is_community_organization(org) is True
    assert member_limit(org) is None
    assert billing_enabled(org) is False
    assert org["tier"] == "community"
    assert org["is_own_model"] is True


def test_legacy_cloud_organization_keeps_existing_member_limit() -> None:
    org = {"tier": "free", "user_limit": 5}

    assert is_community_organization(org) is False
    assert member_limit(org) == 5
    assert billing_enabled(org) is True
