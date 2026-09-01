import asyncio

import pytest

from app.enterprise_capabilities.browser.engine.execution_budget import (
    BrowserExecutionBudget,
    BrowserExecutionBudgetExpired,
    budget_partial_artifacts,
    interrupted_effect_requires_handoff,
)


def test_execution_budget_interrupts_before_outer_gateway_timeout() -> None:
    async def run() -> None:
        budget = BrowserExecutionBudget.start(0.01)
        with pytest.raises(BrowserExecutionBudgetExpired):
            await budget.wait_for(asyncio.sleep(2))

    asyncio.run(run())


def test_budget_result_preserves_evidence_and_requests_continuation() -> None:
    artifacts = budget_partial_artifacts(
        objective="read records",
        summary="partial",
        data={"target_url": "https://example.test/item/1", "observed_content": {"text": "fact"}},
        steps=7,
    )
    assert artifacts["browser_receipt"]["status"] == "partial_success"
    assert artifacts["browser_receipt"]["continuation_required"] is True
    assert artifacts["browser_result"]["data"]["observed_content"]["text"] == "fact"
    assert artifacts["browser_result"]["task_outcome"]["reason"] == "execution_budget_reached"


def test_interrupted_write_effect_requires_human_verification_but_read_does_not() -> None:
    assert interrupted_effect_requires_handoff(
        capability_id="browser.submit",
        tool="browser_press",
        final_commit_control=False,
    ) is True
    assert interrupted_effect_requires_handoff(
        capability_id="browser.read",
        tool="browser_press",
        final_commit_control=True,
    ) is False
    assert interrupted_effect_requires_handoff(
        capability_id="browser.submit",
        tool="browser_fill",
        final_commit_control=False,
    ) is False
