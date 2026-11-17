"""Persistence latency must be bounded and reported without retrying execution."""
import asyncio
import pytest

from app.enterprise_capabilities.tools.observability import ToolControlPlaneTimeout, tool_stage


def test_slow_control_stage_is_cancelled_and_classified():
    async def verify():
        stopped = asyncio.Event()
        attempts = 0
        @tool_stage('receipt_probe', timeout_seconds=.01)
        async def persistence():
            nonlocal attempts
            attempts += 1
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        with pytest.raises(ToolControlPlaneTimeout, match='recorded outcome'):
            await asyncio.wait_for(persistence(), .5)
        assert stopped.is_set()
        assert attempts == 1
    asyncio.run(verify())
