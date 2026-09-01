from __future__ import annotations

from collections import Counter
from typing import Any

from .collector import ScenarioResult
from .loader import ScenarioCase


class ScenarioFailure(AssertionError):
    pass


def _capabilities(result: ScenarioResult) -> set[str]:
    steps = result.task_ir.get("steps") if isinstance(result.task_ir, dict) else []
    found = {
        str(step.get("capability_id") or "").strip()
        for step in list(steps or [])
        if isinstance(step, dict)
    }
    contract_caps = result.task_contract.get("execution_capabilities", [])
    found.update(str(value).strip() for value in list(contract_caps or []))
    return {value for value in found if value}


def _tool_name(call: dict[str, Any]) -> str:
    return str(call.get("name") or call.get("tool_name") or call.get("detail") or "").strip()


def assert_scenario(case: ScenarioCase, result: ScenarioResult) -> None:
    errors: list[str] = []
    expect = case.expect

    expected_status = str(expect.get("status") or "").strip()
    if expected_status and result.terminal_status != expected_status:
        errors.append(f"status: expected {expected_status!r}, got {result.terminal_status!r}")

    graph_expect = expect.get("graph") if isinstance(expect.get("graph"), dict) else {}
    required_caps = set(graph_expect.get("required_capabilities") or [])
    missing_caps = sorted(required_caps - _capabilities(result))
    if missing_caps:
        errors.append(f"missing capabilities: {missing_caps}")

    counts = Counter(_tool_name(call) for call in result.tool_calls)
    for tool_expect in list(expect.get("tools") or []):
        if not isinstance(tool_expect, dict):
            continue
        name = str(tool_expect.get("name") or "").strip()
        actual = counts[name]
        if "count" in tool_expect and actual != int(tool_expect["count"]):
            errors.append(f"tool {name!r}: expected count {tool_expect['count']}, got {actual}")
        if "min_count" in tool_expect and actual < int(tool_expect["min_count"]):
            errors.append(f"tool {name!r}: expected at least {tool_expect['min_count']}, got {actual}")

    output_expect = expect.get("output") if isinstance(expect.get("output"), dict) else {}
    for fact in list(output_expect.get("required_facts") or []):
        if str(fact) not in result.final_text:
            errors.append(f"output missing required fact: {fact!r}")

    forbidden = expect.get("forbidden") if isinstance(expect.get("forbidden"), dict) else {}
    forbidden_events = set(forbidden.get("events") or [])
    present_forbidden = sorted(forbidden_events.intersection(result.event_types))
    if present_forbidden:
        errors.append(f"forbidden events present: {present_forbidden}")

    if result.malformed_lines:
        errors.append(f"malformed stream lines: {result.malformed_lines[:3]}")

    if errors:
        detail = "\n- ".join(errors)
        raise ScenarioFailure(f"scenario {case.scenario_id!r} failed:\n- {detail}")
