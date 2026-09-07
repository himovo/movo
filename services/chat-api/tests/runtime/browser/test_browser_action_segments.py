from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation
from app.enterprise_capabilities.browser.engine.agent_loop.structured_output import (
    BrowserPlannerOutput,
    PlannedAction,
    decision_from_output,
)
from app.enterprise_capabilities.browser.engine.recovery_router import (
    INTERNAL_FAILURE,
    recovery_source_for_browser_fail,
)


def test_scroll_then_observe_executes_scroll_as_one_turn() -> None:
    decision = decision_from_output(
        _output(
            ("browser_scroll", {"direction": "down"}),
            ("browser_observe", {}),
        ),
        _observation(),
    )

    assert decision.tool == "browser_scroll"
    assert decision.args == {"direction": "down"}
    assert "trailing_observation_deferred" in decision.rationale


def test_search_segment_discards_redundant_trailing_observe() -> None:
    decision = decision_from_output(
        _output(
            ("browser_fill", {"ref": "search", "value": "MOVO"}),
            ("browser_press", {"ref": "search", "key": "Enter"}),
            ("browser_observe", {}),
        ),
        _observation(),
    )

    assert decision.tool == "browser_execute_plan"
    assert [item["tool"] for item in decision.args["actions"]] == [
        "browser_fill",
        "browser_press",
    ]


def test_observe_before_other_actions_starts_a_fresh_turn() -> None:
    decision = decision_from_output(
        _output(
            ("browser_observe", {}),
            ("browser_scroll", {"direction": "down"}),
        ),
        _observation(),
    )

    assert decision.tool == "browser_observe"
    assert decision.args == {}


def test_two_transitions_are_serialized_instead_of_requesting_human_help() -> None:
    decision = decision_from_output(
        _output(
            ("browser_scroll", {"direction": "down"}),
            ("browser_click", {"ref": "result"}),
        ),
        _observation(),
    )

    assert decision.tool == "browser_scroll"
    assert "multiple_transitions" in decision.rationale


def test_unrecoverable_segment_is_an_internal_planner_failure() -> None:
    decision = decision_from_output(
        _output(
            ("browser_fill", {"ref": "result", "value": "unsafe"}),
            ("browser_press", {"ref": "result", "key": "Enter"}),
        ),
        _observation(),
    )

    assert decision.tool == "browser_fail"
    assert decision.args["error_code"] == "planner_action_segment_invalid"
    assert recovery_source_for_browser_fail(decision.args) == INTERNAL_FAILURE


def test_empty_action_segment_is_an_internal_planner_failure() -> None:
    decision = decision_from_output(
        BrowserPlannerOutput(kind="actions", actions=[]),
        _observation(),
    )

    assert decision.tool == "browser_fail"
    assert decision.args["error_code"] == "planner_action_segment_empty"
    assert recovery_source_for_browser_fail(decision.args) == INTERNAL_FAILURE


def test_model_declared_failure_does_not_turn_into_fake_page_assistance() -> None:
    decision = decision_from_output(
        BrowserPlannerOutput(kind="fail", reason="cannot satisfy contract"),
        _observation(),
    )

    assert decision.tool == "browser_fail"
    assert decision.args["error_code"] == "planner_declared_failure"
    assert recovery_source_for_browser_fail(decision.args) == INTERNAL_FAILURE


def _output(*actions: tuple[str, dict]) -> BrowserPlannerOutput:
    return BrowserPlannerOutput(
        kind="actions",
        summary="继续处理页面",
        actions=[PlannedAction(tool=tool, args=args) for tool, args in actions],
    )


def _observation() -> Observation:
    return Observation(
        url="https://example.test/search",
        title="Search",
        revision="tab:ax:1",
        fresh=True,
        elements=[
            {
                "ref": "search",
                "role": "searchbox",
                "name": "搜索",
                "editable": True,
                "visible": True,
                "disabled": False,
            },
            {
                "ref": "result",
                "role": "link",
                "name": "MOVO",
                "editable": False,
                "visible": True,
                "disabled": False,
            },
        ],
    )
