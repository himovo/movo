"""Wall-clock budget below the outer Tool Gateway hard timeout."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Any, Awaitable, Mapping, TypeVar

from app.enterprise_capabilities.browser.engine.result_artifact import build_browser_result


T = TypeVar("T")

_WRITE_CAPABILITIES = frozenset({
    "browser.submit", "browser.modify", "browser.delete",
    "browser.file_transfer", "browser.publish",
})
_OPAQUE_EFFECT_TOOLS = frozenset({
    "browser_upload_file", "browser_paste_image", "browser_execute_workflow",
})


class BrowserExecutionBudgetExpired(TimeoutError):
    pass


@dataclass(frozen=True)
class BrowserBudgetContinuation:
    summary: str
    artifacts: dict[str, Any]


@dataclass(frozen=True)
class BrowserExecutionBudget:
    deadline: float

    @classmethod
    def start(cls, seconds: float) -> "BrowserExecutionBudget":
        return cls(deadline=monotonic() + max(0.01, float(seconds)))

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline - monotonic())

    @property
    def expired(self) -> bool:
        return self.remaining_seconds <= 0

    async def wait_for(self, awaitable: Awaitable[T]) -> T:
        remaining = self.remaining_seconds
        if remaining <= 0:
            if asyncio.iscoroutine(awaitable):
                awaitable.close()
            raise BrowserExecutionBudgetExpired("browser execution soft budget exhausted")
        try:
            return await asyncio.wait_for(awaitable, timeout=remaining)
        except asyncio.TimeoutError as exc:
            raise BrowserExecutionBudgetExpired(
                "browser execution soft budget exhausted"
            ) from exc


def budget_partial_artifacts(
    *,
    objective: str,
    summary: str,
    data: Mapping[str, Any],
    steps: int,
) -> dict[str, Any]:
    task_outcome = {
        "status": "partial_success",
        "reason": "execution_budget_reached",
        "continuation_required": True,
    }
    bounded_data = dict(data)
    bounded_data["continuation"] = task_outcome
    return {
        "browser_receipt": {
            "status": "partial_success",
            "summary": summary,
            "reason": "execution_budget_reached",
            "steps": max(0, int(steps)),
            "continuation_required": True,
        },
        "browser_result": build_browser_result(
            objective=objective,
            summary=summary,
            data=bounded_data,
            status="partial_success",
            task_outcome=task_outcome,
        ),
        **bounded_data,
    }


def interrupted_effect_requires_handoff(
    *,
    capability_id: str,
    tool: str,
    final_commit_control: bool,
) -> bool:
    """Fail closed when a soft timeout may have interrupted a real effect."""
    if str(capability_id or "").strip().lower() not in _WRITE_CAPABILITIES:
        return False
    normalized_tool = str(tool or "")
    return bool(
        final_commit_control
        or normalized_tool in _OPAQUE_EFFECT_TOOLS
        or normalized_tool == "browser_press"
    )


def build_budget_continuation(
    *,
    context: Any,
    observation: Any,
    tracks_context_state: bool,
    lang: str,
    objective: str,
    steps: int,
) -> BrowserBudgetContinuation:
    summary = (
        "浏览器任务达到本次执行预算，已保留当前页面和已观察证据供下一次调用继续。"
        if str(lang).startswith("zh") else
        "The browser mission reached its execution budget; the live page and observed evidence are retained for continuation."
    )
    data = context.result_evidence(observation) if tracks_context_state else {}
    if tracks_context_state:
        summary, data = context.finalize(
            summary,
            data,
            partial=True,
            partial_reason="execution_budget_reached",
        )
    return BrowserBudgetContinuation(
        summary=summary,
        artifacts=budget_partial_artifacts(
            objective=objective,
            summary=summary,
            data=data,
            steps=steps,
        ),
    )


def unknown_effect_verification_question(lang: str) -> str:
    return (
        "浏览器写操作在等待页面结果时达到执行预算，系统无法确认是否已经生效。"
        "请在右侧浏览器核对实际结果后选择已完成或未完成；在确认前系统不会重复执行。"
        if str(lang).startswith("zh") else
        "The browser write reached its execution budget while waiting for the page result. "
        "Verify the live browser outcome and mark it completed or not completed; it will not be replayed before confirmation."
    )


__all__ = [
    "BrowserExecutionBudget",
    "BrowserExecutionBudgetExpired",
    "BrowserBudgetContinuation",
    "budget_partial_artifacts",
    "build_budget_continuation",
    "interrupted_effect_requires_handoff",
    "unknown_effect_verification_question",
]
