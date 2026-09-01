from app.enterprise_capabilities.browser.engine.auth_state import AuthTransitionTracker, assessment_from_payload, site_scope


def test_site_scope_groups_cross_subdomain_login_redirects():
    assert site_scope("https://mail.example.com/login") == "example.com"
    assert site_scope("https://app.example.com/inbox") == "example.com"
    assert site_scope("https://id.example.co.uk/login") == "example.co.uk"


def test_auth_transition_requires_two_stable_business_observations():
    tracker = AuthTransitionTracker()
    assert tracker.observe(
        url="https://id.example.com/login",
        assessment={"state": "required"},
        has_page_evidence=True,
    ) == "required"
    assert tracker.observe(
        url="https://app.example.com/home",
        assessment={"state": "unknown"},
        has_page_evidence=True,
    ) == "verifying"
    assert tracker.observe(
        url="https://app.example.com/home",
        assessment={"state": "unknown"},
        has_page_evidence=True,
    ) == "authenticated"


def test_legacy_login_signal_is_still_understood():
    result = assessment_from_payload({"observation": {"loginDetected": True}})
    assert result["state"] == "required"
