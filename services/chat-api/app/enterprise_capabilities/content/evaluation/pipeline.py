"""Public entry point. Generates standards from a request and finds issues
in a piece of content. **Does not repair**.

Repair is the writer engine's job — it has the full original context
(publish channel, profile preset, user skills, compose policy, formatting
rules, tone, etc.) that an isolated repair LLM does not. The caller takes
the issue list returned by this pipeline and feeds it back to the writer
engine as additional input ("avoid these problems"), and the writer
regenerates with full context preserved.

Usage:

    pipeline = DynamicEvaluationPipeline()
    result = await pipeline.evaluate(
        user_request="...",
        content="...",
    )
    if result.verdict != "pass":
        # hand result.issues back to writer engine for regeneration
        ...
"""
from __future__ import annotations
from app.infrastructure.observability.config import log_print

from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.enterprise_capabilities.content.evaluation.contracts import (
    EvaluationResult,
    Standard,
    derive_verdict,
)
from app.enterprise_capabilities.content.evaluation.issue_finder import IssueFinder
from app.enterprise_capabilities.content.evaluation.retry_policy import (
    EvaluationRetryPolicy,
    evaluation_deadline,
    run_evaluation_stage,
)
from app.enterprise_capabilities.content.evaluation.standards_generator import StandardsGenerator


class DynamicEvaluationPipeline:
    """Evaluation only: standards + issue finding. No repair.

    Evaluation failures remain non-blocking, but are explicitly marked as
    inconclusive.  A timeout is not evidence that the content passed.
    """

    def __init__(self) -> None:
        self._standards = StandardsGenerator()
        self._issues = IssueFinder()
        self._retry_policy = EvaluationRetryPolicy()

    async def evaluate(
        self,
        *,
        user_request: str,
        content: str,
        skill_context: Optional[Dict[str, Any]] = None,
        standards: Optional[List[Standard]] = None,
        commentary_callback: Optional[Callable[[Any, str], Awaitable[None]]] = None,
    ) -> EvaluationResult:
        """Run standards-generation (if not given) + issue-finding.

        Pass `standards` explicitly when reusing the same standards across
        multiple sections of a long document — avoids regenerating them on
        every call.
        """
        result = EvaluationResult()
        policy = self._resolved_retry_policy()
        deadline = evaluation_deadline(policy)

        if standards is None:
            async def standards_sink(payload: Dict[str, str]) -> None:
                if commentary_callback is not None:
                    await commentary_callback(payload, "standards")

            standards_run = await run_evaluation_stage(
                lambda: self._standards.generate_outcome(
                    user_request=user_request,
                    skill_context=skill_context,
                    commentary_sink=standards_sink if commentary_callback is not None else None,
                ),
                attempt_timeouts=policy.standards_timeouts,
                deadline=deadline,
            )
            standards_outcome = standards_run.outcome
            result.metadata["standards_attempts"] = standards_run.attempts
            if not standards_outcome.completed:
                log_print(
                    "[content_evaluation] standards stage unavailable: "
                    f"{standards_outcome.error_type}: {standards_outcome.error}",
                    flush=True,
                )
                result.verdict = "pass"
                self._mark_inconclusive(
                    result,
                    stage="standards",
                    error_type=standards_outcome.error_type,
                    error=standards_outcome.error,
                )
                return result
            result.metadata["standards_commentary"] = standards_outcome.commentary
            standards = list(standards_outcome.items)
        if skill_context:
            result.metadata["skill_context_used"] = True
            result.metadata["skill_context_keys"] = sorted(list(skill_context.keys()))
        result.standards = standards

        if not standards:
            result.verdict = "pass"
            self._mark_inconclusive(result, stage="standards", error_type="EmptyStandards")
            return result
        if not (content or "").strip():
            result.verdict = "pass"
            result.metadata["evaluation_status"] = "completed"
            result.metadata["short_circuit"] = "empty_content"
            return result

        async def issues_sink(payload: Dict[str, str]) -> None:
            if commentary_callback is not None:
                await commentary_callback(payload, "issues")

        issues_run = await run_evaluation_stage(
            lambda: self._issues.find_outcome(
                content=content,
                standards=standards,
                commentary_sink=issues_sink if commentary_callback is not None else None,
            ),
            attempt_timeouts=policy.issues_timeouts,
            deadline=deadline,
        )
        issues_outcome = issues_run.outcome
        result.metadata["issues_attempts"] = issues_run.attempts
        if not issues_outcome.completed:
            log_print(
                "[content_evaluation] issues stage unavailable: "
                f"{issues_outcome.error_type}: {issues_outcome.error}",
                flush=True,
            )
            result.verdict = "pass"
            self._mark_inconclusive(
                result,
                stage="issues",
                error_type=issues_outcome.error_type,
                error=issues_outcome.error,
            )
            return result
        result.metadata["issues_commentary"] = issues_outcome.commentary
        result.issues = list(issues_outcome.items)
        result.verdict = derive_verdict(result.issues)
        result.metadata["evaluation_status"] = "completed"
        return result

    def _resolved_retry_policy(self) -> EvaluationRetryPolicy:
        policy = getattr(self, "_retry_policy", None)
        if isinstance(policy, EvaluationRetryPolicy):
            return policy
        # Compatibility for tests or integrations that constructed the old
        # pipeline shape directly and supplied one stage timeout.
        legacy_timeout = max(0.1, float(getattr(self, "_stage_timeout_seconds", 60.0)))
        return EvaluationRetryPolicy(
            standards_timeouts=(legacy_timeout,),
            issues_timeouts=(legacy_timeout,),
            total_timeout_seconds=legacy_timeout * 2,
        )

    @staticmethod
    def _mark_inconclusive(
        result: EvaluationResult,
        *,
        stage: str,
        exc: BaseException | None = None,
        error_type: str = "",
        error: str = "",
    ) -> None:
        result.verdict = "pass"  # preserve the non-blocking delivery policy
        result.metadata.update(
            {
                "evaluation_status": "inconclusive",
                "error_stage": stage,
                "error_type": error_type or (type(exc).__name__ if exc else "EvaluationUnavailable"),
                "error": (error or (str(exc) if exc else ""))[:300],
            }
        )


_default_pipeline: Optional[DynamicEvaluationPipeline] = None


def get_default_pipeline() -> DynamicEvaluationPipeline:
    """Process-wide singleton — the underlying LLM clients are reusable."""
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = DynamicEvaluationPipeline()
    return _default_pipeline
