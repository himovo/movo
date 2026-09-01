from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from .runner.assertions import ScenarioFailure
from .runner.fixtures import FixtureToolExecutor
from .runner.loader import load_scenario
from .runner.runner import CallableStreamAdapter, ScenarioRunner


CASE = Path(__file__).parent / "cases" / "store_audit_contract.yaml"


async def _passing_stream(_case):
    events = [
        {
            "type": "runtime_status",
            "content": {
                "task_ir": {
                    "steps": [
                        {"capability_id": "external.invoke_tool"},
                        {"capability_id": "control.map_each"},
                        {"capability_id": "control.branch"},
                        {"capability_id": "generation.compose_report"},
                    ]
                }
            },
        },
        {"type": "tool_call", "content": {"name": "get_store_audit_tasks", "arguments": {}}},
        {"type": "tool_call", "content": {"name": "get_store_audit_task_detail", "arguments": {"task_id": "1"}}},
        {"type": "tool_call", "content": {"name": "get_store_audit_task_detail", "arguments": {"task_id": "2"}}},
        {"type": "answer", "content": "上海浦东店存在 critical 风险，已生成整改报告。"},
        {"type": "activity", "content": {"kind": "complete", "message": "完成"}},
    ]
    for event in events:
        yield json.dumps(event, ensure_ascii=False) + "\n"


def test_contract_scenario_passes() -> None:
    case = load_scenario(CASE)
    result = asyncio.run(ScenarioRunner(CallableStreamAdapter(_passing_stream)).run(case))
    assert result.terminal_status == "completed"
    assert len(result.tool_calls) == 3


def test_contract_scenario_reports_actionable_diff() -> None:
    async def broken_stream(_case):
        yield json.dumps({"type": "error", "content": "planner failed"})

    case = load_scenario(CASE)
    with pytest.raises(ScenarioFailure) as exc_info:
        asyncio.run(ScenarioRunner(CallableStreamAdapter(broken_stream)).run(case))

    message = str(exc_info.value)
    assert "expected 'completed', got 'failed'" in message
    assert "missing capabilities" in message
    assert "get_store_audit_tasks" in message


def test_fixture_tool_executor_records_calls_and_isolates_results() -> None:
    async def exercise():
        executor = FixtureToolExecutor({"lookup": {"data": [1, 2]}})
        first = await executor.execute("lookup", {"id": "A"})
        first["data"].append(3)
        second = await executor.execute("lookup", {"id": "B"})
        return executor, second

    executor, second = asyncio.run(exercise())

    assert second == {"data": [1, 2]}
    assert executor.calls == [
        {"name": "lookup", "arguments": {"id": "A"}},
        {"name": "lookup", "arguments": {"id": "B"}},
    ]
