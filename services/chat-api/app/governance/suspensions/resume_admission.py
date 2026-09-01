"""Trusted admission context for continuing an already accepted task.

The public chat payload is not a trust boundary: clients can submit arbitrary
``output_spec`` fields. Only the task-resume endpoint may open this context,
after it has claimed a real suspension owned by the authenticated user.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator


_trusted_resume_admission: ContextVar[bool] = ContextVar(
    "trusted_resume_admission",
    default=False,
)


@contextmanager
def trusted_resume_admission() -> Iterator[None]:
    token = _trusted_resume_admission.set(True)
    try:
        yield
    finally:
        _trusted_resume_admission.reset(token)


def is_trusted_task_continuation(output_spec: Dict[str, Any] | None) -> bool:
    return bool(
        _trusted_resume_admission.get()
        and isinstance(output_spec, dict)
        and output_spec.get("_runtime_resume_only") is True
    )
