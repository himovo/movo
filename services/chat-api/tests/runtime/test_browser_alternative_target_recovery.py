from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision,
    Observation,
    StepRecord,
)
from app.enterprise_capabilities.browser.engine.alternative_target_recovery import (
    AlternativeTargetRecovery,
)


RESULTS = "https://example.test/search?q=agents"
FIRST = "https://example.test/result/one?token=volatile"
SECOND = "https://example.test/result/two"


def _result_observation() -> Observation:
    return Observation(
        url=RESULTS,
        title="Results",
        elements=[
            {"ref": "one", "role": "link", "href": FIRST, "name": "First"},
            {"ref": "two", "role": "link", "href": SECOND, "name": "Second"},
            {"ref": "search", "role": "searchbox", "editable": True},
        ],
    )


def test_duplicate_opened_from_an_observed_list_returns_to_that_list() -> None:
    recovery = AlternativeTargetRecovery()
    history = [StepRecord(
        observation=Observation(url=FIRST, title="Detail", elements=[]),
        decision=Decision("browser_click", {"ref": "one"}),
        ok=True,
        decision_observation=_result_observation(),
    )]

    decision = recovery.recovery_decision(history=history, target_id=FIRST)

    assert decision is not None
    assert decision.tool == "browser_navigate"
    assert decision.args == {"url": RESULTS}


def test_direct_target_task_does_not_invent_an_alternative_list() -> None:
    recovery = AlternativeTargetRecovery()
    history = [StepRecord(
        observation=Observation(url=FIRST, title="Detail", elements=[]),
        decision=Decision("browser_navigate", {"url": FIRST}),
        ok=True,
    )]

    assert recovery.recovery_decision(history=history, target_id=FIRST) is None
    assert recovery.excluded_target_ids == set()


def test_opaque_content_identity_can_return_to_its_observed_candidate_list() -> None:
    result_observation = _result_observation()
    result_observation.elements[0]["contentContextId"] = "post:one"
    history = [StepRecord(
        observation=Observation(url=FIRST, title="Detail", elements=[]),
        decision=Decision("browser_click", {"ref": "one"}),
        ok=True,
        decision_observation=result_observation,
    )]
    recovery = AlternativeTargetRecovery()
    opaque_target = "opaque:example.test:post:one"

    decision = recovery.recovery_decision(history=history, target_id=opaque_target)

    assert decision is not None
    assert decision.args == {"url": RESULTS}


def test_planning_view_excludes_only_the_completed_durable_target() -> None:
    recovery = AlternativeTargetRecovery()
    recovery.exclude("https://example.test/result/one?token=another")

    planning = recovery.planning_observation(_result_observation())

    assert [item["ref"] for item in planning.elements] == ["two", "search"]
    assert [item["ref"] for item in _result_observation().elements] == ["one", "two", "search"]


def test_exclusions_survive_checkpoint_restore_and_augment_guidance() -> None:
    first = AlternativeTargetRecovery()
    first.exclude(FIRST)
    first.remember_source([FIRST], RESULTS)
    restored = AlternativeTargetRecovery()
    restored.restore_state(first.export_state())

    ledger = restored.augment_state_ledger({"phase": "choose_result"})

    assert restored.excluded_target_ids == {"https://example.test/result/one"}
    assert restored.source_url_for(FIRST) == RESULTS
    assert ledger is not None
    assert ledger["phase"] == "choose_result"
    assert ledger["action_constraints"]
    assert ledger["notes"][0]["excluded_completed_targets"]


def test_invalid_or_same_target_sources_are_not_remembered() -> None:
    recovery = AlternativeTargetRecovery()

    recovery.remember_source([FIRST], "javascript:alert(1)")
    recovery.remember_source([FIRST], FIRST)

    assert recovery.source_url_for(FIRST) == ""
