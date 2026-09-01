from app.product.extensions import COMMUNITY_FEATURES, community_extension


def test_community_extension_disables_cloud_only_capabilities() -> None:
    payload = community_extension().capability_payload()

    assert payload["edition"] == "community"
    assert payload["extensionId"] == "movo.community"
    assert payload["features"] == COMMUNITY_FEATURES
    assert payload["features"]["passwordLogin"] is True
    assert payload["features"]["smsLogin"] is False
    assert payload["features"]["billing"] is False
