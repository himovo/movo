from app.enterprise_capabilities.browser.engine.entry_preflight import (
    ENTRY_URL_REQUIRED,
    assess_entry_preflight,
)


def test_blank_page_without_a_grounded_entry_fails_before_planning() -> None:
    result = assess_entry_preflight(current_url="about:blank", candidates=[])

    assert result.ready is False
    assert result.code == ENTRY_URL_REQUIRED
    assert "target_url" in result.reason


def test_blank_page_with_a_grounded_entry_can_bootstrap() -> None:
    result = assess_entry_preflight(
        current_url="about:blank",
        candidates=[{"url": "https://example.com", "source": "user_request"}],
    )

    assert result.ready is True


def test_live_page_can_be_used_for_current_page_continuation() -> None:
    result = assess_entry_preflight(
        current_url="https://example.com/after-login",
        candidates=[],
    )

    assert result.ready is True


def test_browser_error_page_needs_a_grounded_recovery_entry() -> None:
    result = assess_entry_preflight(
        current_url="chrome-error://chromewebdata/",
        candidates=[],
    )

    assert result.ready is False
    assert result.code == ENTRY_URL_REQUIRED
