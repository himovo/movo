"""Durable state for ordinary multi-step browser tasks.

Unlike the specialised form/scrape contexts, this context does not take
over action selection.  It records compact, site-agnostic milestones so the
planner does not have to reconstruct the whole task from its short history.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import urlparse

from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectReceipt
from app.enterprise_capabilities.browser.engine.effect_task_outcome import EffectTaskOutcome
from app.enterprise_capabilities.browser.engine.operation_intent import (
    is_final_commit_control,
    stops_before_final_commit,
)
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord

from .base import BrowserTaskContext
from .action_transition import ActionTargetSnapshot, BrowserActionTransition
from .content_evidence import observed_content_text
from .detail_progress import (
    DetailPageBaseline,
    DetailTargetFingerprint,
    capture_detail_target,
    capture_detail_baseline,
    detail_page_observed,
    same_detail_resource,
)
from .effect_goal_binding import bind_effect_to_commit_goal
from .detail_target_lock import DetailTargetLock
from .detail_write_gate import DetailWriteGate
from .detail_candidate_lifecycle import classify_detail_candidate_return
from .general_mission import GeneralMissionLedger, SearchCycle
from .inline_target_editor import inline_target_editor_observed
from .intent_requirements import compile_general_requirements
from .operation_contract import BrowserOperationContract
from .search_progress import (
    ObservedSearchResult,
    SearchBaseline,
    capture_search_baseline,
    infer_search_result_from_observation,
    infer_observed_search_result,
    search_submission_confirmed,
)
from .search_submission_policy import (
    SearchSubmissionState,
    begin_search_submission,
    record_search_submission_transition,
    suggest_search_submission_action,
)


_SIGNAL_LABELS = {
    "navigate": "target_page_opened",
    "search": "search_submitted",
    "open_result": "requested_result_opened",
    "read": "requested_content_read",
    "return": "returned_to_requested_page",
    "commit": "requested_operation_confirmed",
}


class GeneralBrowserContext(BrowserTaskContext):
    """State-only fallback for tasks that have no specialised context."""

    active = False
    stateful = True
    MAX_PAGE_MILESTONES = 32
    MAX_EVIDENCE_ITEMS = 12
    MAX_EVIDENCE_CHARS = 1200
    _checkpoint_excluded_fields = BrowserTaskContext._checkpoint_excluded_fields | {
        "operation_contract",
    }

    def __init__(
        self,
        *,
        lang: str,
        node: CapabilityTask,
        goal: str,
        original_user_request: str,
        prefulfilled_requirements: Optional[Iterable[str]] = None,
    ) -> None:
        self.lang = lang
        self.node = node
        self.goal = goal
        self.original_user_request = original_user_request
        self.operation_contract = BrowserOperationContract.from_node(node)
        self.step_counter = 0
        self.phase = "starting"
        # The capability goal is the execution contract for this browser run.
        # The original chat request may describe work already completed by an
        # earlier browser run (for example search -> open detail -> verify).
        # Recompiling all milestones from that original text makes a focused
        # verification run incorrectly demand that it repeat the search.
        intent_text = str(goal or original_user_request or "")
        safety_intent_text = f"{original_user_request}\n{goal}"
        self.stop_before_final_commit = stops_before_final_commit(safety_intent_text)
        self.requirements: Set[str] = self.operation_contract.constrain_requirements(
            self._compile_requirements(intent_text)
        )
        if self.stop_before_final_commit:
            self.requirements.discard("commit")
        self.prefulfilled_requirements: Set[str] = {
            str(item)
            for item in (prefulfilled_requirements or ())
            if str(item) in self.requirements
        }
        self.completed: Set[str] = set(self.prefulfilled_requirements)
        self.page_milestones: List[Dict[str, Any]] = []
        self.evidence: List[Dict[str, Any]] = []
        self.last_url = ""
        self.search_input_pending = False
        self.search_results_url = ""
        self.search_baseline: Optional[SearchBaseline] = None
        self.search_submission = SearchSubmissionState()
        self.detail_url = ""
        self.detail_business_target = ""
        self.detail_target_labels: List[str] = []
        self.detail_baseline: Optional[DetailPageBaseline] = None
        self.next_target_source_url = ""
        self.detail_target_lock = DetailTargetLock()
        self.detail_write_gate = DetailWriteGate()
        self.deferred_effects: Dict[str, Dict[str, Any]] = {}
        self.reconciled_deferred_effects: Set[str] = set()
        self.rejected_effects: List[Dict[str, str]] = []
        self.mission = GeneralMissionLedger.compile(
            safety_intent_text,
            requires_search=(
                "search" in self.requirements
                and "search" not in self.prefulfilled_requirements
            ),
            requires_commit="commit" in self.requirements,
        )

    @staticmethod
    def _compile_requirements(goal: str) -> Set[str]:
        return compile_general_requirements(goal)

    def after_step(
        self,
        decision: Decision,
        result: Any,
        ok: bool,
        current_obs: Observation,
        error: Optional[str] = None,
    ) -> None:
        transition = BrowserActionTransition.capture(
            decision,
            before=current_obs,
            after=current_obs,
        )
        self.after_transition(transition, result, ok, error=error)

    def after_transition(
        self,
        transition: BrowserActionTransition,
        result: Any,
        ok: bool,
        error: Optional[str] = None,
    ) -> None:
        # A dispatched action may outlive the local-agent observation timeout.
        # Preserve its pre-action intent now; the executor's forced fresh
        # observe will confirm any resulting page milestone on the next turn.
        effective_after = (
            transition.after
            if transition.after.fresh
            else transition.before
        )
        self._apply_step(
            transition.decision,
            result,
            ok,
            effective_after,
            before_obs=transition.before,
            action_target=transition.target,
            error=error,
        )
        if transition.after.fresh:
            self.reconciled_deferred_effects.update(self.deferred_effects)

    def _apply_step(
        self,
        decision: Decision,
        result: Any,
        ok: bool,
        current_obs: Observation,
        *,
        before_obs: Observation,
        action_target: ActionTargetSnapshot,
        error: Optional[str] = None,
    ) -> None:
        self.step_counter += 1
        tool = str(decision.tool or "")
        args = dict(decision.args or {})
        search_target = bool(
            tool in {"browser_fill", "browser_type_at"}
            and self.mission.is_search_target(decision, before_obs)
        )
        if (
            ok
            and search_target
            and "search" in self.requirements
            and "search" not in self.completed
        ):
            target = _decision_target(decision, before_obs)
            begin_search_submission(
                self.search_submission,
                query=str(args.get("value") or ""),
                field_target=target,
            )
        if not ok:
            record_search_submission_transition(
                self.search_submission,
                decision,
                current_obs,
                search_confirmed=False,
            )
            self.detail_target_lock.finish_action(detail_confirmed=False)
            return

        previous_url = self.last_url
        current_url = str(current_obs.url or "")
        known_page_urls = {
            str(item.get("url") or "")
            for item in self.page_milestones
            if item.get("url")
        }
        had_search = "search" in self.completed

        if current_url:
            self._record_page(current_obs, reason=tool)
            self.last_url = current_url
        if self._recordable_url(current_url):
            self.completed.add("navigate")
        if search_target:
            self.search_input_pending = "search" in self.requirements and "search" not in self.completed
            if self.search_input_pending:
                self.search_baseline = capture_search_baseline(
                    str(args.get("value") or ""),
                    before_obs,
                )
        search_confirmed = self.search_input_pending and search_submission_confirmed(
            self.search_baseline, current_obs, result,
        )
        observed_search: Optional[ObservedSearchResult] = None
        if (
            "search" in self.requirements
            and "search" not in self.completed
            and not search_confirmed
        ):
            observed_search = infer_observed_search_result(decision, current_obs)
            search_confirmed = observed_search is not None
        if search_confirmed:
            self.completed.add("search")
            self.search_results_url = current_url
            self.detail_baseline = capture_detail_baseline(current_obs)
            self.search_input_pending = False

        candidate_outcome = classify_detail_candidate_return(
            target=self.detail_target_lock.target,
            detail_confirmed=self.detail_target_lock.detail_confirmed,
            decision=decision,
            before=before_obs,
            after=current_obs,
            requirements=self.requirements,
            completed=self.completed,
        )
        if candidate_outcome.exclude:
            rejected_target = self.detail_target_lock.exclude_current(
                reason=candidate_outcome.reason,
            )
            self.completed.discard("open_result")
            if rejected_target is not None:
                rejected_detail_url = str(self.detail_url or "").strip()
                self.evidence = [
                    item for item in self.evidence
                    if str(item.get("url") or "").strip() != rejected_detail_url
                ]
                if "read" in self.requirements and not self.evidence:
                    self.completed.discard("read")
            self.detail_url = ""
            self.detail_business_target = ""
            self.detail_target_labels = []
            self.detail_write_gate.clear()
            self.mission.reject_current_detail()
        record_search_submission_transition(
            self.search_submission,
            decision,
            current_obs,
            search_confirmed=bool(search_confirmed),
        )

        detail_confirmed = bool(
            "open_result" in self.requirements
            and (had_search or "search" not in self.requirements)
            and detail_page_observed(
                self.detail_baseline,
                current_obs,
                target=self.detail_target_lock.target,
                known_page_urls=known_page_urls,
            )
        )
        if (
            not detail_confirmed
            and "open_result" in self.requirements
            and "commit" in self.requirements
            and (had_search or "search" not in self.requirements)
        ):
            inline_editor = inline_target_editor_observed(
                decision,
                before_obs,
                current_obs,
                target=self.detail_target_lock.target,
            )
            detail_confirmed = inline_editor.confirmed
        if detail_confirmed:
            self.completed.add("open_result")
            self.detail_url = current_url
            locked_target = self.detail_target_lock.target
            if locked_target is not None:
                self.detail_target_labels = list(locked_target.labels)
                self.detail_business_target = (
                    locked_target.content_context_id
                    or locked_target.target_url
                    or "|".join(locked_target.labels)
                    or locked_target.scope_id
                )
        self.detail_write_gate.observe(
            current_url=current_url,
            detail_confirmed=bool(detail_confirmed),
        )

        content_text = observed_content_text(
            decision,
            result,
            current_obs,
            requirements=self.requirements,
            completed=self.completed,
        )
        if content_text:
            self.completed.add("read")
            self._record_evidence(current_obs, content_text)

        if tool == "browser_back":
            self.completed.add("return")
        elif self.detail_url and self.search_results_url and current_url == self.search_results_url:
            self.completed.add("return")

        self.mission.after_step(
            decision,
            current_obs,
            previous_url=previous_url,
            search_target=search_target,
            search_confirmed=bool(search_confirmed),
            search_query=observed_search.query if observed_search is not None else "",
            detail_confirmed=bool(detail_confirmed),
        )
        if tool in {"browser_click", "browser_click_at", "browser_navigate", "browser_tab_new"}:
            self.detail_target_lock.finish_action(
                detail_confirmed=bool(detail_confirmed),
                detail_url=current_url,
                retain_confirmed=self._retain_detail_candidate(current_url),
            )
        elif tool in {"browser_observe", "browser_wait_for"}:
            self.detail_target_lock.finish_observation(
                detail_confirmed=bool(detail_confirmed),
                detail_url=current_url,
                retain_confirmed=self._retain_detail_candidate(current_url),
            )
        if not self._detail_candidate_follow_up_pending():
            self.detail_target_lock.clear()
            self.detail_write_gate.clear()
        self._reconcile_deferred_effects()
        if self.mission.complete and "commit" in self.requirements:
            self.completed.add("commit")
            self.next_target_source_url = ""
            self.detail_target_lock.clear()
            self.detail_write_gate.clear()

        remaining = self._remaining_requirements()
        self.phase = f"awaiting_{remaining[0]}" if remaining else "ready_to_finish"

    def build_state_ledger(
        self, current_obs: Optional[Observation] = None,
    ) -> Optional[Dict[str, Any]]:
        if current_obs is not None and current_obs.url:
            self._record_page(current_obs, reason="current_observation")
            self.last_url = str(current_obs.url or self.last_url)
            if self._recordable_url(current_obs.url):
                self.completed.add("navigate")
            self._reconcile_search_observation(current_obs)

        remaining = self._remaining_requirements()
        self.phase = f"awaiting_{remaining[0]}" if remaining else "ready_to_finish"
        completed_signals = [
            (
                f"upstream_satisfied: {_SIGNAL_LABELS[name]}"
                if name in self.prefulfilled_requirements
                else _SIGNAL_LABELS[name]
            )
            for name in self._ordered(self.completed)
        ]
        for page in self.page_milestones:
            completed_signals.append(
                f"page_seen: {page.get('title') or '(untitled)'} | {page.get('url') or ''}"
            )
        for item in self.evidence:
            completed_signals.append(
                f"content_evidence: {item.get('title') or '(untitled)'} | "
                f"{item.get('url') or ''} | {item.get('text') or ''}"
            )

        return {
            "phase": f"general_{self.phase}",
            "phase_goal": (
                f"完成并验证：{_SIGNAL_LABELS[remaining[0]]}"
                if remaining and str(self.lang).startswith("zh")
                else f"complete and verify: {_SIGNAL_LABELS[remaining[0]]}"
                if remaining
                else "目标证据已收集，可以整理结果并 browser_done"
                if str(self.lang).startswith("zh")
                else "required evidence is collected; return results with browser_done"
            ),
            "completed_signals": completed_signals,
            "remaining_signals": [_SIGNAL_LABELS[name] for name in remaining],
            "budget": {
                "step_counter": self.step_counter,
                "unique_pages": len(self.page_milestones),
                "evidence_items": len(self.evidence),
            },
            "mission": self.mission.as_dict(),
            "search_submission": self.search_submission.as_dict(),
            "detail_target_lock": self.detail_target_lock.as_dict(),
            "detail_write_gate": self.detail_write_gate.as_dict(),
            "next_target_source_url": self.next_target_source_url,
            "deferred_effect_keys": sorted(self.deferred_effects),
            "rejected_effects": list(self.rejected_effects),
            "pending_confirmed_effects": self._pending_confirmed_effect_count(),
            "action_constraints": self.detail_target_lock.excluded_constraints() + (
                [
                    "已有足够数量的业务操作确认成功但尚待补齐页面证据；"
                    "禁止执行新的提交、发布、发送或保存，只能观察和核验现有结果。"
                    if str(self.lang).startswith("zh")
                    else
                    "Enough business operations are already confirmed and await prerequisite evidence; "
                    "do not submit another mutation, only observe and verify the existing result."
                ]
                if self._pending_effect_quota_reached() else []
            ) + (
                [
                    "用户要求停在预览或草稿状态；可以打开创作入口、填写内容和上传文件，"
                    "但禁止点击最终发布、提交、发送、保存或创建按钮。"
                    if str(self.lang).startswith("zh")
                    else
                    "The user requested a preview/draft stop. Opening the editor, filling content, "
                    "and uploading files are allowed, but the final commit control is forbidden."
                ]
                if self.stop_before_final_commit else []
            ),
            "notes": [
                "页面里程碑是跨短期历史保存的事实；不要重复打开已经记录的页面。"
                if str(self.lang).startswith("zh")
                else "Page milestones survive short history; do not reopen pages already recorded."
            ],
        }

    def ready_to_done(self) -> bool:
        return not self._remaining_requirements()

    def interaction_purpose(
        self,
        decision: Decision,
        current_obs: Observation,
    ) -> str:
        tool = str(decision.tool or "")
        key = str((decision.args or {}).get("key") or "").strip().casefold()
        if (
            self.search_submission.active
            and tool == "browser_press"
            and key in {"enter", "return"}
        ):
            return "search"
        return ""

    def business_target_hint(self, current_obs: Observation) -> str:
        return str(self.detail_business_target or self.detail_url or "")

    def result_evidence(self, current_obs: Observation) -> Dict[str, Any]:
        mission = self.mission.as_dict()
        cycles = list(mission.get("search_cycles") or [])
        current_cycle = cycles[-1] if cycles else {}
        query = str(
            current_cycle.get("query")
            or mission.get("current_query")
            or ""
        ).strip()
        target_url = str(
            self.detail_url
            or current_cycle.get("detail_url")
            or current_obs.url
            or ""
        ).strip()
        target_title = next(
            (
                str(label).strip()
                for label in self.detail_target_labels
                if str(label).strip()
            ),
            "",
        )
        if not target_title and target_url:
            target_title = next(
                (
                    str(item.get("title") or "").strip()
                    for item in reversed(self.page_milestones)
                    if str(item.get("url") or "").strip() == target_url
                    and str(item.get("title") or "").strip()
                ),
                "",
            )
        out: Dict[str, Any] = {}
        if query:
            out["search_query"] = query
        if target_url:
            out["target_url"] = target_url
        if target_title:
            out["target_title"] = target_title
        if self.evidence:
            latest = self.evidence[-1]
            out["observed_content"] = {
                "title": str(latest.get("title") or "")[:300],
                "url": str(latest.get("url") or ""),
                "text": str(latest.get("text") or "")[:1200],
            }
        return out

    def validate_action(self, decision: Decision, current_obs: Observation):
        target = _decision_target(decision, current_obs)
        search_interaction = bool(
            self.mission.is_search_target(decision, current_obs)
            or self.interaction_purpose(decision, current_obs) == "search"
        )
        blocker = self.operation_contract.read_only_action_blocker(
            tool=decision.tool,
            target={**dict(target or {}), "key": str((decision.args or {}).get("key") or "")},
            search_interaction=search_interaction,
            final_commit_control=bool(target and is_final_commit_control(target)),
        )
        if blocker:
            return ("reject", decision, blocker)
        if self.stop_before_final_commit and decision.tool in {
            "browser_click", "browser_click_at", "browser_press",
        }:
            if target and is_final_commit_control(target):
                return (
                    "reject",
                    decision,
                    "用户要求停在预览或草稿状态，不能执行最终发布、提交、发送、保存或创建。",
                )
        detail_blocker = self.detail_write_gate.blocker(decision, current_obs)
        if detail_blocker:
            return ("reject", decision, detail_blocker)
        if (
            self._pending_effect_quota_reached()
            and decision.tool in {"browser_fill", "browser_type_at"}
            and self.mission.is_search_target(decision, current_obs)
        ):
            return (
                "rewrite",
                Decision(
                    tool="browser_observe",
                    args={},
                    rationale="confirmed business effect awaits mission evidence; observe instead of starting another search",
                ),
                "已有业务操作成功，正在补齐任务证据，不再开始新的搜索。",
            )
        verdict, hint = self.mission.validate(decision, current_obs)
        if verdict == "allow" and (
            "open_result" in self.requirements
            and "open_result" not in self.completed
            and ("search" not in self.requirements or "search" in self.completed)
        ):
            candidate = capture_detail_target(decision, current_obs)
            if candidate is not None:
                if self.detail_baseline is None:
                    self.detail_baseline = capture_detail_baseline(current_obs)
                if not self.detail_target_lock.prepare(candidate):
                    replacement = self.detail_target_lock.replacement(current_obs)
                    if replacement is not None:
                        replacement.args["domain"] = str((decision.args or {}).get("domain") or "")
                        return (
                            "rewrite",
                            replacement,
                            "当前详情目标尚未验证，已重新定位并继续处理同一目标。",
                        )
                    return (
                        "reject",
                        decision,
                        "当前详情目标尚未验证；请先重新观察或完成该目标，再选择其他条目。",
                    )
                self.detail_write_gate.arm(candidate)
        return (verdict, decision, hint)

    def suggest_next_action(self, current_obs: Observation) -> Optional[Decision]:
        search_decision = suggest_search_submission_action(
            self.search_submission,
            current_obs,
        )
        if search_decision is not None:
            return Decision(
                tool=search_decision.tool,
                args={
                    **dict(search_decision.args or {}),
                    "domain": self._domain(current_obs.url),
                },
                rationale=search_decision.rationale,
            )
        if (
            self.next_target_source_url
            and "open_result" in self.requirements
            and "open_result" not in self.completed
            and not same_detail_resource(
                self.next_target_source_url,
                str(current_obs.url or ""),
            )
        ):
            return Decision(
                tool="browser_navigate",
                args={
                    "url": self.next_target_source_url,
                    "domain": self._domain(self.next_target_source_url),
                },
                rationale="return to the retained result list to select the next distinct business object",
            )
        recovery = self.detail_write_gate.suggest_recovery(current_obs)
        if recovery is not None:
            return Decision(
                tool=recovery.tool,
                args={
                    **dict(recovery.args or {}),
                    "domain": self._domain(current_obs.url),
                },
                rationale=recovery.rationale,
            )
        decision = self.detail_target_lock.suggest(current_obs)
        if decision is not None:
            return Decision(
                tool=decision.tool,
                args={**dict(decision.args or {}), "domain": self._domain(current_obs.url)},
                rationale=decision.rationale,
            )
        if self._pending_effect_quota_reached() and {
            "open_result", "read",
        }.intersection(self._remaining_requirements()):
            return Decision(
                tool="browser_observe",
                args={},
                rationale="collect missing mission evidence for an already confirmed business action",
            )
        return None

    def business_effect_blocker(self, receipt_contract: Any) -> str:
        if not self._pending_effect_quota_reached():
            return ""
        return (
            "已有足够数量的业务操作确认成功但尚待补齐任务证据；"
            "已禁止新的提交，接下来只能观察并核验现有结果。"
            if str(self.lang).startswith("zh")
            else
            "Enough business operations are already confirmed and await mission evidence; "
            "another commit is blocked while the existing result is verified."
        )

    def after_effect(self, receipt: EffectReceipt, current_obs: Observation) -> None:
        binding = bind_effect_to_commit_goal(
            receipt,
            requirements=self.requirements,
            completed=self.completed,
        )
        accepted = self.mission.record_effect(receipt, eligible=binding.accepted)
        if binding.deferred:
            self.deferred_effects[receipt.contract_key] = receipt.model_dump(mode="json")
            self.reconciled_deferred_effects.discard(receipt.contract_key)
        else:
            self.deferred_effects.pop(receipt.contract_key, None)
            self.reconciled_deferred_effects.discard(receipt.contract_key)
        if not accepted and receipt.status == "confirmed_success" and not binding.deferred:
            self.rejected_effects.append({
                "contract_key": str(receipt.contract_key or ""),
                "reason": binding.reason,
            })
            self.rejected_effects = self.rejected_effects[-8:]
        if accepted and not self.mission.complete:
            self._prepare_next_business_target()
        if self.mission.complete and "commit" in self.requirements:
            self.completed.add("commit")
            self.next_target_source_url = ""
            self.detail_target_lock.clear()
            self.detail_write_gate.clear()

    def _reconcile_deferred_effects(self) -> None:
        for contract_key, payload in list(self.deferred_effects.items()):
            receipt = EffectReceipt(**payload)
            binding = bind_effect_to_commit_goal(
                receipt,
                requirements=self.requirements,
                completed=self.completed,
            )
            if binding.accepted:
                accepted = self.mission.record_effect(receipt, eligible=True)
                self.deferred_effects.pop(contract_key, None)
                self.reconciled_deferred_effects.discard(contract_key)
                if accepted and not self.mission.complete:
                    self._prepare_next_business_target()
            elif not binding.deferred:
                self.deferred_effects.pop(contract_key, None)
                self.reconciled_deferred_effects.discard(contract_key)
        if self.mission.complete and "commit" in self.requirements:
            self.completed.add("commit")
            self.next_target_source_url = ""
            self.detail_target_lock.clear()
            self.detail_write_gate.clear()

    def _pending_confirmed_effect_count(self) -> int:
        identities = {
            str(
                payload.get("business_action_id")
                or payload.get("contract_key")
                or contract_key
            ).strip()
            for contract_key, payload in self.deferred_effects.items()
            if isinstance(payload, dict)
            and str(payload.get("status") or "") == "confirmed_success"
        }
        identities.discard("")
        return len(identities)

    def _prepare_next_business_target(self) -> None:
        """Start a fresh object cycle while preserving page/search progress."""
        locked_target = self.detail_target_lock.target
        current_cycle = self.mission.current_cycle
        self.next_target_source_url = str(
            (locked_target.source_url if locked_target is not None else "")
            or self.search_results_url
            or (current_cycle.result_url if current_cycle is not None else "")
            or ""
        ).strip()
        self.mission.prepare_next_target()
        for requirement in ("open_result", "read", "commit"):
            if requirement in self.requirements:
                self.completed.discard(requirement)
        self.detail_url = ""
        self.detail_business_target = ""
        self.detail_target_labels = []
        self.detail_baseline = None
        self.detail_target_lock.clear()
        self.detail_write_gate.clear()

    def _pending_effect_quota_reached(self) -> bool:
        return (
            self.mission.enabled
            and self.mission.confirmed_effects + self._pending_confirmed_effect_count()
            >= self.mission.minimum_effects
            and self._pending_confirmed_effect_count() > 0
        )

    def effect_completes_task(self, receipt: EffectReceipt) -> bool:
        # A receipt proves one operation. The mission ledger decides whether
        # enough distinct operations and page milestones satisfy the task.
        self._reconcile_deferred_effects()
        return (
            receipt.status == "confirmed_success"
            and (
                receipt.business_action_id or receipt.contract_key
            ) in self.mission.confirmed_contract_keys
            and self.ready_to_done()
        )

    def effect_task_outcome(self, receipt: EffectReceipt) -> EffectTaskOutcome:
        if self.effect_completes_task(receipt):
            return EffectTaskOutcome.complete()
        contract_key = str(receipt.contract_key or "").strip()
        if (
            receipt.status == "confirmed_success"
            and contract_key in self.deferred_effects
            and contract_key in self.reconciled_deferred_effects
            and self._pending_effect_quota_reached()
        ):
            return EffectTaskOutcome(
                status="partial_success",
                reason=(
                    "business effect was confirmed, but prerequisite mission "
                    "evidence remained incomplete after a fresh reconciliation"
                ),
                verified_requirements=tuple(sorted(self.completed)),
                missing_requirements=tuple(self._remaining_requirements()),
            )
        return EffectTaskOutcome.continue_()

    def done_blocked_hint(self, current_obs: Observation) -> StepRecord:
        remaining = self._remaining_requirements()
        labels = [_SIGNAL_LABELS[name] for name in remaining]
        reason = (
            f"通用浏览任务还有未验证目标：{', '.join(labels)}"
            if str(self.lang).startswith("zh")
            else f"General browser task still has unverified goals: {', '.join(labels)}"
        )
        return StepRecord(
            observation=current_obs,
            decision=Decision(tool="__general_done_blocked__", args={}, rationale="generic ledger completion gate"),
            ok=False,
            error=reason,
            result_digest=reason,
        )

    def finalize(
        self,
        summary: str,
        data: Dict[str, Any],
        *,
        partial: bool = False,
        partial_reason: str = "",
    ) -> tuple[str, Dict[str, Any]]:
        out = dict(data or {})
        out.setdefault("browser_task_ledger", {
            "phase": self.phase,
            "completed": self._ordered(self.completed),
            "remaining": self._remaining_requirements(),
            "pages": list(self.page_milestones),
            "evidence": list(self.evidence),
        })
        return summary, out

    def _record_page(self, obs: Observation, *, reason: str) -> None:
        url = str(obs.url or "").strip()
        if not self._recordable_url(url):
            return
        title = str(obs.title or "").strip()[:300]
        for page in self.page_milestones:
            if page.get("url") == url:
                page["title"] = title or page.get("title", "")
                page["last_step"] = self.step_counter
                page["last_reason"] = reason
                return
        self.page_milestones.append({
            "url": url,
            "title": title,
            "first_step": self.step_counter,
            "last_step": self.step_counter,
            "last_reason": reason,
        })
        if len(self.page_milestones) > self.MAX_PAGE_MILESTONES:
            self.page_milestones = [self.page_milestones[0], *self.page_milestones[-(self.MAX_PAGE_MILESTONES - 1):]]

    def _reconcile_search_observation(self, observation: Observation) -> None:
        if "search" not in self.requirements or "search" in self.completed:
            return
        expected_query = str(
            self.search_submission.query
            or (self.search_baseline.query if self.search_baseline else "")
            or self.mission.pending_query
            or ""
        ).strip()
        observed = infer_search_result_from_observation(
            observation,
            expected_query=expected_query,
        )
        if observed is None:
            return
        self.completed.add("search")
        self.search_results_url = observed.url
        self.detail_baseline = capture_detail_baseline(observation)
        self.search_input_pending = False
        self.mission.after_step(
            Decision(tool="browser_observe", args={}),
            observation,
            previous_url=self.last_url,
            search_confirmed=True,
            search_query=observed.query,
        )
        record_search_submission_transition(
            self.search_submission,
            Decision(tool="browser_observe", args={}),
            observation,
            search_confirmed=True,
        )

    def _record_evidence(self, obs: Observation, text: str) -> None:
        item = {
            "url": str(obs.url or ""),
            "title": str(obs.title or "")[:300],
            "text": " ".join(str(text).split())[:self.MAX_EVIDENCE_CHARS],
            "step": self.step_counter,
        }
        fingerprint = (item["url"], item["text"][:240])
        if any((entry.get("url"), str(entry.get("text") or "")[:240]) == fingerprint for entry in self.evidence):
            return
        self.evidence.append(item)
        if len(self.evidence) > self.MAX_EVIDENCE_ITEMS:
            self.evidence = self.evidence[-self.MAX_EVIDENCE_ITEMS:]

    def _remaining_requirements(self) -> List[str]:
        return [name for name in self._ordered(self.requirements) if name not in self.completed]

    def _detail_candidate_follow_up_pending(self) -> bool:
        return any(
            name in self.requirements and name not in self.completed
            for name in ("read", "commit")
        )

    def _retain_detail_candidate(self, current_url: str) -> bool:
        target = self.detail_target_lock.target
        return bool(
            target is not None
            and self._detail_candidate_follow_up_pending()
            and not same_detail_resource(target.source_url, current_url)
        )

    @staticmethod
    def _ordered(values: Set[str]) -> List[str]:
        order = ("navigate", "search", "open_result", "read", "commit", "return")
        return [name for name in order if name in values]

    @staticmethod
    def _recordable_url(url: str) -> bool:
        return str(url or "").startswith(("http://", "https://"))

    @staticmethod
    def _domain(url: str) -> str:
        try:
            return str(urlparse(str(url or "")).hostname or "")
        except ValueError:
            return ""

    def checkpoint_dataclasses(self) -> Dict[str, type]:
        return {
            "GeneralMissionLedger": GeneralMissionLedger,
            "SearchCycle": SearchCycle,
            "SearchBaseline": SearchBaseline,
            "SearchSubmissionState": SearchSubmissionState,
            "DetailPageBaseline": DetailPageBaseline,
            "DetailTargetFingerprint": DetailTargetFingerprint,
            "DetailTargetLock": DetailTargetLock,
            "DetailWriteGate": DetailWriteGate,
        }


def _decision_target(
    decision: Decision,
    observation: Observation,
) -> Dict[str, Any]:
    ref = str((decision.args or {}).get("ref") or "").strip()
    elements = [
        element
        for element in list(observation.elements or [])
        if isinstance(element, dict)
    ]
    if ref:
        for element in elements:
            if str(element.get("ref") or "") == ref:
                return element
    if decision.tool == "browser_press":
        for element in elements:
            if element.get("focused"):
                return element
    if decision.tool == "browser_click_at":
        try:
            x = float((decision.args or {}).get("x"))
            y = float((decision.args or {}).get("y"))
        except (TypeError, ValueError):
            return {}
        for element in elements:
            try:
                center_x = float(element.get("x"))
                center_y = float(element.get("y"))
                width = float(element.get("width") or 0)
                height = float(element.get("height") or 0)
            except (TypeError, ValueError):
                continue
            if (
                abs(x - center_x) <= width / 2
                and abs(y - center_y) <= height / 2
            ):
                return element
    return {}
