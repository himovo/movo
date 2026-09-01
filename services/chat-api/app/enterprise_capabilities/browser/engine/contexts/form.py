"""Form-submission context — single-shot "fill and submit" flow.

The task is considered complete once the form has been submitted and a success
signal (toast / URL change / reset) is detected.

State machine:
    phase = filling     → gather field list, suggest next unfilled field
    phase = submitting  → click submit button (rules.form.pick_submit)
    phase = verifying   → wait one turn, detect success / validation error
    phase = done        → browser_done allowed

The context is intentionally lean — it reuses rules.form wholesale
and only adds the cross-turn state tracking.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine import rules
from app.enterprise_capabilities.browser.engine.rules import page_kind as _page_kind_mod
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision, Observation, StepRecord,
)

from .base import BrowserTaskContext
from .null import NullContext


def _signals_form_mode(node: CapabilityTask, output_spec: Dict[str, Any]) -> bool:
    """Detect form tasks from the upstream schema category."""
    cts = output_spec.get("content_task_spec") if isinstance(output_spec, dict) else None
    if not isinstance(cts, dict):
        return False
    schema = cts.get("schema") if isinstance(cts.get("schema"), dict) else {}
    return str(schema.get("category") or "").strip().lower() == "form_submission"


class FormContext(BrowserTaskContext):
    active: bool = True

    PHASE_FILLING = "filling"
    PHASE_SUBMITTING = "submitting"
    PHASE_VERIFYING = "verifying"
    PHASE_DONE = "done"

    def __init__(self, *, lang: str, node: CapabilityTask, goal: str,
                 original_user_request: str) -> None:
        self.lang = lang
        self.node = node
        self.goal = goal
        self.original_user_request = original_user_request

        self.phase = self.PHASE_FILLING
        self.filled_fields: set[str] = set()   # refs we've already filled
        self._submit_ref_pool: set[str] = set()  # refs that looked like submits
        self.step_counter = 0
        self.submit_clicked_at: Optional[int] = None
        self.success_detected: bool = False
        self.validation_errors: List[Dict[str, Any]] = []

    @classmethod
    def maybe_init(
        cls, *, node: CapabilityTask, output_spec: Dict[str, Any],
        original_user_request: str, goal: str, lang: str,
    ) -> BrowserTaskContext:
        if _signals_form_mode(node, output_spec):
            return cls(
                lang=lang, node=node, goal=goal,
                original_user_request=original_user_request,
            )
        return NullContext()

    # ─── Phase tracking ────────────────────────────────────────────
    def after_step(
        self, decision: Decision, result: Any, ok: bool, current_obs: Observation,
        error: Optional[str] = None,
    ) -> None:
        self.step_counter += 1
        tool = str(getattr(decision, "tool", "") or "")
        args = dict(getattr(decision, "args", None) or {})
        if not ok:
            return
        elements = list(getattr(current_obs, "elements", None) or [])

        # Record which refs look like submit buttons from THIS page so
        # the next click can be recognised as a submit even after the
        # button has disappeared from the subsequent page.
        submit_now = rules.form.pick_submit(elements)
        for it in submit_now.items:
            ref = str(it.get("ref") or "")
            if ref:
                self._submit_ref_pool.add(ref)

        if tool == "browser_fill":
            ref = str(args.get("ref") or "")
            if ref:
                self.filled_fields.add(ref)
        elif tool == "browser_click":
            clicked_ref = str(args.get("ref") or "")
            if clicked_ref in self._submit_ref_pool:
                self.phase = self.PHASE_VERIFYING
                self.submit_clicked_at = self.step_counter

        # Outcome detection — runs regardless of phase so a success toast
        # appearing the same turn we clicked counts. A validation error
        # kicks us back to filling, mirroring how humans retry forms.
        if rules.form.detect_success_toast(elements):
            self.success_detected = True
            self.phase = self.PHASE_DONE
            return
        if self.phase == self.PHASE_VERIFYING:
            errs = rules.form.detect_validation_error(elements)
            if errs:
                self.validation_errors = errs
                self.phase = self.PHASE_FILLING

    # ─── Rules layer ───────────────────────────────────────────────
    def suggest_next_action(self, current_obs: Observation) -> Optional[Decision]:
        elements = list(getattr(current_obs, "elements", None) or [])
        if not elements:
            return None
        # Confirm dialog always takes precedence
        confirm = rules.crud.find_confirm(elements)
        if confirm.action == rules.AUTO_EXECUTE:
            el = confirm.items[0]
            return Decision(
                tool="browser_click", args={"ref": el["ref"]},
                rationale=f"rule auto-execute: confirm dialog ({confirm.reason})",
            )
        # Submit when filling is complete enough to try
        if self.phase == self.PHASE_SUBMITTING:
            submit = rules.form.pick_submit(elements)
            if submit.action == rules.AUTO_EXECUTE:
                el = submit.items[0]
                return Decision(
                    tool="browser_click", args={"ref": el["ref"]},
                    rationale=f"rule auto-execute: submit ({submit.reason})",
                )
        return None

    # ─── State ledger ──────────────────────────────────────────────
    def build_state_ledger(
        self, current_obs: Optional[Observation] = None,
    ) -> Optional[Dict[str, Any]]:
        ledger: Dict[str, Any] = {
            "phase": f"form_{self.phase}",
            "phase_goal": self._phase_goal(),
            "budget": {"step_counter": self.step_counter},
        }
        if current_obs is not None:
            elements = list(getattr(current_obs, "elements", None) or [])
            required = rules.form.find_form_fields(elements, required_only=True)
            pending = [f for f in required if str(f.get("ref") or "") not in self.filled_fields]
            if pending:
                ledger["pending_required_fields"] = pending[:12]
        if self.validation_errors:
            ledger["last_validation_errors"] = self.validation_errors[:4]
        if self.success_detected:
            ledger["success_detected"] = True
        return ledger

    def _phase_goal(self) -> str:
        zh = str(self.lang or "").startswith("zh")
        if self.phase == self.PHASE_FILLING:
            return "填完所有必填字段" if zh else "fill all required fields"
        if self.phase == self.PHASE_SUBMITTING:
            return "点击提交按钮" if zh else "click the submit button"
        if self.phase == self.PHASE_VERIFYING:
            return "等待提交结果（成功提示或校验错误）" if zh else \
                   "wait for success toast or validation errors"
        return "已完成，可 browser_done" if zh else "done — browser_done allowed"

    # ─── Termination ───────────────────────────────────────────────
    def ready_to_done(self) -> bool:
        return self.phase == self.PHASE_DONE

    def done_blocked_hint(self, current_obs: Observation) -> StepRecord:
        zh = str(self.lang or "").startswith("zh")
        reason = (
            f"表单任务未完成，当前阶段={self.phase}；请先填完必填字段并点提交。"
            if zh else
            f"Form task not complete (phase={self.phase}); fill required fields and submit first."
        )
        return StepRecord(
            observation=current_obs,
            decision=Decision(tool="__form_done_blocked__", args={},
                              rationale="form gate: premature browser_done"),
            ok=False, error=reason, result_digest="",
        )
