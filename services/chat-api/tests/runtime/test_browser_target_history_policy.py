from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation
from app.enterprise_capabilities.browser.engine.alternative_target_recovery import AlternativeTargetRecovery
from app.enterprise_capabilities.browser.engine.target_history_policy import (
    TargetHistoryDirective,
    TargetHistoryState,
)
from app.enterprise_capabilities.browser.engine.target_identity import element_target_aliases
from app.governance.action_receipt import ActionReceipt


RESULTS = "https://example.test/search?q=browser"
FIRST = "https://example.test/posts/one?token=volatile"
SECOND = "https://example.test/posts/two"


class _Store:
    def __init__(self, rows: list[ActionReceipt]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, str]] = []

    async def list_succeeded_for_operation(self, *, actor_id: str, operation_id: str):
        self.calls.append((actor_id, operation_id))
        return list(self.rows)


def _results() -> Observation:
    return Observation(
        url=RESULTS,
        title="Results",
        elements=[
            {"ref": "one", "role": "link", "href": FIRST, "contentContextId": "post:one"},
            {"ref": "two", "role": "link", "href": SECOND, "contentContextId": "post:two"},
        ],
    )


def _planner_decision(policy: str, operation: str) -> Decision:
    return Decision(
        tool="browser_click",
        args={"ref": "one"},
        rationale_source="model",
        commentary={
            "target_history": {
                "policy": policy,
                "operation": operation,
                "reason": "compiled from the task",
            },
        },
    )


def test_exclude_completed_loads_history_and_filters_before_click() -> None:
    async def scenario() -> None:
        aliases = element_target_aliases(_results().elements[0], page_url=RESULTS)
        store = _Store([
            ActionReceipt(
                action_id="a1",
                idempotency_key="i1",
                status="succeeded",
                actor_id="user-1",
                operation_id="comment",
                target_id=aliases[0],
                target_aliases=list(aliases),
            ),
        ])
        state = TargetHistoryState()
        recovery = AlternativeTargetRecovery()
        decision = _planner_decision("exclude_completed", "comment")

        assert state.adopt(decision) is True
        await state.load_completed_targets(store=store, actor_id="user-1", recovery=recovery)

        assert state.blocked_selection_ref(decision, _results(), recovery) == "one"
        assert [item["ref"] for item in recovery.planning_observation(_results()).elements] == ["two"]
        assert store.calls == [("user-1", "comment")]

    asyncio.run(scenario())


def test_allow_completed_does_not_query_or_filter_history() -> None:
    async def scenario() -> None:
        store = _Store([])
        state = TargetHistoryState()
        recovery = AlternativeTargetRecovery()
        decision = _planner_decision("allow_completed", "comment")

        state.adopt(decision)
        count = await state.load_completed_targets(
            store=store, actor_id="user-1", recovery=recovery,
        )

        assert count == 0
        assert store.calls == []
        assert state.blocked_selection_ref(decision, _results(), recovery) == ""

    asyncio.run(scenario())


def test_unspecified_policy_still_retains_operation_for_future_receipts() -> None:
    state = TargetHistoryState()
    decision = _planner_decision("unspecified", "update_ticket")

    assert state.adopt(decision) is True
    assert state.policy == "unspecified"
    assert state.operation == "update_ticket"
    assert state.excludes_completed is False


def test_first_explicit_policy_is_stable_across_later_planner_turns() -> None:
    state = TargetHistoryState()
    state.adopt(_planner_decision("exclude_completed", "comment"))
    state.adopt(_planner_decision("allow_completed", "comment"))

    assert state.policy == "exclude_completed"
    assert state.operation == "comment"


def test_checkpoint_round_trip_keeps_policy_and_loaded_scope() -> None:
    first = TargetHistoryState()
    first.adopt(_planner_decision("exclude_completed", "comment"))
    first._loaded_operations.add("comment")
    restored = TargetHistoryState()

    restored.restore_state(first.export_state())

    assert restored.policy == "exclude_completed"
    assert restored.operation == "comment"
    assert restored._loaded_operations == {"comment"}


def test_explicit_policy_requires_a_semantic_operation() -> None:
    with pytest.raises(ValidationError):
        TargetHistoryDirective(policy="exclude_completed", operation="")


def test_completed_target_source_is_restored_with_its_aliases() -> None:
    async def scenario() -> None:
        aliases = element_target_aliases(_results().elements[0], page_url=RESULTS)
        store = _Store([ActionReceipt(
            action_id="a1",
            idempotency_key="i1",
            status="succeeded",
            actor_id="user-1",
            operation_id="comment",
            target_id=aliases[0],
            target_aliases=list(aliases),
            source_url=RESULTS,
        )])
        state = TargetHistoryState()
        recovery = AlternativeTargetRecovery()
        state.adopt(_planner_decision("exclude_completed", "comment"))

        await state.load_completed_targets(
            store=store,
            actor_id="user-1",
            recovery=recovery,
        )

        assert recovery.source_url_for(aliases[0]) == RESULTS

    asyncio.run(scenario())
