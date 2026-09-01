from app.product.extensions import community_extension


def test_community_admin_extension_has_unlimited_members_and_no_billing() -> None:
    extension = community_extension()

    assert extension.edition == "community"
    assert extension.routers == ()
    assert extension.organization_defaults["billing_enabled"] is False
    assert extension.organization_defaults["user_limit"] is None
