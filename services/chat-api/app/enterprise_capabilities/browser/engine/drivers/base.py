"""Driver interface.

A driver answers one question per turn: "given the current page and
what's happened so far, what should I tool-call next?". Two
implementations live in this package — see ``__init__`` for the
big-picture summary.

Drivers are intentionally orthogonal to BrowserTaskContext (form,
scrape, null). Any context can drive any task with any driver. To keep
this contract honest, the driver protocol intentionally avoids
context-specific arguments: the context's ledger is passed through as
an opaque ``state_ledger`` dict that the driver may or may not
consume.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import inspect
from typing import Any, Dict, List, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision,
    Observation,
    StepRecord,
)


def prepare_driver_dispatch(
    driver: Any,
    decision: Decision,
    observation: Observation,
) -> Decision:
    """Run the optional final dispatch hook without breaking legacy drivers."""

    prepare = getattr(driver, "prepare_dispatch", None)
    if not callable(prepare):
        return decision
    prepared = prepare(decision, observation)
    return prepared if isinstance(prepared, Decision) else decision


def notify_driver_rejection(
    driver: Any,
    decision: Decision,
    observation: Observation,
    *,
    category: str,
    reason: str,
) -> None:
    """Notify stateful drivers when dispatch is rejected before tool execution."""

    reject = getattr(driver, "on_decision_rejected", None)
    if not callable(reject):
        return
    reject(
        decision,
        observation,
        category=category,
        reason=reason,
    )


def notify_step_completed(
    driver: Any,
    decision: Decision,
    ok: bool,
    observation_after: Observation,
    result: Any = None,
) -> None:
    """Deliver logical tool output without breaking legacy driver adapters."""

    completed = getattr(driver, "on_step_completed", None)
    if not callable(completed):
        return
    if "result" in inspect.signature(completed).parameters:
        completed(decision, ok, observation_after, result=result)
    else:
        completed(decision, ok, observation_after)


def notify_effect_receipt(driver: Any, receipt: Any) -> None:
    """Optionally deliver a verified business receipt to cache-aware drivers."""

    handler = getattr(driver, "on_effect_receipt", None)
    if callable(handler):
        handler(receipt)


def apply_driver_resume_signal(
    driver: Any,
    signal: Dict[str, Any],
    observation: Optional[Observation] = None,
) -> None:
    """Apply typed human facts after the executor acquired a fresh page.

    ``observation`` is optional for compatibility with third-party drivers,
    but built-in stateful drivers use it to reconcile rather than blindly
    trusting checkpoint-era element references.
    """
    apply_signal = getattr(driver, "apply_resume_signal", None)
    if callable(apply_signal):
        try:
            apply_signal(dict(signal or {}), observation)
        except TypeError:
            apply_signal(dict(signal or {}))


class BrowserDriver(ABC):
    """Decides the next tool call given the running task state."""

    @property
    @abstractmethod
    def kind(self) -> str:
        """Human-readable identifier — used for logging and metrics.

        Conventions:

        * ``"exploration"`` for LLM-driven free exploration.
        * ``"skill_driven"`` for strict recorded-step replay.
        * ``"<base>+fallback:<other>"`` for composed drivers (e.g. a
          skill replay that hands off to exploration once steps run out).
        """

    @abstractmethod
    async def next_step(
        self,
        goal: str,
        history: List[StepRecord],
        observation: Observation,
        state_ledger: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        """Return the next tool call.

        The signature mirrors the legacy ``Planner.next_step`` so the
        driver is a drop-in replacement at the executor level.
        """

    def on_step_completed(
        self,
        decision: Decision,
        ok: bool,
        observation_after: Observation,
        result: Any = None,
    ) -> None:
        """Optional hook fired after the executor runs the decision.

        Default: no-op. Stateful drivers (e.g. ``SkillDriver`` tracking
        cursor position) override this to advance internal state. The
        hook receives BOTH driver-issued decisions AND any externally
        forced ones (for example context rule auto-execution); concrete drivers
        must distinguish these themselves if their state depends on
        only consuming their own decisions.
        """
        del decision, ok, observation_after, result  # unused in base impl
        return None

    def on_decision_rejected(
        self,
        decision: Decision,
        observation: Observation,
        *,
        category: str,
        reason: str,
    ) -> None:
        """Optional hook for a decision rejected before tool dispatch.

        Rejection is not equivalent to a failed browser mutation: the tool did
        not run. Stateful drivers use this hook to discard observation-local
        bindings without marking the underlying business field as failed.
        """
        del decision, observation, category, reason
        return None

    def prepare_dispatch(
        self,
        decision: Decision,
        observation: Observation,
    ) -> Decision:
        """Apply driver-owned invariants after executor decision rewrites.

        The executor may turn waits or coordinate actions into semantic
        actions after ``next_step`` returns. Decorator drivers can use this
        final hook to keep those rewritten actions inside their transaction.
        """
        del observation
        return decision

    def export_checkpoint_state(self) -> Dict[str, Any]:
        return {}

    def restore_checkpoint_state(self, state: Dict[str, Any]) -> None:
        del state
