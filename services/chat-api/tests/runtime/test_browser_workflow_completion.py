from __future__ import annotations

from app.enterprise_capabilities.browser.engine.workflow_cache.completion import build_local_completion
from app.enterprise_capabilities.browser.engine.workflow_cache.contracts import CachedCompletionContract
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def test_cached_write_cannot_complete_from_unverified_page_text() -> None:
    decision = build_local_completion(
        CachedCompletionContract(capability_id="browser.submit"),
        Observation(
            url="https://example.test/editor", title="Editor",
            elements=[], page_text="保存为草稿",
        ),
        lang="zh",
    )

    assert decision is None


def test_cached_navigation_can_still_complete_locally() -> None:
    decision = build_local_completion(
        CachedCompletionContract(capability_id="browser.navigate"),
        Observation(url="https://example.test/target", title="Target", elements=[]),
        lang="zh",
    )

    assert decision is not None
    assert decision.tool == "browser_done"
