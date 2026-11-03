import asyncio

import httpx
import pytest

from app.services.presentation.execution.failures import PresentationStepError, run_generation_step


def test_timeout_retries_only_failed_step_then_returns_result():
    calls = []
    async def operation():
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("")
        return "saved-image"
    assert asyncio.run(run_generation_step(operation, stage="slide_image_generation", page_id="p2")) == "saved-image"
    assert len(calls) == 2


def test_retries_are_bounded_and_empty_exception_is_explained():
    calls = []
    async def operation():
        calls.append(1)
        raise TimeoutError()
    with pytest.raises(PresentationStepError, match="provider_timeout") as captured:
        asyncio.run(run_generation_step(operation, stage="slide_image_generation", page_id="p2"))
    assert len(calls) == 2
    assert captured.value.page_id == "p2"
    assert captured.value.attempts == 2
    assert "TimeoutError" in str(captured.value)


@pytest.mark.parametrize("status,category", [(402, "insufficient_balance"), (401, "provider_authentication"), (400, "generation_error")])
def test_permanent_provider_errors_are_not_retried_or_exposed(status, category):
    calls = []
    async def operation():
        calls.append(1)
        raise RuntimeError(f"image generation failed http_{status}: secret-provider-response")
    with pytest.raises(PresentationStepError) as captured:
        asyncio.run(run_generation_step(operation, stage="slide_image_generation"))
    assert len(calls) == 1
    assert captured.value.category == category
    assert "secret-provider-response" not in str(captured.value)


def test_cancellation_never_retries():
    async def operation():
        raise asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_generation_step(operation, stage="slide_image_generation"))
