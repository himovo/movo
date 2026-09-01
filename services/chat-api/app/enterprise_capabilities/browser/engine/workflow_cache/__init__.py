"""Automatically learned browser workflow cache.

The cache is deliberately separate from user-authored Skills. It learns a
value-free, parameterized workflow in the background and replays it through
the normal browser executor before falling back to form binding / exploration.
"""

from .contracts import (
    CachedBrowserWorkflow,
    CachedFieldBinding,
    CachedWorkflowStep,
    WorkflowIdentity,
)
from .service import browser_workflow_cache

__all__ = [
    "CachedBrowserWorkflow",
    "CachedFieldBinding",
    "CachedWorkflowStep",
    "WorkflowIdentity",
    "browser_workflow_cache",
]
