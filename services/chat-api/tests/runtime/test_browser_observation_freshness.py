from app.enterprise_capabilities.browser.engine.observation_freshness import adopt_probed_observation
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _observation(url: str, *, fresh: bool, screenshot: str | None = None) -> Observation:
    return Observation(
        url=url,
        title="",
        elements=[],
        revision="probe:1" if fresh else "",
        fresh=fresh,
        screenshot=screenshot,
    )


def test_fresh_about_blank_probe_replaces_uninitialized_state() -> None:
    current = _observation("about:blank", fresh=False)
    probed = _observation("about:blank", fresh=True)

    adopted = adopt_probed_observation(current, probed)

    assert adopted is probed
    assert adopted.fresh is True


def test_invalid_probe_keeps_current_observation() -> None:
    current = _observation("about:blank", fresh=False)
    probed = _observation("", fresh=True)

    assert adopt_probed_observation(current, probed) is current
    assert adopt_probed_observation(current, None) is current


def test_same_page_probe_preserves_existing_screenshot() -> None:
    current = _observation("https://example.test", fresh=True, screenshot="image")
    probed = _observation("https://example.test", fresh=True)

    adopted = adopt_probed_observation(current, probed)

    assert adopted is not probed
    assert adopted.screenshot == "image"
