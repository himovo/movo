from __future__ import annotations

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision,
    Observation,
    StepRecord,
)
from app.enterprise_capabilities.browser.engine.alternative_target_recovery import (
    AlternativeTargetRecovery,
)
from app.enterprise_capabilities.browser.engine.completed_target_recovery import (
    CompletedTargetRecovery,
)


DETAIL = "https://example.test/posts/one?token=volatile"
RESULTS = "https://example.test/search?q=agents"
HOME = "https://example.test/"


def _detail() -> Observation:
    return Observation(url=DETAIL, title="Completed detail", elements=[])


def test_current_completed_page_recovers_to_source_observed_in_this_run() -> None:
    alternatives = AlternativeTargetRecovery()
    alternatives.exclude(DETAIL)
    source = Observation(
        url=RESULTS,
        title="Results",
        elements=[{"ref": "one", "role": "link", "href": DETAIL}],
    )
    history = [StepRecord(
        observation=_detail(),
        decision=Decision("browser_click", {"ref": "one"}),
        decision_observation=source,
        ok=True,
    )]

    decision = CompletedTargetRecovery().recovery_decision(
        observation=_detail(),
        history=history,
        candidate_entries=[{"url": HOME, "source": "target_url"}],
        recovery=alternatives,
    )

    assert decision is not None
    assert decision.args == {"url": RESULTS}
    assert "observed_candidate_list" in decision.rationale


def test_new_run_uses_persisted_source_when_click_history_is_empty() -> None:
    alternatives = AlternativeTargetRecovery()
    alternatives.exclude(DETAIL)
    alternatives.remember_source([DETAIL], RESULTS)

    decision = CompletedTargetRecovery().recovery_decision(
        observation=_detail(),
        history=[],
        candidate_entries=[{"url": HOME, "source": "target_url"}],
        recovery=alternatives,
    )

    assert decision is not None
    assert decision.args == {"url": RESULTS}
    assert "persisted_candidate_source" in decision.rationale


def test_new_run_falls_back_to_grounded_task_entry_without_guessing_site_routes() -> None:
    alternatives = AlternativeTargetRecovery()
    alternatives.exclude(DETAIL)

    decision = CompletedTargetRecovery().recovery_decision(
        observation=_detail(),
        history=[],
        candidate_entries=[{"url": HOME, "source": "target_url"}],
        recovery=alternatives,
    )

    assert decision is not None
    assert decision.args == {"url": HOME}
    assert "task_entry" in decision.rationale


def test_legacy_receipt_without_source_or_task_entry_uses_observed_site_root() -> None:
    alternatives = AlternativeTargetRecovery()
    alternatives.exclude(DETAIL)

    decision = CompletedTargetRecovery().recovery_decision(
        observation=_detail(),
        history=[],
        candidate_entries=[],
        recovery=alternatives,
    )

    assert decision is not None
    assert decision.args == {"url": HOME}
    assert "observed_site_root" in decision.rationale


def test_recovery_never_repeats_the_same_route_on_an_unchanged_page() -> None:
    alternatives = AlternativeTargetRecovery()
    alternatives.exclude(DETAIL)
    state = CompletedTargetRecovery()

    first = state.recovery_decision(
        observation=_detail(),
        history=[],
        candidate_entries=[{"url": HOME, "source": "target_url"}],
        recovery=alternatives,
    )
    second = state.recovery_decision(
        observation=_detail(),
        history=[],
        candidate_entries=[{"url": HOME, "source": "target_url"}],
        recovery=alternatives,
    )

    assert first is not None
    assert second is None


def test_uncompleted_page_is_left_to_normal_planning() -> None:
    assert CompletedTargetRecovery().recovery_decision(
        observation=_detail(),
        history=[],
        candidate_entries=[{"url": HOME, "source": "target_url"}],
        recovery=AlternativeTargetRecovery(),
    ) is None


def test_attempted_routes_survive_checkpoint_restore() -> None:
    first = CompletedTargetRecovery(attempted_routes={HOME})
    restored = CompletedTargetRecovery()

    restored.restore_state(first.export_state())

    assert restored.attempted_routes == {HOME}
