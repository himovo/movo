from types import SimpleNamespace

from app.enterprise_capabilities.browser.engine.business_site_scope import (
    resolve_business_site_scope,
)
from app.enterprise_capabilities.browser.engine.initial_entry_navigation import initial_entry_url
from app.enterprise_capabilities.browser.engine.entry_candidates import extract_candidate_entries


def test_explicit_entry_replaces_an_unrelated_page_for_a_new_run() -> None:
    assert initial_entry_url(
        step=1,
        candidates=[{"url": "https://www.baidu.com", "source": "user_request"}],
        current_url="https://www.himovo.com/",
        resuming=False,
    ) == "https://www.baidu.com"


def test_resolved_site_scope_replaces_the_previous_tasks_page() -> None:
    assert initial_entry_url(
        step=1,
        candidates=[{"url": "https://baidu.com/", "source": "site_scope"}],
        current_url="https://www.himovo.com/",
        resuming=False,
    ) == "https://baidu.com/"


def test_named_site_resolution_without_a_literal_url_still_forces_entry() -> None:
    candidates = extract_candidate_entries(
        "打开百度搜索 MOVO 官网",
        [],
        expected_site="baidu.com",
    )
    assert candidates == [{
        "url": "https://baidu.com/",
        "source": "site_scope",
        "name": "baidu.com",
    }]
    assert initial_entry_url(
        step=1,
        candidates=candidates,
        current_url="https://www.himovo.com/",
        resuming=False,
    ) == "https://baidu.com/"


def test_semantic_target_url_becomes_a_grounded_first_entry() -> None:
    node = SimpleNamespace(
        goal="打开目标网站并读取首页",
        meta={"semantic_config": {"targetUrl": "https://example.com/start"}},
    )
    resolution = resolve_business_site_scope(
        node,
        original_request="读取目标网站首页",
        visible_sites=[],
    )
    candidates = extract_candidate_entries(
        "读取目标网站首页",
        [],
        expected_site=resolution.site_id,
        target_url=node.meta["semantic_config"]["targetUrl"],
    )

    assert resolution.site_id == "example.com"
    assert resolution.source == "planner"
    assert candidates == [{
        "url": "https://example.com/start",
        "source": "target_url",
        "name": "",
    }]
    assert initial_entry_url(
        step=1,
        candidates=candidates,
        current_url="about:blank",
        resuming=False,
    ) == "https://example.com/start"


def test_explicit_target_url_wins_over_urls_mentioned_in_the_objective() -> None:
    candidates = extract_candidate_entries(
        "参考 https://assets.example.net/input.pdf 后进入目标系统",
        [],
        expected_site="portal.example.com",
        target_url="https://portal.example.com/tasks/42",
    )

    assert candidates == [{
        "url": "https://portal.example.com/tasks/42",
        "source": "target_url",
        "name": "",
    }]


def test_initial_entry_preserves_same_page_and_resumed_human_progress() -> None:
    candidate = [{"url": "https://www.baidu.com/", "source": "user_request"}]
    assert initial_entry_url(
        step=1, candidates=candidate, current_url="https://baidu.com", resuming=False,
    ) is None
    assert initial_entry_url(
        step=1, candidates=candidate, current_url="https://example.com/after-login", resuming=True,
    ) is None


def test_profile_entry_does_not_override_cross_node_browser_state() -> None:
    assert initial_entry_url(
        step=1,
        candidates=[{"url": "https://portal.example.com", "source": "site_profile"}],
        current_url="https://portal.example.com/workspace/1",
        resuming=False,
    ) is None
