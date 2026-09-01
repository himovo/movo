"""Strict step replay of a recorded ``composite_task`` skill.

Replays the parsed step list one Decision per turn:

* ``navigate_url`` set    → ``browser_navigate``
* ``fill_value``  set     → ``browser_fill`` (locator must resolve)
* otherwise (locator only) → ``browser_click``

When a step's locator can't be resolved against the current
observation (page hasn't rendered the element yet, scroll required,
etc.), the driver issues a no-op ``browser_observe`` to let the page
settle and retries on the next turn — up to a small budget. After
that budget, or when all steps are consumed, the driver permanently
hands control to the fallback driver so the task can still finish.

The driver is intentionally site-agnostic. Locator matching uses only
the structured signal bag captured by the recorder
(``role / name / name_contains / aria_label / icon_class / text /
ancestor_role / ancestor_contains_text / nth``); no business
keywords, no per-site special cases.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision,
    Observation,
    StepRecord,
)

from .base import BrowserDriver, notify_step_completed

# Rationale prefix written onto every script-derived Decision. Used by
# ``on_step_completed`` to distinguish the driver's own decisions from
# externally injected ones (e.g. context rule auto-execution, executor-level
# soft-recovery navigates) so internal cursor tracking doesn't advance
# on third-party decisions.
_DRIVER_TAG = "[skill_driver]"
_RECOVERY_TAG = "[skill_driver:recover]"


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _element_signal(element: Dict[str, Any]) -> Dict[str, str]:
    """Extract the comparable signals from an observation element.

    Mirrors the recorder's locator schema so locator-vs-element
    matching can compare like for like. ``description`` and ``text``
    are looked up too because the agent's compact observation
    sometimes folds icon-class hints there instead of into a
    dedicated field.
    """
    return {
        "role": _normalize(element.get("role")),
        "name": _normalize(element.get("name")),
        "description": _normalize(element.get("description")),
        "text": _normalize(element.get("text")),
        "aria_label": _normalize(element.get("aria_label") or element.get("ariaLabel")),
    }


def _match_score(element: Dict[str, Any], locator: Dict[str, Any]) -> int:
    """Score how well an element satisfies a locator.

    Returns 0 when any *hard* constraint mismatches — caller treats 0
    as "not a match". Positive scores rank candidates by specificity
    (exact name > contains > aria > icon class > ancestor text), so
    higher score wins ties.
    """
    if not isinstance(element, dict) or not isinstance(locator, dict):
        return 0
    sig = _element_signal(element)

    # ── Hard constraints (any mismatch invalidates the candidate) ──
    want_role = _normalize(locator.get("role"))
    if want_role and sig["role"] and sig["role"] != want_role:
        return 0
    want_name = _normalize(locator.get("name"))
    want_contains = _normalize(locator.get("name_contains"))
    if want_name:
        # Exact name takes priority. ``name_contains`` covers the
        # softer "name contains substring" case; if neither matches we
        # bail unless the user provided ONLY name_contains.
        if sig["name"] != want_name:
            if not want_contains or want_contains not in sig["name"]:
                return 0

    # ── Scoring ──
    score = 0
    if want_role:
        score += 5
    if want_name and sig["name"] == want_name:
        score += 12
    if want_contains:
        if want_contains in sig["name"]:
            score += 6
        elif want_contains in sig["description"] or want_contains in sig["text"]:
            score += 3
        else:
            return 0  # contains is hard when explicitly set
    want_aria = _normalize(locator.get("aria_label"))
    if want_aria and (want_aria == sig["aria_label"] or want_aria in sig["name"]):
        score += 3
    want_icon = _normalize(locator.get("icon_class"))
    if want_icon and want_icon in sig["description"]:
        score += 4
    want_text = _normalize(locator.get("text"))
    if want_text:
        if sig["text"] == want_text or want_text in sig["name"]:
            score += 4
        else:
            return 0
    want_ancestor_text = _normalize(locator.get("ancestor_contains_text"))
    if want_ancestor_text and want_ancestor_text in sig["description"]:
        score += 3
    want_ancestor_role = _normalize(locator.get("ancestor_role"))
    if want_ancestor_role and want_ancestor_role in sig["description"]:
        score += 2
    return score


def _resolve_ref(observation: Observation, locator: Dict[str, Any]) -> Optional[str]:
    """Pick the best matching ``ref`` for a locator from the current
    observation, honouring an optional ``nth`` selector.

    Returns ``None`` when nothing scores above zero.
    """
    if not isinstance(locator, dict) or not locator:
        return None
    elements = list(getattr(observation, "elements", None) or [])
    candidates: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        s = _match_score(el, locator)
        if s > 0:
            candidates.append({"score": s, "el": el})
    if not candidates:
        return None
    nth_raw = locator.get("nth")
    if isinstance(nth_raw, int):
        # nth uses document order, not score order, because the
        # recorder writes the index of the matched element in the live
        # DOM. Score-based ranking is for tie-breaking when nth is
        # absent.
        candidates.sort(key=lambda c: elements.index(c["el"]))
        if 0 <= nth_raw < len(candidates):
            return str(candidates[nth_raw]["el"].get("ref") or "") or None
        return None
    candidates.sort(key=lambda c: -c["score"])
    return str(candidates[0]["el"].get("ref") or "") or None


def _step_locator(step: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the locator dict for this step.

    composite_task supports both per-op locator bags
    (``locators: {primary: {...}, update: {...}}``) and a single
    ``locator: {...}`` shorthand. The replay driver always uses
    ``primary`` (or the bare locator) — per-op aliasing is a
    task-context concern and is read by the rule engine, not the
    driver.
    """
    locators = step.get("locators") if isinstance(step.get("locators"), dict) else None
    if isinstance(locators, dict) and isinstance(locators.get("primary"), dict):
        return locators["primary"]
    raw = step.get("locator")
    return raw if isinstance(raw, dict) else {}


