from __future__ import annotations

from app.enterprise_capabilities.browser.engine.navigation_provenance import (
    assess_navigation_provenance,
    normalize_http_url,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _obs(url: str, elements=None, page_text: str = "") -> Observation:
    return Observation(
        url=url,
        title="",
        elements=list(elements or []),
        page_text=page_text,
    )


def test_normalizes_default_ports_relative_links_and_unreserved_escapes() -> None:
    assert normalize_http_url("/a/%7Euser", base_url="https://EXAMPLE.test:443/root") == (
        "https://example.test/a/~user"
    )


def test_allows_exact_observed_href_including_relative_href() -> None:
    assessment = assess_navigation_provenance(
        target_url="https://example.test/publish/article",
        current_observation=_obs(
            "https://example.test/home",
            [{"ref": "publish", "href": "/publish/article"}],
        ),
    )

    assert assessment.allowed is True
    assert assessment.source == "observed_href"


def test_blocks_hallucinated_same_site_route() -> None:
    assessment = assess_navigation_provenance(
        target_url="https://example.test/#/statistics",
        current_observation=_obs(
            "https://example.test/home",
            [{"ref": "statistics", "role": "button", "name": "统计分析"}],
        ),
    )

    assert assessment.allowed is False
    assert "same-site route" in assessment.reason


def test_relative_hallucinated_route_cannot_bypass_the_gate() -> None:
    assessment = assess_navigation_provenance(
        target_url="/#/statistics",
        current_observation=_obs("https://example.test/home"),
    )

    assert assessment.allowed is False


def test_relative_path_in_page_text_is_not_treated_as_provenance() -> None:
    assessment = assess_navigation_provenance(
        target_url="https://example.test/statistics",
        current_observation=_obs(
            "https://example.test/home",
            page_text="统计分析 /statistics",
        ),
    )

    assert assessment.allowed is False


def test_allows_absolute_url_rendered_in_page_text() -> None:
    assessment = assess_navigation_provenance(
        target_url="https://docs.example.test/help",
        current_observation=_obs(
            "https://example.test/home",
            page_text="帮助地址：https://docs.example.test/help",
        ),
    )

    assert assessment.allowed is True
    assert assessment.source == "observed_text_url"


def test_blocks_first_step_that_ignores_explicit_user_url() -> None:
    assessment = assess_navigation_provenance(
        target_url="https://example.test/guessed",
        current_observation=_obs("about:blank"),
        original_user_request="请打开 https://example.test/start",
    )

    assert assessment.allowed is False


def test_name_only_bootstrap_and_cross_site_transition_remain_compatible() -> None:
    bootstrap = assess_navigation_provenance(
        target_url="https://www.baidu.com/",
        current_observation=_obs("about:blank"),
        original_user_request="打开百度",
    )
    cross_site = assess_navigation_provenance(
        target_url="https://wikipedia.org/",
        current_observation=_obs("https://www.baidu.com/"),
        original_user_request="先用百度，再去维基百科",
    )

    assert bootstrap.allowed is True and bootstrap.audit_only is True
    assert cross_site.allowed is True and cross_site.audit_only is True


def test_unrelated_saved_site_profile_does_not_block_name_only_bootstrap() -> None:
    assessment = assess_navigation_provenance(
        target_url="https://www.baidu.com/",
        current_observation=_obs("about:blank"),
        original_user_request="打开百度",
        site_profiles=[{
            "name": "公司后台",
            "entry_url": "https://internal.example.test/home",
        }],
    )

    assert assessment.allowed is True
    assert assessment.audit_only is True


def test_system_owned_navigation_bypasses_provenance_gate() -> None:
    assessment = assess_navigation_provenance(
        target_url="https://example.test/runtime-route",
        current_observation=_obs("https://example.test/home"),
        system_owned=True,
    )

    assert assessment.allowed is True
    assert assessment.source == "runtime"


def test_previous_observation_href_remains_grounded_after_page_changes() -> None:
    assessment = assess_navigation_provenance(
        target_url="https://example.test/detail/1",
        current_observation=_obs("https://example.test/menu"),
        history_observations=[
            _obs("https://example.test/list", [{"href": "/detail/1"}]),
        ],
    )

    assert assessment.allowed is True
    assert assessment.source == "observed_href"
