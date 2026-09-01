"""Abstract base for every browser task context.

The executor talks ONLY to this interface — concrete contexts (form /
scrape / general) are plugged in via ``factory.maybe_init``.

Hooks are deliberately small and uniform:
    before_decision / after_step   — state-machine driver
    build_state_ledger             — layer 1 → surface state to LLM
    suggest_next_action            — layer 2 → rules auto-execute
    validate_action                — layer 2 → pre-flight audit
    maybe_force_navigation         — layer 2 → system-owned routing
    intercept_tool                 — virtual tool handler
    ready_to_done / done_blocked_hint / finalize  — termination
    needs_plan_generation          — optional planning phase

Default implementations return harmless "do nothing" values so a new
context can start minimal and grow only what it needs."""
from __future__ import annotations

from abc import ABC
from typing import Any, Dict, List, Optional, Tuple

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision, Observation, StepRecord,
)
from app.enterprise_capabilities.browser.engine.checkpoint_state import decode_checkpoint_value, encode_checkpoint_value
from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectReceipt
from app.enterprise_capabilities.browser.engine.effect_task_outcome import EffectTaskOutcome
from .action_transition import BrowserActionTransition


class BrowserTaskContext(ABC):
    """Subclasses override whichever hooks they use. The base provides
    no-op defaults so concrete contexts stay short.

    ``active`` is read by the executor to decide whether any context
    hooks should run at all — Null contexts set it to False."""

    active: bool = False
    # ``active`` is retained for the legacy specialised-control paths in the
    # executor.  A context may still maintain planner state without enabling
    # those paths (the generic browser fallback is the first such context).
    stateful: bool = False
    _checkpoint_excluded_fields = {
        "lang", "node", "goal", "original_user_request", "output_spec",
        "_task_id", "_prior_ledger",
    }

    # ─── Phase progression ─────────────────────────────────────────
    def before_decision(
        self, history: List[StepRecord], current_obs: Observation,
    ) -> Optional[StepRecord]:
        return None

    def after_step(
        self, decision: Decision, result: Any, ok: bool, current_obs: Observation,
        error: Optional[str] = None,
    ) -> None:
        return None

    def after_transition(
        self,
        transition: BrowserActionTransition,
        result: Any,
        ok: bool,
        error: Optional[str] = None,
    ) -> None:
        """Apply one action using its original target and resulting page.

        Existing specialised contexts keep their legacy hook. Stateful SPA
        contexts may override this when target identity must survive rerenders.
        """
        if not transition.after.fresh:
            return
        self.after_step(
            transition.decision,
            result,
            ok,
            transition.after,
            error=error,
        )

    def after_effect(self, receipt: EffectReceipt, current_obs: Observation) -> None:
        """Observe a verified side effect. Non-transactional contexts ignore it."""
        return None

    def effect_completes_task(self, receipt: EffectReceipt) -> bool:
        """Decide whether a verified effect completes this context's task.

        Legacy and specialised contexts keep the effect contract's task-level
        signal. Stateful contexts with their own mission ledger may override
        this and make the ledger authoritative instead.
        """
        return (
            receipt.status == "confirmed_success"
            and bool(receipt.completes_goal)
            and self.ready_to_done()
        )

    def effect_task_outcome(self, receipt: EffectReceipt) -> EffectTaskOutcome:
        """Return the task-level disposition of a verified browser effect."""
        if self.effect_completes_task(receipt):
            return EffectTaskOutcome.complete()
        return EffectTaskOutcome.continue_()

    def business_target_hint(self, current_obs: Observation) -> str:
        """Optional stable object identity for same-URL SPA interactions."""
        return ""

    def business_effect_blocker(self, receipt_contract: Any) -> str:
        """Return a reason when another business mutation must not run."""
        return ""

    def result_evidence(self, current_obs: Observation) -> Dict[str, Any]:
        """Return compact, safe business facts for the terminal result."""
        return {}

    def interaction_purpose(
        self,
        decision: Decision,
        current_obs: Observation,
    ) -> str:
        """Return a context-proven non-business interaction purpose."""
        return ""

    # ─── Three-layer pipeline ──────────────────────────────────────
    def build_state_ledger(
        self, current_obs: Optional[Observation] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return a structured state card surfaced at the top of the
        planner prompt. None → no ledger injected."""
        return None

    def suggest_next_action(
        self, current_obs: Observation,
    ) -> Optional[Decision]:
        """Return a synthesized Decision when deterministic rules have
        a single unambiguous answer. None → fall through to the LLM."""
        return None

    def validate_action(
        self, decision: Decision, current_obs: Observation,
    ) -> Tuple[str, Decision, str]:
        """Pre-flight audit. Returns (verdict, new_decision, hint).
        verdict ∈ {'allow', 'rewrite', 'reject'}."""
        return ("allow", decision, "")

    def maybe_force_navigation(
        self, current_obs: Observation,
    ) -> Optional[Decision]:
        """Context-driven navigation (e.g. return to list after a
        detail detour). None → no forced nav this turn."""
        return None

    # ─── Termination gating ────────────────────────────────────────
    def ready_to_done(self) -> bool:
        """Whether browser_done is allowed right now."""
        return True

    def done_blocked_hint(self, current_obs: Observation) -> StepRecord:
        """Only called when ready_to_done() returned False. Returns a
        StepRecord explaining why the done call was blocked."""
        raise NotImplementedError(
            "done_blocked_hint must be overridden by any context that "
            "can return ready_to_done()=False"
        )

    def finalize(
        self, summary: str, data: Dict[str, Any], *,
        partial: bool = False, partial_reason: str = "",
    ) -> Tuple[str, Dict[str, Any]]:
        """Post-process the browser_done payload."""
        return summary, data

    # ─── Miscellaneous executor-facing queries ─────────────────────
    def checkpoint_dataclasses(self) -> Dict[str, type]:
        return {}

    def export_checkpoint_state(self) -> Dict[str, Any]:
        state: Dict[str, Any] = {}
        for key, value in vars(self).items():
            if key in self._checkpoint_excluded_fields:
                continue
            state[key] = encode_checkpoint_value(value)
        return {"version": 1, "context": type(self).__name__, "state": state}

    def restore_checkpoint_state(self, payload: Dict[str, Any]) -> None:
        if not isinstance(payload, dict) or payload.get("context") != type(self).__name__:
            return
        state = payload.get("state")
        if not isinstance(state, dict):
            return
        registry = self.checkpoint_dataclasses()
        for key, value in state.items():
            if key in self._checkpoint_excluded_fields or not hasattr(self, key):
                continue
            setattr(self, key, decode_checkpoint_value(value, dataclasses=registry))