def _step_to_decision(
    step: Dict[str, Any],
    observation: Observation,
) -> Optional[Decision]:
    """Translate a single step into a concrete Decision.

    Returns ``None`` when the step references the current page but
    can't resolve its locator against ``observation.elements`` — the
    caller treats that as "page not ready, observe and retry".
    """
    instruction = str(step.get("instruction") or "").strip()
    rationale = f"{_DRIVER_TAG} {instruction[:200]}"

    nav_url = str(step.get("navigate_url") or "").strip()
    if nav_url:
        return Decision(
            tool="browser_navigate",
            args={"url": nav_url},
            rationale=rationale,
        )

    locator = _step_locator(step)

    if "fill_value" in step:
        ref = _resolve_ref(observation, locator) if locator else None
        if not ref:
            return None
        return Decision(
            tool="browser_fill",
            args={"ref": ref, "value": str(step.get("fill_value") or "")},
            rationale=rationale,
        )

    # Default: a click step.
    ref = _resolve_ref(observation, locator) if locator else None
    if not ref:
        # No navigate, no fill, no resolved locator → can't replay.
        return None
    return Decision(
        tool="browser_click",
        args={"ref": ref},
        rationale=rationale,
    )


class SkillDriver(BrowserDriver):
    """Replays composite_task steps in order; falls back when stuck.

    State machine:

    * ``_idx`` — index of the next step to consume. Advances on a
      successful round-trip of a script-derived decision.
    * ``_unresolved_streak`` — consecutive turns we issued a recovery
      observe because the next step's locator couldn't resolve.
      Resets when a step finally fires.
    * ``_handed_off`` — once true, we've given up on the script and
      delegate every subsequent ``next_step`` to the fallback driver.

    ``on_step_completed`` only advances the cursor when the executed
    decision matches the one we returned last turn. External rule
    auto-executions (context rule layer, executor soft-recovery navigates)
    do NOT consume our cursor — they're effectively transparent to
    script replay.
    """

    # If the next step's locator misses this many turns running, give
    # up the script. Three observe-retries is generous for normal SPA
    # render delays without burning the whole step budget.
    _UNRESOLVED_RETRY_BUDGET = 3

    def __init__(
        self,
        *,
        steps: List[Dict[str, Any]],
        fallback: BrowserDriver,
    ) -> None:
        self._steps: List[Dict[str, Any]] = list(steps or [])
        self._fallback: BrowserDriver = fallback
        self._idx: int = 0
        self._unresolved_streak: int = 0
        self._handed_off: bool = False
        # (tool, ref/url/value-tuple) of the last decision we returned.
        # Used by on_step_completed to ignore externally injected ones.
        self._last_signature: Optional[tuple] = None
        self._last_was_recovery: bool = False
        self._last_delegated: bool = False
        self._dispatch_prepared_by_fallback: bool = False

    # ── Public introspection ──
    @property
    def kind(self) -> str:
        return f"skill_driven+fallback:{self._fallback.kind}"

    @property
    def total_steps(self) -> int:
        return len(self._steps)

    @property
    def steps_remaining(self) -> int:
        return max(0, len(self._steps) - self._idx)

    @property
    def script_done(self) -> bool:
        return self._handed_off or self._idx >= len(self._steps)

    def export_checkpoint_state(self) -> Dict[str, Any]:
        return {
            "version": 2,
            "index": self._idx,
            "unresolved_streak": self._unresolved_streak,
            "handed_off": self._handed_off,
            "fallback_state": self._fallback.export_checkpoint_state(),
        }

    def restore_checkpoint_state(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        self._idx = min(len(self._steps), max(0, int(state.get("index") or 0)))
        self._unresolved_streak = max(0, int(state.get("unresolved_streak") or 0))
        self._handed_off = bool(state.get("handed_off"))
        fallback_state = state.get("fallback_state")
        if isinstance(fallback_state, dict):
            self._fallback.restore_checkpoint_state(fallback_state)
        self._last_signature = None
        self._last_was_recovery = False
        self._last_delegated = False
        self._dispatch_prepared_by_fallback = False

    # ── Driver protocol ──
    async def next_step(
        self,
        goal: str,
        history: List[StepRecord],
        observation: Observation,
        state_ledger: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        if self._handed_off or self._idx >= len(self._steps):
            decision = await self._fallback.next_step(
                goal, history, observation, state_ledger=state_ledger,
            )
            self._last_signature = None  # not ours
            self._last_was_recovery = False
            self._last_delegated = True
            return decision

        step = self._steps[self._idx]
        decision = _step_to_decision(step, observation)
        if decision is None:
            # Can't resolve locator yet. Try to give the page another
            # tick to render before bailing on the script entirely.
            self._unresolved_streak += 1
            if self._unresolved_streak >= self._UNRESOLVED_RETRY_BUDGET:
                self._handed_off = True
                fallback_decision = await self._fallback.next_step(
                    goal, history, observation, state_ledger=state_ledger,
                )
                self._last_signature = None
                self._last_was_recovery = False
                self._last_delegated = True
                return fallback_decision
            recovery = Decision(
                tool="browser_observe",
                args={},
                rationale=(
                    f"{_RECOVERY_TAG} step {self._idx} locator unresolved; "
                    f"retry {self._unresolved_streak}/{self._UNRESOLVED_RETRY_BUDGET}"
                ),
            )
            self._last_signature = self._sig(recovery)
            self._last_was_recovery = True
            self._last_delegated = False
            return recovery

        self._last_signature = self._sig(decision)
        self._last_was_recovery = False
        self._last_delegated = False
        return decision

    def on_step_completed(
        self,
        decision: Decision,
        ok: bool,
        observation_after: Observation,
        result: Any = None,
    ) -> None:
        prepared_by_fallback = self._dispatch_prepared_by_fallback
        if prepared_by_fallback:
            notify_step_completed(self._fallback, decision, ok, observation_after, result)
            self._dispatch_prepared_by_fallback = False
        if self._last_delegated:
            if not prepared_by_fallback:
                # A delegated decision normally reaches the fallback here.
                # Final-dispatch preparation may already have delivered it.
                notify_step_completed(self._fallback, decision, ok, observation_after, result)
            self._last_delegated = False
            return
        if self._handed_off:
            return
        # Only react to decisions we actually issued. External
        # decisions (forced by the context rule layer, etc.) bypass the
        # cursor entirely.
        if self._last_signature is None or self._sig(decision) != self._last_signature:
            return
        # Recovery observes don't consume a step.
        if self._last_was_recovery:
            self._last_signature = None
            self._last_was_recovery = False
            return
        # Real script decision was dispatched — consume the step.
        # We advance even on `ok=False`: a step that consistently
        # fails (e.g. backing element disappeared between record and
        # replay) should not block the entire script. The fallback
        # driver picks up after the script ends.
        self._idx += 1
        self._unresolved_streak = 0
        self._last_signature = None

    def apply_resume_signal(
        self,
        signal: Dict[str, Any],
        observation: Optional[Observation] = None,
    ) -> None:
        apply_signal = getattr(self._fallback, "apply_resume_signal", None)
        if callable(apply_signal):
            try:
                apply_signal(dict(signal or {}), observation)
            except TypeError:
                apply_signal(dict(signal or {}))

    def on_decision_rejected(
        self,
        decision: Decision,
        observation: Observation,
        *,
        category: str,
        reason: str,
    ) -> None:
        prepared_by_fallback = self._dispatch_prepared_by_fallback
        delegated = prepared_by_fallback or self._last_delegated or self._handed_off
        if delegated:
            self._fallback.on_decision_rejected(
                decision,
                observation,
                category=category,
                reason=reason,
            )
        elif (
            self._last_signature is not None
            and self._sig(decision) == self._last_signature
        ):
            self._unresolved_streak += 1
            if self._unresolved_streak >= self._UNRESOLVED_RETRY_BUDGET:
                self._handed_off = True
        self._dispatch_prepared_by_fallback = False
        self._last_delegated = False
        self._last_signature = None
        self._last_was_recovery = False

    def prepare_dispatch(
        self,
        decision: Decision,
        observation: Observation,
    ) -> Decision:
        prepared = self._fallback.prepare_dispatch(decision, observation)
        if prepared == decision:
            return decision
        self._dispatch_prepared_by_fallback = True
        self._last_signature = self._sig(prepared)
        self._last_was_recovery = prepared.tool == "browser_observe"
        return prepared

    # ── Internal helpers ──
    @staticmethod
    def _sig(decision: Decision) -> tuple:
        """Cheap structural equality for a Decision — tool plus the
        few arg fields the driver emits. Avoids deep-equality cost
        and is robust to extra args appearing in returned decisions
        (e.g. executor-side annotations)."""
        args = decision.args if isinstance(decision.args, dict) else {}
        return (
            str(decision.tool or ""),
            str(args.get("ref") or ""),
            str(args.get("url") or ""),
            str(args.get("value") or ""),
        )
