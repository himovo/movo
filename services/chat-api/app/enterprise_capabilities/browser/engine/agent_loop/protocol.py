"""Internal value types shared by planner + loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Observation:
    url: str
    title: str
    elements: List[Dict[str, Any]]
    # Monotonic within one browser tab/session when supplied by the desktop
    # sidecar. Decisions that mutate the page are bound to this revision so
    # stale element refs are never silently reused after a missing snapshot.
    revision: str = ""
    state_fingerprint: str = ""
    fresh: bool = True
    screenshot: Optional[str] = None
    clean_dom: Optional[Dict[str, Any]] = None
    dom_diff: Optional[Dict[str, Any]] = None
    # The visible text of the page (excerpt) — captured via
    # ``document.body.innerText`` on the observer side. Interactive-only
    # element scans miss pure-display text nodes (metric cards, status
    # widgets, report values), so the planner LLM reads this field when
    # it needs to extract displayed values.
    page_text: str = ""
    auth: Optional[Dict[str, Any]] = None
    frame_count: int = 1
    interaction: Optional[Dict[str, Any]] = None
    effects: List[Dict[str, Any]] = field(default_factory=list)
    diagnostics: Optional[Dict[str, Any]] = None
    viewport: Optional[Dict[str, Any]] = None
    screenshot_metadata: Optional[Dict[str, Any]] = None


@dataclass
class Decision:
    """One LLM turn output — the next tool to invoke."""
    tool: str
    args: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    rationale_source: str = "system"
    commentary: Optional[Dict[str, Any]] = None


@dataclass
class StepRecord:
    observation: Observation
    decision: Decision
    ok: bool
    error: Optional[str] = None
    result_digest: Optional[str] = None
    # ``decision.ref`` belongs to the pre-dispatch DOM, while ``observation``
    # normally stores the post-dispatch state. Keep both identities explicit.
    decision_observation: Optional[Observation] = None
