from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from app.enterprise_capabilities.browser.engine.drivers.base import BrowserDriver, notify_step_completed
from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord

from .contracts import CachedBrowserWorkflow, CachedWorkflowStep
from .completion import build_local_completion
from .page_state import same_url_shape
from .parameters import RuntimeParameterResolver
from .preconditions import RuntimePreconditionGate
from .replay_evidence import replay_postcondition_satisfied
from .replay_plan import build_replay_plan
from .replay_target_resolution import resolve_replay_target
from .stability import readiness_probe, replay_failure_reason, safe_to_retry
from .successor_state import SuccessorState, classify_successor
from .target_state import logical_action_succeeded


_TAG = "[learned_workflow]"


class LearnedWorkflowDriver(BrowserDriver):
    """Replay a parameterized workflow with live state checks and safe fallback."""

    def __init__(
        self,
        *,
        workflow: CachedBrowserWorkflow,
        fallback: BrowserDriver,
        input_context: BrowserInputContext,
        lang: str = "zh",
        on_failure: Callable[[str], None] | None = None,
    ) -> None:
        self.workflow = workflow
        replay_plan = build_replay_plan(workflow, input_context)
        self._steps = replay_plan.steps
        self._partial_replay = replay_plan.mode == "partial"
        self._missing_roles = replay_plan.missing_roles
        self._replay_step_count = len(self._steps) if self._partial_replay else -1
        self._fallback = fallback
        self._parameters = RuntimeParameterResolver(
            context=input_context,
            request_template=workflow.request_template,
        )
        self._on_failure = on_failure
        self._lang = str(lang or "zh")
        self._index = 0
        self._handoff = False
        self._unresolved_once = False
        self._last_signature: tuple[str, str, str, str] | None = None
        self._last_delegated = False
        self._before_observation: Observation | None = None
        self._pending_step: CachedWorkflowStep | None = None
        self._failure_reported = False
        self._completion_emitted = False
        self._replay_failed = False
        self._terminal_effect_confirmed = False
        self._terminal_effect_dispatched = False
        self._attempted_cached_step = False
        self._recovery_step: CachedWorkflowStep | None = None
        self._recovery_before: Observation | None = None
        self._recovery_phase = ""
        self._recovery_probe_advances = False
        self._recovery_successor_waits = 0
        self._preconditions = RuntimePreconditionGate(
            workflow.runtime_preconditions, lang=self._lang,
        )

    @property
    def kind(self) -> str:
        mode = "partial" if self._partial_replay else "full"
        return f"learned_workflow:{mode}+fallback:{self._fallback.kind}"

    @property
    def workflow_id(self) -> str:
        return self.workflow.workflow_id

    @property
    def replayed_any(self) -> bool:
        return (
            self._attempted_cached_step
            or self._index > 0
            or bool(getattr(self._fallback, "replayed_any", False))
        )

    @property
    def replay_failed(self) -> bool:
        return self._replay_failed

    @property
    def replay_completed(self) -> bool:
        effect_required = bool(
            self.workflow.completion is not None
            and str(self.workflow.completion.capability_id or "").casefold() in {
                "browser.submit", "browser.modify", "browser.delete",
                "browser.publish", "browser.publish_or_submit",
            }
        )
        return bool(
            not self._partial_replay
            and not self._replay_failed
            and self._index >= len(self._steps)
            and (not effect_required or self._terminal_effect_confirmed)
        )

    def on_effect_receipt(self, receipt: Any) -> None:
        if not self._terminal_effect_dispatched or not self._receipt_matches_terminal(receipt):
            return
        status = str(getattr(receipt, "status", "") or "").casefold()
        if status == "confirmed_success":
            self._terminal_effect_confirmed = True
        elif status == "confirmed_failure":
            self._handoff = True
            self._fail("cached terminal business effect was rejected")

    def _receipt_matches_terminal(self, receipt: Any) -> bool:
        if not self._steps:
            return False
        action = " ".join(str(getattr(receipt, "action_name", "") or "").casefold().split())
        locator = self._steps[-1].locator or {}
        labels = {
            " ".join(str(locator.get(key) or "").casefold().split())
            for key in ("name", "text")
            if str(locator.get(key) or "").strip()
        }
        return bool(action and action in labels)

    async def next_step(
        self,
        goal: str,
        history: List[StepRecord],
        observation: Observation,
        state_ledger: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        recovery = await self._next_recovery_step(
            goal, history, observation, state_ledger=state_ledger,
        )
        if recovery is not None:
            return recovery
        precondition = self._preconditions.evaluate(
            self._steps,
            index=self._index,
            observation=observation,
            resolve=self._parameters.resolve,
        )
        if precondition.index != self._index:
            self._index = precondition.index
            self._unresolved_once = False
        if precondition.decision is not None:
            return self._prepare_precondition_decision(precondition.decision)
        if self._index == 0 and not self._all_parameters_resolve():
            self._fail("cached workflow parameters did not match the current request")
            self._handoff = True
        if not self._handoff and self._index >= len(self._steps):
            if (
                not self._partial_replay
                and self.workflow.completion is not None
                and self.workflow.completion.enabled
            ):
                if not self._completion_emitted:
                    decision = build_local_completion(
                        self.workflow.completion,
                        observation,
                        lang=self._lang,
                    )
                    if decision is None:
                        self._fail("cached workflow lacks sufficient local completion evidence")
                        self._handoff = True
                        return await self._fallback.next_step(
                            goal, history, observation, state_ledger=state_ledger,
                        )
                    self._completion_emitted = True
                    self._last_delegated = False
                    self._last_signature = _signature(decision)
                    return decision
                self._fail("cached local completion was rejected")
                self._handoff = True
        if self._handoff or self._index >= len(self._steps):
            self._handoff = True
            self._last_delegated = True
            self._last_signature = None
            return await self._fallback.next_step(
                goal, history, observation, state_ledger=state_ledger,
            )
        step = self._steps[self._index]
        if (
            step.tool not in {"browser_navigate", "browser_tab_new"}
            and not same_url_shape(observation.url, step.source_url_shape)
        ):
            self._fail("cached step page precondition did not match")
            self._handoff = True
            self._last_delegated = True
            return await self._fallback.next_step(
                goal, history, observation, state_ledger=state_ledger,
            )
        decision = _decision_for_step(step, observation, self._parameters)
        if decision is None:
            if not self._unresolved_once:
                self._unresolved_once = True
                recovery = Decision(
                    tool="browser_observe",
                    args={},
                    rationale=f"{_TAG} refresh before abandoning unresolved cached locator",
                )
                self._last_signature = _signature(recovery)
                self._last_delegated = False
                return recovery
            precondition_pause = self._preconditions.pause_for_unresolved()
            if precondition_pause is not None:
                return self._prepare_precondition_decision(precondition_pause)
            self._handoff = True
            self._fail("cached parameter or locator could not be resolved uniquely")
            self._last_delegated = True
            self._last_signature = None
            return await self._fallback.next_step(
                goal, history, observation, state_ledger=state_ledger,
            )
        self._last_signature = _signature(decision)
        self._last_delegated = False
        self._before_observation = observation
        self._pending_step = step
        self._attempted_cached_step = True
        if self._index == len(self._steps) - 1:
            self._terminal_effect_dispatched = True
        return decision

    def prepare_dispatch(self, decision: Decision, observation: Observation) -> Decision:
        prepared = self._fallback.prepare_dispatch(decision, observation)
        if not self._last_delegated:
            self._last_signature = _signature(prepared)
        return prepared

    def on_step_completed(
        self,
        decision: Decision,
        ok: bool,
        observation_after: Observation,
        result: Any = None,
    ) -> None:
        if self._last_delegated:
            notify_step_completed(self._fallback, decision, ok, observation_after, result)
            self._last_delegated = False
            return
        if self._last_signature != _signature(decision):
            return
        if self._recovery_step is not None:
            self._on_recovery_completed(decision, ok, observation_after, result)
            self._last_signature = None
            return
        if decision.tool == "browser_observe" and self._unresolved_once:
            self._last_signature = None
            return
        if ok and self._postcondition_matches(observation_after, result):
            self._index += 1
            self._unresolved_once = False
        else:
            step = self._pending_step
            before = self._before_observation
            if step is not None and step.expect_state_change:
                self._begin_recovery(step, before)
            else:
                self._handoff = True
                self._fail(
                    replay_failure_reason(self._index, step)
                    if step is not None else
                    "cached step execution or postcondition failed"
                )
        self._last_signature = None
        self._before_observation = None
        self._pending_step = None

    def on_decision_rejected(
        self,
        decision: Decision,
        observation: Observation,
        *,
        category: str,
        reason: str,
    ) -> None:
        if self._last_delegated:
            self._fallback.on_decision_rejected(
                decision, observation, category=category, reason=reason,
            )
        else:
            self._handoff = True
            self._fail(f"cached decision rejected: {category}")
        self._last_signature = None
        self._last_delegated = False

    def _postcondition_matches(self, after: Observation, result: Any = None) -> bool:
        step = self._pending_step
        before = self._before_observation
        if step is None:
            return True
        return self._postcondition_matches_for(step, before, after, result)

    def _fail(self, reason: str) -> None:
        if self._failure_reported:
            return
        self._failure_reported = True
        self._replay_failed = True
        if self._on_failure is not None:
            self._on_failure(reason)

    def _all_parameters_resolve(self) -> bool:
        return all(
            self._parameters.resolve(binding) is not None
            for step in self._steps
            for binding in (*step.arg_bindings.values(), *step.locator_bindings.values())
        )

    def _prepare_precondition_decision(self, decision: Decision) -> Decision:
        self._last_signature = _signature(decision)
        self._last_delegated = False
        self._pending_step = None
        self._before_observation = None
        return decision

    def export_checkpoint_state(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "workflow_id": self.workflow_id,
            "index": self._index,
            "handoff": self._handoff,
            "completion_emitted": self._completion_emitted,
            "replay_failed": self._replay_failed,
            "terminal_effect_confirmed": self._terminal_effect_confirmed,
            "terminal_effect_dispatched": self._terminal_effect_dispatched,
            "attempted_cached_step": self._attempted_cached_step,
            "replay_step_count": self._replay_step_count,
            "missing_input_roles": list(self._missing_roles),
            "fallback_state": self._fallback.export_checkpoint_state(),
            "precondition_state": self._preconditions.export(),
        }

    def restore_checkpoint_state(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict) or str(state.get("workflow_id") or "") != self.workflow_id:
            return
        replay_step_count = int(state.get("replay_step_count", self._replay_step_count))
        if 0 <= replay_step_count < len(self.workflow.steps):
            self._steps = tuple(self.workflow.steps[:replay_step_count])
            self._partial_replay = True
            self._replay_step_count = replay_step_count
            self._missing_roles = tuple(
                str(item or "").strip().casefold()
                for item in list(state.get("missing_input_roles") or [])
                if str(item or "").strip()
            )
        self._index = min(len(self._steps), max(0, int(state.get("index") or 0)))
        self._handoff = bool(state.get("handoff"))
        self._completion_emitted = bool(state.get("completion_emitted"))
        self._attempted_cached_step = bool(
            state.get("attempted_cached_step", self._index > 0)
        )
        fallback_state = state.get("fallback_state")
        if isinstance(fallback_state, dict):
            self._fallback.restore_checkpoint_state(fallback_state)
        self._unresolved_once = False
        self._last_signature = None
        self._last_delegated = False
        self._before_observation = None
        self._pending_step = None
        self._recovery_step = None
        self._recovery_before = None
        self._recovery_phase = ""
        self._recovery_probe_advances = False
        self._recovery_successor_waits = 0
        self._replay_failed = bool(state.get("replay_failed", self._replay_failed))
        self._terminal_effect_confirmed = bool(state.get("terminal_effect_confirmed"))
        self._terminal_effect_dispatched = bool(state.get("terminal_effect_dispatched"))
        precondition_state = state.get("precondition_state")
        if isinstance(precondition_state, dict):
            self._preconditions.restore(precondition_state)

    def apply_resume_signal(
        self,
        signal: Dict[str, Any],
        observation: Observation | None = None,
    ) -> None:
        self._preconditions.apply_resume_signal(signal)
        apply_signal = getattr(self._fallback, "apply_resume_signal", None)
        if callable(apply_signal):
            apply_signal(signal, observation)

    async def _next_recovery_step(
        self,
        goal: str,
        history: List[StepRecord],
        observation: Observation,
        *,
        state_ledger: Optional[Dict[str, Any]],
    ) -> Decision | None:
        step = self._recovery_step
        if step is None:
            return None
        if self._recovery_phase in {"probe", "wait_successor"}:
            successor = (
                self._steps[self._index + 1]
                if self._index + 1 < len(self._steps) else None
            )
            probe = readiness_probe(
                successor,
                self._parameters.resolve,
                timeout_ms=2000 if self._recovery_phase == "wait_successor" else 5000,
            )
            # A successful wait derived from the successor is direct evidence
            # that the current action reached the required state. This is
            # especially important for same-page menus and async disclosures,
            # where a whole-page fingerprint may remain unchanged.
            self._recovery_probe_advances = probe is not None
            if probe is None:
                probe = Decision(
                    tool="browser_observe",
                    args={},
                    rationale="[learned_workflow] refresh delayed postcondition",
                )
            self._recovery_phase = "probe_dispatched"
            self._last_signature = _signature(probe)
            self._last_delegated = False
            return probe
        if self._recovery_phase == "retry":
            retried = _decision_for_step(step, observation, self._parameters)
            if retried is None:
                self._finish_recovery_failure()
                self._last_delegated = True
                return await self._fallback.next_step(
                    goal, history, observation, state_ledger=state_ledger,
                )
            self._recovery_phase = "retry_dispatched"
            self._last_signature = _signature(retried)
            self._last_delegated = False
            self._attempted_cached_step = True
            return retried
        return None

    def _begin_recovery(
        self,
        step: CachedWorkflowStep,
        before: Observation | None,
    ) -> None:
        self._recovery_step = step
        self._recovery_before = before
        self._recovery_phase = "probe"
        self._recovery_probe_advances = False
        self._recovery_successor_waits = 0

    def _on_recovery_completed(
        self,
        decision: Decision,
        ok: bool,
        observation_after: Observation,
        result: Any = None,
    ) -> None:
        step = self._recovery_step
        if step is None:
            return
        if self._recovery_phase == "probe_dispatched":
            successor = (
                self._steps[self._index + 1]
                if self._index + 1 < len(self._steps) else None
            )
            successor_state = classify_successor(
                successor,
                observation_after,
                self._parameters.resolve,
                before=self._recovery_before,
            )
            if (
                ok
                and self._recovery_probe_advances
                and logical_action_succeeded(
                    decision.tool, result, observation_after.diagnostics,
                )
                and successor_state == SuccessorState.ACTIONABLE
            ):
                self._finish_recovery_success()
                return
            if (
                successor_state == SuccessorState.PRESENT_NOT_READY
                and self._recovery_successor_waits < 2
            ):
                # The opener already produced its exact successor. Repeating
                # it can close a menu/drawer, so hold the achieved state and
                # wait for the successor's activation surface to stabilize.
                self._recovery_successor_waits += 1
                self._recovery_phase = "wait_successor"
                return
            if (
                not self._recovery_probe_advances
                and ok
                and self._postcondition_matches_for(
                    step, self._recovery_before, observation_after, result,
                    allow_deferred_completion=False,
                )
            ):
                self._finish_recovery_success()
                return
            if successor_state == SuccessorState.PRESENT_NOT_READY:
                self._finish_recovery_failure()
                return
            if safe_to_retry(step):
                self._recovery_phase = "retry"
                return
            self._finish_recovery_failure()
            return
        if self._recovery_phase == "retry_dispatched":
            if ok and self._postcondition_matches_for(
                step, self._recovery_before, observation_after, result,
            ):
                self._finish_recovery_success()
            else:
                self._finish_recovery_failure()

    def _finish_recovery_success(self) -> None:
        self._index += 1
        self._unresolved_once = False
        self._clear_recovery()

    def _finish_recovery_failure(self) -> None:
        step = self._recovery_step
        if self._index == len(self._steps) - 1:
            self._terminal_effect_dispatched = False
        self._handoff = True
        self._fail(
            replay_failure_reason(self._index, step)
            if step is not None else
            "cached step execution or postcondition failed"
        )
        self._clear_recovery()

    def _clear_recovery(self) -> None:
        self._recovery_step = None
        self._recovery_before = None
        self._recovery_phase = ""
        self._recovery_probe_advances = False
        self._recovery_successor_waits = 0
        self._before_observation = None
        self._pending_step = None

    def _postcondition_matches_for(
        self,
        step: CachedWorkflowStep,
        before: Observation | None,
        after: Observation,
        result: Any = None,
        *,
        allow_deferred_completion: bool = True,
    ) -> bool:
        successor = (
            self._steps[self._index + 1]
            if self._index + 1 < len(self._steps) else None
        )
        return replay_postcondition_satisfied(
            step,
            before=before,
            after=after,
            resolve=self._parameters.resolve,
            successor=successor,
            allow_deferred_completion=bool(
                allow_deferred_completion
                and
                successor is None
                and self.workflow.completion is not None
                and self.workflow.completion.enabled
            ),
            result=result,
        )


def _decision_for_step(
    step: CachedWorkflowStep,
    observation: Observation,
    parameters: RuntimeParameterResolver,
) -> Decision | None:
    args = dict(step.args or {})
    for key, binding in step.arg_bindings.items():
        value = parameters.resolve(binding)
        if value is None:
            return None
        args[key] = value
    if step.tool in {"browser_navigate", "browser_tab_new", "browser_back", "browser_forward"}:
        return Decision(tool=step.tool, args=args, rationale=f"{_TAG} cached route")
    locator = dict(step.locator or {})
    for key, binding in step.locator_bindings.items():
        value = parameters.resolve(binding)
        if value is None:
            return None
        locator[key] = str(value)
    if locator:
        ref = resolve_replay_target(
            locator, observation.elements, tool=step.tool,
        ).ref
        if not ref:
            return None
        args["editor_ref" if step.tool == "browser_paste_image" else "ref"] = ref
    elif step.tool in {"browser_click", "browser_hover"}:
        return None
    if step.tool == "browser_click":
        # Internal execution provenance.  The local sidecar uses this only to
        # enable replay-specific recovery; LLM exploration never receives it.
        args["__workflow_replay"] = True
    return Decision(tool=step.tool, args=args, rationale=f"{_TAG} cached semantic target")


def _signature(decision: Decision) -> tuple[str, str, str, str]:
    args = decision.args if isinstance(decision.args, dict) else {}
    return (
        str(decision.tool or ""),
        str(args.get("ref") or ""),
        str(args.get("url") or ""),
        str(args.get("key") or args.get("direction") or ""),
    )


__all__ = ["LearnedWorkflowDriver"]
