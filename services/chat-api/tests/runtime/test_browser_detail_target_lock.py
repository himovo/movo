from __future__ import annotations

from app.enterprise_capabilities.browser.engine.contexts.detail_progress import (
    DetailTargetFingerprint,
    capture_detail_target,
    same_detail_resource,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision
from app.enterprise_capabilities.browser.engine.contexts.detail_target_lock import DetailTargetLock
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _target(url: str, label: str) -> DetailTargetFingerprint:
    return DetailTargetFingerprint(
        source_url="https://example.test/search",
        target_url=url,
        labels=(label,),
    )


def _results(ref: str = "e7") -> Observation:
    return Observation(
        url="https://example.test/search",
        title="Results",
        page_text="Target post",
        elements=[{
            "ref": ref,
            "role": "link",
            "name": "Target post",
            "href": "https://example.test/post/7",
        }],
    )


def test_detail_lock_observes_then_retries_the_same_remapped_target():
    lock = DetailTargetLock()
    assert lock.prepare(_target("https://example.test/post/7", "Target post")) is True

    lock.finish_action(detail_confirmed=False)
    assert lock.suggest(_results()).tool == "browser_observe"

    lock.finish_observation(detail_confirmed=False)
    retried = lock.suggest(_results(ref="e19"))

    assert retried is not None
    assert retried.tool == "browser_click"
    assert retried.args["ref"] == "e19"


def test_detail_lock_blocks_switching_objects_until_retry_is_exhausted():
    lock = DetailTargetLock()
    first = _target("https://example.test/post/7", "Target post")
    other = _target("https://example.test/post/8", "Other post")
    assert lock.prepare(first) is True
    lock.finish_action(detail_confirmed=False)

    assert lock.prepare(other) is False

    lock.finish_observation(detail_confirmed=False)
    assert lock.prepare(first) is True
    lock.finish_action(detail_confirmed=False)
    lock.finish_observation(detail_confirmed=False)

    assert lock.prepare(other) is True
    assert lock.target == other


def test_exhausted_detail_target_cannot_be_rearmed_by_the_planner():
    lock = DetailTargetLock(max_attempts=1)
    target = _target("https://example.test/post/7", "Target post")
    assert lock.prepare(target) is True

    lock.finish_action(detail_confirmed=False)
    lock.finish_observation(detail_confirmed=False)

    assert lock.prepare(target) is False


def test_detail_lock_clears_after_verified_detail():
    lock = DetailTargetLock()
    assert lock.prepare(_target("https://example.test/post/7", "Target post")) is True

    lock.finish_action(detail_confirmed=True)

    assert lock.target is None
    assert lock.attempts == 0


def test_detail_lock_can_retain_then_exclude_a_verified_dead_end():
    lock = DetailTargetLock()
    target = _target("https://example.test/post/7", "Target post")
    assert lock.prepare(target) is True

    lock.finish_action(
        detail_confirmed=True,
        detail_url="https://example.test/post/7",
        retain_confirmed=True,
    )
    assert lock.target == target
    assert lock.detail_confirmed is True

    excluded = lock.exclude_current(reason="required editor unavailable")

    assert excluded == target
    assert lock.target is None
    assert lock.prepare(target) is False
    assert "required editor unavailable" in str(lock.as_dict()["excluded_targets"])


def test_detail_lock_does_not_conflate_equal_action_labels_in_distinct_rows():
    lock = DetailTargetLock()
    first = DetailTargetFingerprint(
        source_url="https://example.test/results",
        target_url="",
        labels=("Open",),
        scope_id="#results > article:nth-child(1) > button",
    )
    second = DetailTargetFingerprint(
        source_url="https://example.test/results",
        target_url="",
        labels=("Open",),
        scope_id="#results > article:nth-child(2) > button",
    )

    assert lock.prepare(first) is True
    lock.finish_action(detail_confirmed=False)

    assert lock.prepare(second) is False


def test_adjacent_row_action_inherits_the_business_resource_link():
    observation = Observation(
        url="https://example.test/results",
        title="Results",
        elements=[
            {
                "ref": "title-1",
                "role": "link",
                "name": "First item",
                "href": "https://example.test/item/1",
                "selector": "#results > article:nth-child(1) > header > a",
            },
            {
                "ref": "open-1",
                "role": "button",
                "name": "Open",
                "href": "",
                "selector": "#results > article:nth-child(1) > footer > button",
            },
            {
                "ref": "title-2",
                "role": "link",
                "name": "Second item",
                "href": "https://example.test/item/2",
                "selector": "#results > article:nth-child(2) > header > a",
            },
        ],
    )

    target = capture_detail_target(
        Decision(tool="browser_click", args={"ref": "open-1"}),
        observation,
    )

    assert target is not None
    assert target.target_url == "https://example.test/item/1"


def test_excluding_a_resource_blocks_other_controls_for_that_row_only():
    observation = Observation(
        url="https://example.test/results",
        title="Results",
        elements=[
            {
                "ref": "title-1",
                "role": "link",
                "name": "First item",
                "href": "https://example.test/item/1",
                "selector": "#results > article:nth-child(1) > header > a",
            },
            {
                "ref": "open-1",
                "role": "button",
                "name": "Open",
                "selector": "#results > article:nth-child(1) > footer > button",
            },
            {
                "ref": "title-2",
                "role": "link",
                "name": "Second item",
                "href": "https://example.test/item/2",
                "selector": "#results > article:nth-child(2) > header > a",
            },
            {
                "ref": "open-2",
                "role": "button",
                "name": "Open",
                "selector": "#results > article:nth-child(2) > footer > button",
            },
        ],
    )
    first_title = capture_detail_target(
        Decision(tool="browser_click", args={"ref": "title-1"}),
        observation,
    )
    first_action = capture_detail_target(
        Decision(tool="browser_click", args={"ref": "open-1"}),
        observation,
    )
    second_action = capture_detail_target(
        Decision(tool="browser_click", args={"ref": "open-2"}),
        observation,
    )
    assert first_title is not None
    assert first_action is not None
    assert second_action is not None

    lock = DetailTargetLock()
    assert lock.prepare(first_title) is True
    lock.finish_action(
        detail_confirmed=True,
        detail_url=first_title.target_url,
        retain_confirmed=True,
    )
    lock.exclude_current(reason="candidate cannot satisfy the pending action")

    assert lock.prepare(first_action) is False
    assert lock.prepare(second_action) is True


def test_entry_navigation_without_an_observed_resource_is_not_a_detail_target():
    blank = Observation(
        url="about:blank",
        title="",
        elements=[],
    )

    target = capture_detail_target(
        Decision(
            tool="browser_navigate",
            args={"url": "https://example.test/invited"},
        ),
        blank,
    )

    assert target is None


def test_direct_navigation_to_an_observed_resource_is_a_detail_target():
    results = Observation(
        url="https://example.test/invited",
        title="Candidates",
        elements=[{
            "ref": "question-1",
            "role": "link",
            "name": "First question",
            "href": "https://example.test/question/1",
        }],
    )

    target = capture_detail_target(
        Decision(
            tool="browser_navigate",
            args={"url": "https://example.test/question/1#write"},
        ),
        results,
    )

    assert target is not None
    assert target.source_url == "https://example.test/invited"
    assert target.target_url == "https://example.test/question/1"
    assert target.labels == ("First question",)


def test_coordinate_detail_target_uses_observed_element_centres():
    observation = Observation(
        url="https://example.test/search?q=ai",
        title="Results",
        elements=[{
            "ref": "e7",
            "role": "link",
            "name": "Target post",
            "href": "https://example.test/post/7",
            "x": 640,
            "y": 700,
            "width": 160,
            "height": 100,
            "visible": True,
        }],
    )

    target = capture_detail_target(
        Decision(tool="browser_click_at", args={"x": 680, "y": 720}),
        observation,
    )

    assert target is not None
    assert target.target_url == "https://example.test/post/7"


def test_plain_filter_button_is_not_captured_as_a_detail_resource():
    observation = Observation(
        url="https://example.test/search?q=ai",
        title="Results",
        elements=[{
            "ref": "filter",
            "role": "button",
            "name": "筛选",
            "selector": "#toolbar > div:nth-child(2)",
            "scopeId": "0:#global",
            "scopeLockable": False,
        }],
    )

    target = capture_detail_target(
        Decision(tool="browser_click", args={"ref": "filter"}),
        observation,
    )

    assert target is None


def test_content_identity_relocates_a_virtualized_resource_after_ref_churn():
    lock = DetailTargetLock()
    target = DetailTargetFingerprint(
        source_url="https://example.test/search",
        target_url="https://example.test/post/expected",
        labels=("Expected",),
        content_context_id="attribute:data-note-id:expected-record",
    )
    assert lock.prepare(target) is True
    lock.finish_action(detail_confirmed=False)
    lock.finish_observation(detail_confirmed=False)

    observation = Observation(
        url=target.source_url,
        title="Results",
        elements=[
            {
                "ref": "old-position",
                "role": "link",
                "name": "Other",
                "href": "https://example.test/post/other",
                "contentContextId": "attribute:data-note-id:other-record",
            },
            {
                "ref": "fresh-target",
                "role": "link",
                "name": "Expected",
                "href": target.target_url,
                "contentContextId": target.content_context_id,
            },
        ],
    )

    retry = lock.suggest(observation)

    assert retry is not None
    assert retry.args["ref"] == "fresh-target"


def test_detail_resource_comparison_rejects_prefix_collision():
    assert same_detail_resource(
        "https://example.test/post/1?source=search",
        "https://example.test/post/10?source=search",
    ) is False
    assert same_detail_resource(
        "https://example.test/post/1?source=search&item=42",
        "https://example.test/post/1?source=feed&item=42",
    ) is True
    assert same_detail_resource(
        "https://example.test/detail?id=1",
        "https://example.test/detail?id=2",
    ) is False
    assert same_detail_resource(
        "https://example.test/detail?id=1",
        "https://example.test/detail?item=1",
    ) is False
