from __future__ import annotations

import asyncio

import pytest

from app.enterprise_capabilities.tools.execution_timeout import (
    ExecutionActivity,
    ExecutionDeadlineExceeded,
    ExecutionTimeoutPolicy,
    execute_with_timeout,
)


def test_activity_extends_inactivity_deadline() -> None:
    async def run() -> str:
        activity = ExecutionActivity()

        async def work() -> str:
            for _ in range(3):
                await asyncio.sleep(0.04)
                activity.touch()
            return "complete"

        return await execute_with_timeout(
            work(),
            policy=ExecutionTimeoutPolicy(total_seconds=0.5, inactivity_seconds=0.07),
            activity=activity,
        )

    assert asyncio.run(run()) == "complete"


def test_activity_aware_execution_stops_after_inactivity() -> None:
    async def run() -> None:
        await execute_with_timeout(
            asyncio.sleep(1),
            policy=ExecutionTimeoutPolicy(total_seconds=0.5, inactivity_seconds=0.05),
            activity=ExecutionActivity(),
        )

    with pytest.raises(ExecutionDeadlineExceeded, match="stopped reporting progress"):
        asyncio.run(run())


def test_activity_does_not_bypass_total_duration_cap() -> None:
    async def run() -> None:
        activity = ExecutionActivity()

        async def work() -> None:
            while True:
                await asyncio.sleep(0.02)
                activity.touch()

        await execute_with_timeout(
            work(),
            policy=ExecutionTimeoutPolicy(total_seconds=0.09, inactivity_seconds=0.06),
            activity=activity,
        )

    with pytest.raises(ExecutionDeadlineExceeded, match="maximum duration"):
        asyncio.run(run())


def test_fixed_timeout_keeps_existing_tool_behavior() -> None:
    async def run() -> None:
        await execute_with_timeout(
            asyncio.sleep(1),
            policy=ExecutionTimeoutPolicy(total_seconds=0.05),
        )

    with pytest.raises(ExecutionDeadlineExceeded, match="tool execution timed out"):
        asyncio.run(run())
