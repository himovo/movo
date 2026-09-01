from app.enterprise_capabilities.browser.engine.contexts.search_progress import (
    capture_search_baseline,
    infer_search_result_from_observation,
    search_submission_confirmed,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _obs(url: str, title: str, links=(), text: str = "") -> Observation:
    return Observation(
        url=url,
        title=title,
        page_text=text,
        elements=[
            {"ref": f"e{index}", "role": "link", "href": href, "name": f"result {index}"}
            for index, href in enumerate(links, 1)
        ],
    )


def test_search_requires_more_than_enter_and_page_text_churn():
    before = _obs("https://example.test/explore", "Explore", ["/home"], "员工服务台")
    baseline = capture_search_baseline("员工服务台", before)
    assert search_submission_confirmed(baseline, before, {"diagnostics": {"pageTextChanged": True}}) is False


def test_search_accepts_navigation_or_a_new_result_collection():
    before = _obs("https://example.test/explore", "Explore", ["/home"])
    baseline = capture_search_baseline("员工服务台", before)
    navigated = _obs(
        "https://example.test/search?q=%E5%91%98%E5%B7%A5%E6%9C%8D%E5%8A%A1%E5%8F%B0",
        "员工服务台 Results",
        ["/p/1", "/p/2"],
    )
    assert search_submission_confirmed(baseline, navigated, {}) is True

    same_url_results = _obs(
        before.url,
        before.title,
        ["/home", "/p/1", "/p/2"],
        "员工服务台相关问题",
    )
    assert search_submission_confirmed(baseline, same_url_results, {}) is True


def test_short_result_routes_are_recognised_from_generic_query_evidence():
    for url, query in (
        ("https://search.test/s?wd=Askbot", "Askbot"),
        ("https://search.test/web?query=Askbot", "Askbot"),
        ("https://search.test/?q=Askbot", "Askbot"),
    ):
        observation = _obs(
            url,
            f"{query} - results",
            ["https://one.test/result", "https://two.test/result"],
            f"Results for {query}",
        )

        result = infer_search_result_from_observation(observation)

        assert result is not None
        assert result.query == query


def test_hash_routed_result_page_is_recognised_without_provider_rules():
    observation = _obs(
        "https://example.test/app#/results?q=knowledge%20base",
        "Knowledge base results",
        ["/doc/1", "/doc/2"],
        "knowledge base matches",
    )

    result = infer_search_result_from_observation(observation)

    assert result is not None
    assert result.query == "knowledge base"


def test_query_parameter_without_result_collection_is_not_enough():
    observation = _obs(
        "https://example.test/settings?q=Askbot",
        "Settings",
        ["/home"],
        "Askbot account settings",
    )

    assert infer_search_result_from_observation(observation) is None


def test_navigation_to_unrelated_page_does_not_confirm_search():
    before = _obs("https://example.test/", "Search", ["/home"])
    baseline = capture_search_baseline("Askbot", before)
    login = _obs(
        "https://example.test/login",
        "Sign in",
        ["/help", "/privacy", "/terms"],
        "Continue to your account",
    )

    assert search_submission_confirmed(
        baseline,
        login,
        {"observation": {"effects": [{"kind": "navigation"}]}},
    ) is False


def test_reconciliation_rejects_a_different_query_than_the_requested_one():
    observation = _obs(
        "https://example.test/?q=Different",
        "Different results",
        ["/one", "/two"],
        "Different",
    )

    assert infer_search_result_from_observation(
        observation,
        expected_query="Askbot",
    ) is None
