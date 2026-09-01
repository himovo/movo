"""Reconnect the existing ASKAI content evaluation closure to DSH writing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.enterprise_capabilities.content.evaluation import issues_as_writer_feedback
from app.enterprise_capabilities.content.evaluation.contracts import EvaluationResult
from app.enterprise_capabilities.content.evaluation.pipeline import get_default_pipeline


ProgressSink = Callable[[dict[str, Any]], Awaitable[None]]
Regenerate = Callable[[str], Awaitable[str]]


@dataclass
class ContentQualityResult:
    markdown: str
    verdict: str = "not_evaluated"
    evaluation_status: str = "not_evaluated"
    standards_count: int = 0
    issues_count: int = 0
    repair_applied: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class ExistingContentQualityClosure:
    """Orchestrate the existing evaluator; it owns no quality rules."""

    def __init__(self, pipeline: Any = None) -> None:
        self._pipeline = pipeline

    async def close(
        self,
        *,
        user_request: str,
        markdown: str,
        writer_path: str,
        skill_context: dict[str, Any],
        regenerate: Regenerate,
        progress_sink: ProgressSink,
        language: str,
    ) -> ContentQualityResult:
        if writer_path != "single_shot" or not str(markdown or "").strip():
            return ContentQualityResult(markdown=markdown)

        pipeline = self._pipeline or get_default_pipeline()
        await self._stage(progress_sink, language, "review_start")
        initial = await pipeline.evaluate(
            user_request=user_request,
            content=markdown,
            skill_context=skill_context,
            commentary_callback=self._commentary_sink(progress_sink),
        )
        status = str((initial.metadata or {}).get("evaluation_status") or "completed")
        if status == "inconclusive":
            await self._stage(progress_sink, language, "review_inconclusive")
            return self._result(markdown, initial, evaluation_status=status)
        if initial.verdict == "pass":
            await self._stage(progress_sink, language, "review_pass")
            return self._result(markdown, initial, evaluation_status=status)

        feedback = issues_as_writer_feedback(initial.issues or [])
        if not feedback:
            await self._stage(progress_sink, language, "review_pass")
            return self._result(markdown, initial, evaluation_status=status)

        await self._stage(progress_sink, language, "repair_start")
        repaired = await regenerate(feedback)
        await self._stage(progress_sink, language, "repair_complete")
        # The closure intentionally permits one repair only. A synchronous
        # second evaluation cannot trigger another repair, so it adds latency
        # and model cost without changing the delivered content.
        result = self._result(repaired, initial, evaluation_status="repaired")
        result.verdict = "repaired_unverified"
        result.repair_applied = True
        result.metadata["initial_verdict"] = initial.verdict
        result.metadata["initial_issues_count"] = len(initial.issues or [])
        result.metadata["post_repair_review_skipped"] = True
        return result

    @staticmethod
    def _commentary_sink(progress_sink: ProgressSink):
        async def publish(payload: Any, stage: str) -> None:
            content = dict(payload or {}) if isinstance(payload, dict) else {"text": str(payload or "")}
            if not str(content.get("text") or "").strip():
                return
            content.setdefault("kind", f"quality_{stage}")
            await progress_sink({"type": "commentary", "content": content})

        return publish

    @staticmethod
    def _result(
        markdown: str,
        evaluation: EvaluationResult,
        *,
        evaluation_status: str,
    ) -> ContentQualityResult:
        return ContentQualityResult(
            markdown=markdown,
            verdict=evaluation.verdict,
            evaluation_status=evaluation_status,
            standards_count=len(evaluation.standards or []),
            issues_count=len(evaluation.issues or []),
            metadata=dict(evaluation.metadata or {}),
        )

    @staticmethod
    async def _stage(progress_sink: ProgressSink, language: str, stage: str) -> None:
        zh = {
            "review_start": "初稿已完成，正在生成质量标准并检查正文",
            "review_pass": "正文质量检查通过",
            "review_inconclusive": "质量检查暂不可用，保留当前成稿",
            "repair_start": "质量检查发现需要修正的问题，正在按原写作要求重写",
            "repair_complete": "修订已完成，正在继续配图与交付处理",
        }
        en = {
            "review_start": "The draft is complete; generating quality standards and reviewing it",
            "review_pass": "The draft passed the quality review",
            "review_inconclusive": "The quality review is unavailable; keeping the current draft",
            "repair_start": "The review found material issues; rewriting with the original requirements",
            "repair_complete": "The revision is complete; continuing with visuals and delivery",
        }
        messages = zh if str(language or "").lower().startswith("zh") else en
        await progress_sink({
            "type": "activity",
            "content": {"kind": "quality", "message": messages[stage]},
        })


__all__ = ["ContentQualityResult", "ExistingContentQualityClosure"]
