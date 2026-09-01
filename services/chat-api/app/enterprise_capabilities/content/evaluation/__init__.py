"""Dynamic-standards content evaluation.

Replaces the old task_satisfaction evaluator + planner for content tasks.
The old evaluator scored on heuristic constants (length, paragraph count,
title-string-match) and stabilized scores after fake repairs.

This package is evaluation-only. It performs three steps:

    1. ask LLM for verifiable standards (from the user's request alone)
    2. ask LLM which standards the content fails

REPAIR is intentionally NOT part of this package. An isolated repair LLM
loses all the original generation context — publish channel, profile
preset, user skills, compose policy, formatting rules. Running such a
"context-blind editor" on the writer's output silently violates the
constraints the writer was honoring. Instead, the issue list is handed
back to the writer engine (which has the full context) for regeneration:

    - whole-document regen via `output_spec["dynamic_evaluation"]` carrying
      issues to the existing retry path
    - per-section regen inside `WriterEnginePipeline.generate()` sectional
      loop, evaluating each section as it's produced

No feature flag — this is the only evaluation pipeline. The legacy
heuristic stack has been removed.
"""
from app.enterprise_capabilities.content.evaluation.contracts import (
    EvaluationResult,
    Issue,
    Severity,
    Standard,
    Verdict,
    derive_verdict,
)
from app.enterprise_capabilities.content.evaluation.feedback import (
    issues_as_writer_feedback,
    issues_summary,
)
from app.enterprise_capabilities.content.evaluation.pipeline import (
    DynamicEvaluationPipeline,
    get_default_pipeline,
)

__all__ = [
    "DynamicEvaluationPipeline",
    "EvaluationResult",
    "Issue",
    "Severity",
    "Standard",
    "Verdict",
    "derive_verdict",
    "get_default_pipeline",
    "issues_as_writer_feedback",
    "issues_summary",
]
