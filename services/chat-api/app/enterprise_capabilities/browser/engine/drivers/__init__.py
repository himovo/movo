"""Browser driver abstraction.

A driver is the "decision engine" that picks the next tool call given
the current observation, history, and any context-supplied hints. Two
drivers exist:

* :class:`ExplorationDriver` — wraps the LLM planner; the model decides
  each step from scratch. Default for any task without a recorded skill.
* :class:`SkillDriver` — replays a recorded composite_task step list
  strictly, one Decision per step. Once steps are exhausted (or a step
  cannot be resolved against the current page), control delegates to a
  fallback driver — typically an :class:`ExplorationDriver` — so the
  LLM can finish the task.

The driver is task-type agnostic: a ``FormContext``,
``ScrapeContext`` or ``NullContext`` all work with either driver. The
driver only decides WHAT TO DO NEXT; the context decides WHAT TO TRACK
and HOW TO FINISH.

Public API:

* :class:`BrowserDriver` — interface every driver implements.
* :func:`select_driver` — picks the right driver based on
  ``output_spec`` (presence / absence of a composite_task skill).
"""
from __future__ import annotations

from .base import (
    apply_driver_resume_signal,
    BrowserDriver,
    notify_driver_rejection,
    notify_effect_receipt,
    notify_step_completed,
    prepare_driver_dispatch,
)
from .exploration import ExplorationDriver
from .factory import select_driver
from .skill import SkillDriver

__all__ = [
    "BrowserDriver",
    "apply_driver_resume_signal",
    "ExplorationDriver",
    "SkillDriver",
    "notify_driver_rejection",
    "notify_effect_receipt",
    "notify_step_completed",
    "prepare_driver_dispatch",
    "select_driver",
]
