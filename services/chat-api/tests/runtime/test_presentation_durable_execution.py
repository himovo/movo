from __future__ import annotations

import asyncio

from app.services.presentation.execution.identity import build_presentation_job_identity
from app.services.presentation.execution.page_executor import BoundedPageExecutor


def test_presentation_identity_survives_action_retry_but_not_new_message() -> None:
    arguments = {
        "request": " 生成   8 页 MOVO 汇报 ",
        "page_count": 8,
        "required_sections": ["挑战", "方案"],
    }
    first = build_presentation_job_identity(
        tenant_id="tenant-a",
        user_id="user-a",
        conversation_id="conversation-a",
        message_id="message-a",
        generation_mode="llm",
        arguments=arguments,
    )
    retried = build_presentation_job_identity(
        tenant_id="tenant-a",
        user_id="user-a",
        conversation_id="conversation-a",
        message_id="message-a",
        generation_mode="llm",
        arguments={**arguments, "request": "生成 8 页 MOVO 汇报"},
    )
    next_message = build_presentation_job_identity(
        tenant_id="tenant-a",
        user_id="user-a",
        conversation_id="conversation-a",
        message_id="message-b",
        generation_mode="llm",
        arguments=arguments,
    )

    assert first.business_key == retried.business_key
    assert first.continuation_token == retried.continuation_token
    assert first.business_key != next_message.business_key


def test_page_executor_resumes_completed_pages_and_bounds_concurrency() -> None:
    async def scenario() -> tuple[list[str], list[str], int]:
        active = 0
        maximum = 0
        generated: list[str] = []
        checkpointed: list[str] = []
        lock = asyncio.Lock()

        async def generate(_: int, page_id: str) -> str:
            nonlocal active, maximum
            async with lock:
                active += 1
                maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            generated.append(page_id)
            async with lock:
                active -= 1
            return f"rendered:{page_id}"

        async def checkpoint(page_id: str, _: str) -> None:
            checkpointed.append(page_id)

        result = await BoundedPageExecutor[str, str](concurrency=3).run(
            items=[f"page_{index:02d}" for index in range(1, 9)],
            item_id=lambda value: value,
            existing={"page_01": "saved:page_01", "page_04": "saved:page_04"},
            generate=generate,
            checkpoint=checkpoint,
            check_cancelled=lambda: None,
        )
        return result, generated, maximum

    result, generated, maximum = asyncio.run(scenario())

    assert result[0] == "saved:page_01"
    assert result[3] == "saved:page_04"
    assert set(generated) == {
        "page_02", "page_03", "page_05", "page_06", "page_07", "page_08"
    }
    assert maximum == 3


def test_page_executor_cancels_sibling_pages_after_failure() -> None:
    async def scenario() -> list[str]:
        cancelled: list[str] = []

        async def generate(_: int, page_id: str) -> str:
            if page_id == "page_02":
                raise RuntimeError("page failed")
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                cancelled.append(page_id)
                raise
            return page_id

        executor = BoundedPageExecutor[str, str](concurrency=3)
        try:
            await executor.run(
                items=["page_01", "page_02", "page_03", "page_04"],
                item_id=lambda value: value,
                existing={},
                generate=generate,
                checkpoint=lambda *_: asyncio.sleep(0),
                check_cancelled=lambda: None,
            )
        except RuntimeError:
            pass
        return cancelled

    cancelled = asyncio.run(scenario())
    assert "page_01" in cancelled or "page_03" in cancelled
