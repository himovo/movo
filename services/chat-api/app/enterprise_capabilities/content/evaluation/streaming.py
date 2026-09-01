from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

from app.enterprise_capabilities.content.evaluation.contracts import Standard
from app.enterprise_capabilities.content.evaluation.pipeline import DynamicEvaluationPipeline


@dataclass(frozen=True)
class EvaluationStreamItem:
    kind: str
    payload: Any
    stage: str = ""


async def stream_evaluation(
    pipeline: DynamicEvaluationPipeline,
    *,
    user_request: str,
    content: str,
    skill_context: Optional[Dict[str, Any]] = None,
    standards: Optional[List[Standard]] = None,
) -> AsyncIterator[EvaluationStreamItem]:
    """Forward existing evaluation-turn commentary as soon as each turn ends."""

    queue: asyncio.Queue[EvaluationStreamItem] = asyncio.Queue()

    async def on_commentary(value: Any, stage: str) -> None:
        await queue.put(EvaluationStreamItem("commentary", value, stage))

    async def run() -> None:
        try:
            result = await pipeline.evaluate(
                user_request=user_request,
                content=content,
                skill_context=skill_context,
                standards=standards,
                commentary_callback=on_commentary,
            )
            await queue.put(EvaluationStreamItem("result", result))
        except Exception as exc:
            await queue.put(EvaluationStreamItem("error", exc))

    task = asyncio.create_task(run())
    try:
        while True:
            item = await queue.get()
            if item.kind == "error":
                raise item.payload
            yield item
            if item.kind == "result":
                break
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
