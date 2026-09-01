"""Field input resolution and deterministic commit handoff for business forms.

This driver is deliberately a decorator around the existing exploration
driver.  It only acts when the current page exposes a business form and a
field can be bound to an explicit user/upstream input (or to a constrained
model decision). Navigation and ambiguous actions remain owned by the browser
Agent Loop; a unique submit control in the active form can be committed
directly after a fresh observation.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord

from app.enterprise_capabilities.browser.engine.form_input import (
    BrowserInputContext,
    CommitBindingLedger,
    FieldBinding,
    FieldDescriptor,
    FormInputModelResolver,
    MediaActivationResolution,
    augment_media_handoff_ledger,
    discover_fields,
    guard_dirty_form_commit,
    guard_media_dispatch,
    is_commit_control_for_fields,
    is_semantic_commit_control,
    normalize_media_upload_decision,
    normalize_media_paste_decision,
    normalize_authoritative_fill,
    page_signature,
    prefers_media_paste,
    promote_media_control_decision,
    pending_media_candidates,
    ready_business_form_scopes,
    replan_rejected_commit,
    resolve_deterministic,
    resolve_fallback_form_mutation,
    resolve_form_commit,
    resolve_media_activation,
    resolve_requested_media_paste,
)
from app.enterprise_capabilities.browser.engine.form_input.stage import FormInteractionStage
from app.enterprise_capabilities.browser.engine.form_input.field_phase import (
    augment_pending_field_ledger,
    is_direct_media_mutation,
    pending_input_fields,
    skip_resolves_input_phase,
)
from app.enterprise_capabilities.browser.engine.form_input.media_recovery import (
    replacement_invalidates_editor_media,
)
from app.enterprise_capabilities.browser.engine.form_input.media_sequence import MediaInsertionSequence
from app.enterprise_capabilities.browser.engine.form_input.transaction_identity import (
    FormResourceIdentityTracker,
    FormTransactionMemory,
    resolve_form_resource_identity,
)
from app.enterprise_capabilities.browser.engine.operation_intent import stops_before_final_commit
from app.enterprise_capabilities.browser.engine.form_human_assistance import (
    FORM_FILL_CATEGORY,
    build_commit_assistance_decision,
    resume_contract,
    resume_outcome,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.bindings import resolve_cached_bindings
from app.enterprise_capabilities.browser.engine.workflow_cache.contracts import CachedFieldBinding

from .base import BrowserDriver, notify_step_completed


_WRITE_CAPABILITIES = {
    "browser.submit",
    "browser.modify",
    "browser.publish",
    "browser.publish_or_submit",
    "browser.file_transfer",
    "integration.send_email",
}
_DRIVER_TAG = "[form_input_driver]"
logger = logging.getLogger(__name__)


class FormInputDriver(BrowserDriver):
    """Resolve visible form fields before delegating other work.

    The driver never invents DOM refs. Each turn it rediscovers the live field
    inventory and binds at most one field. After its own fields are complete,
    it submits only a unique, enabled semantic commit control in that scope.
    """

    def __init__(
        self,
        *,
        fallback: BrowserDriver,
        input_context: BrowserInputContext,
        capability_id: str,
        lang: str = "zh",
        model_resolver: Optional[FormInputModelResolver] = None,
        cached_binding_hints: Optional[Sequence[CachedFieldBinding]] = None,
    ) -> None:
        self._fallback = fallback
        self._input_context = input_context
        self._capability_id = str(capability_id or "")
        self._lang = lang
        self._model_resolver = model_resolver
        self._cached_binding_hints = list(cached_binding_hints or [])
        self._cached_field_keys: set[str] = set()
        self._cached_binding_used = False
        self._completed_keys: set[str] = set()
        self._completed_candidate_ids: set[str] = set()
        self._completed_editor_media_candidate_ids: set[str] = set()
        self._mutated_field_keys: set[str] = set()
        self._blocked_keys: set[str] = set()
        self._skipped_keys: set[str] = set()
        self._model_attempted_signatures: set[str] = set()
        self._bindings: Dict[str, FieldBinding] = {}
        self._last_owner = ""
        self._last_field_key = ""
        self._last_candidate_id = ""
        self._last_observation: Optional[Observation] = None
        self._commit_refreshed_scopes: set[str] = set()
        self._commit_attempts: set[str] = set()
        self._commit_unresolved_counts: Dict[str, int] = {}
        self._commit_bindings = CommitBindingLedger()
        self._resource_identity = FormResourceIdentityTracker()
        self._active_transaction_key = ""
        self._transaction_memories: Dict[str, FormTransactionMemory] = {}
        self._post_commit_transition_guard = False
        self._media_activation_attempts: set[str] = set()
        self._media_sequence = MediaInsertionSequence()
        self._stage = FormInteractionStage()

    @property
    def kind(self) -> str:
        return f"form_input+fallback:{self._fallback.kind}"

    @property
    def replayed_any(self) -> bool:
        return self._cached_binding_used or bool(getattr(self._fallback, "replayed_any", False))

    async def next_step(
        self,
        goal: str,
        history: List[StepRecord],
        observation: Observation,
        state_ledger: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        self._last_observation = observation
        if self._capability_id not in _WRITE_CAPABILITIES or _auth_blocks_input(observation):
            return await self._delegate(goal, history, observation, state_ledger)
        fields = discover_fields(observation)
        if self._media_sequence.refresh_required:
            self._last_owner = "media_refresh"
            return Decision(
                tool="browser_observe",
                args={},
                rationale=(
                    "[form_media_activation] refresh the editor after a completed "
                    "upload before binding the next pending file"
                ),
            )

        ready_scopes = ready_business_form_scopes(observation, fields) if fields else {}
        scope_id = self._stage.select_scope(observation, ready_scopes, history)
        if not scope_id:
            return await self._delegate(goal, history, observation, state_ledger)
        fields = ready_scopes[scope_id]
        self._activate_form_transaction(observation, fields)
        self._commit_bindings.observe(
            candidates=_commit_candidates(observation),
            fields=fields,
            mutated_field_keys=self._mutated_field_keys,
            page_url=observation.url,
        )
        if prefers_media_paste(self._input_context.original_request):
            fields = [
                field for field in fields
                if field.control_kind != "file"
            ]
            if not fields:
                return await self._delegate(
                    goal,
                    history,
                    observation,
                    state_ledger,
                )

        signature = page_signature(observation, fields)
        deterministic, unresolved = resolve_deterministic(fields, self._input_context)
        cached = resolve_cached_bindings(fields, self._input_context, self._cached_binding_hints)
        self._cached_field_keys.update(set(cached) - set(deterministic))
        self._bindings.update(cached)
        # Current-page deterministic evidence is authoritative when both paths bind.
        self._bindings.update(deterministic)
        unresolved = [field for field in unresolved if field.field_key not in self._bindings]

        if (
            unresolved
            and signature not in self._model_attempted_signatures
        ):
            self._model_attempted_signatures.add(signature)
            model_fields = self._model_fields(unresolved)
            if model_fields:
                resolver = self._model_resolver or FormInputModelResolver()
                model_bindings = await resolver.resolve(
                    fields=model_fields,
                    context=self._input_context,
                    lang=self._lang,
                    task_goal=goal,
                )
                for binding in model_bindings:
                    self._bindings.setdefault(binding.field_key, binding)

        field_by_key = {field.field_key: field for field in fields}
        for field in _ordered_fields(fields):
            if field.current_value.strip():
                self._completed_keys.add(field.field_key)
                continue
            if field.field_key in self._completed_keys or field.field_key in self._blocked_keys:
                continue
            binding = self._bindings.get(field.field_key)
            if binding is None:
                continue
            if binding.action == "skip":
                if skip_resolves_input_phase(
                    field,
                    context=self._input_context,
                    task_goal=goal,
                ):
                    self._skipped_keys.add(field.field_key)
                self._bindings.pop(field.field_key, None)
                continue
            decision = _binding_decision(field_by_key[field.field_key], binding, self._lang)
            if decision is None:
                self._blocked_keys.add(field.field_key)
                continue
            self._last_owner = "form"
            self._last_field_key = field.field_key
            self._last_candidate_id = binding.candidate_id
            if field.field_key in self._cached_field_keys:
                self._cached_binding_used = True
            self._commit_refreshed_scopes.discard(scope_id)
            return decision

        # Generated media is part of the same publish transaction as the
        # title/body. Never commit the form while an anchored asset is still
        # pending; the delegated path either uploads a uniquely resolved
        # control or constrains exploration to the current editor toolbar.
        pending_media = pending_media_candidates(
            self._input_context,
            self._completed_candidate_ids,
        )
        if pending_media:
            unresolved_inputs = pending_input_fields(
                fields,
                completed_keys=self._completed_keys,
                skipped_keys=self._skipped_keys,
            )
            return await self._delegate(
                goal,
                history,
                observation,
                state_ledger,
                allow_media=not unresolved_inputs,
                pending_fields=unresolved_inputs,
            )

        commit = (
            resolve_form_commit(
                observation,
                fields=fields,
                mutated_field_keys=self._mutated_field_keys,
                observation_is_fresh=scope_id in self._commit_refreshed_scopes,
                bound_action_keys=self._commit_bindings.bound_action_keys,
            )
            if not stops_before_final_commit(self._input_context.original_request)
            else None
        )
        if commit is not None and commit.decision is not None:
            if commit.kind == "refresh":
                self._commit_refreshed_scopes.add(scope_id)
                self._last_owner = "commit_refresh"
                logger.info(
                    "browser form commit refresh queued",
                    extra={
                        "event": "browser.form_commit_refresh_queued",
                        "scope_id": scope_id,
                        "candidate_count": len(commit.candidate_refs),
                    },
                )
                return commit.decision
            attempt_key = scope_id
            if attempt_key not in self._commit_attempts:
                self._commit_attempts.add(attempt_key)
                self._last_owner = "commit"
                logger.info(
                    "browser form commit resolved",
                    extra={
                        "event": "browser.form_commit_resolved",
                        "scope_id": scope_id,
                        "ref": commit.candidate_refs[0] if commit.candidate_refs else "",
                    },
                )
                return commit.decision

        if commit is not None and commit.kind in {"ambiguous", "none"} and commit.reason in {
            "multiple commit controls require planner selection",
            "commit controls remain disabled",
            "no semantic commit control in active form",
        }:
            # Missing controls do not get the resolver's normal refresh branch.
            # Give the page one fresh read, then one ordinary planner turn. Only
            # a still-identical unresolved state is handed to the user.
            unresolved_key = "\0".join((scope_id, commit.kind, commit.reason, *commit.candidate_refs))
            count = self._commit_unresolved_counts.get(unresolved_key, 0) + 1
            self._commit_unresolved_counts[unresolved_key] = count
            # Preserve the existing planner opportunity on the first
            # unresolved turn. It may know a multi-step submit flow that the
            # local semantic resolver intentionally does not guess.
            if count == 1:
                return await self._delegate(goal, history, observation, state_ledger)
            if scope_id not in self._commit_refreshed_scopes:
                self._commit_refreshed_scopes.add(scope_id)
                self._last_owner = "commit_refresh"
                return Decision(
                    tool="browser_observe",
                    args={},
                    rationale="[form_commit_resolver] refresh before escalating an unresolved commit",
                )
            if count >= 3:
                self._last_owner = "commit_assistance"
                return build_commit_assistance_decision(
                    reason=commit.reason,
                    candidate_refs=commit.candidate_refs,
                    lang=self._lang,
                )

        return await self._delegate(goal, history, observation, state_ledger)

    def on_step_completed(
        self,
        decision: Decision,
        ok: bool,
        observation_after: Observation,
        result: Any = None,
    ) -> None:
        self._stage.record_transition(
            decision=decision,
            ok=ok,
            before=self._last_observation,
            after=observation_after,
        )
        if self._last_owner == "fallback":
            notify_step_completed(self._fallback, decision, ok, observation_after, result)
            if ok and decision.tool in {"browser_click", "browser_click_at", "browser_navigate"}:
                self._post_commit_transition_guard = False
            before_fields = (
                discover_fields(self._last_observation)
                if self._last_observation is not None
                else []
            )
            handoff = resolve_fallback_form_mutation(
                decision=decision,
                before=self._last_observation,
                after=observation_after,
            ) if ok else None
            if handoff is not None:
                mutated_field = next((
                    field for field in before_fields
                    if field.field_key == handoff.field_key
                ), None)
                self._mutated_field_keys.add(handoff.field_key)
                self._completed_keys.add(handoff.field_key)
                self._bindings.pop(handoff.field_key, None)
                self._commit_refreshed_scopes.discard(handoff.scope_id)
                self._commit_attempts.discard(handoff.scope_id)
                logger.info(
                    "fallback form fill adopted by commit transaction",
                    extra={
                        "event": "browser.form_fallback_fill_adopted",
                        "field_key": handoff.field_key,
                        "scope_id": handoff.scope_id,
                    },
                )
                self._requeue_editor_media_after_replacement(
                    mutated_field,
                    decision,
                )
            self._last_owner = ""
            return
        if self._last_owner == "media_refresh":
            self._media_sequence.complete_refresh(ok)
            self._last_owner = ""
            return
        if self._last_owner == "field_gate":
            self._last_owner = ""
            return
        if self._last_owner == "commit_refresh":
            if ok:
                self._commit_refreshed_scopes.update(
                    field.scope_id
                    for field in discover_fields(observation_after)
                    if field.scope_id
                )
            self._last_owner = ""
            return
        if self._last_owner in {"commit", "commit_assistance"}:
            if self._last_owner == "commit" and ok:
                self._post_commit_transition_guard = True
            self._last_owner = ""
            return
        if self._last_owner == "media_activation":
            confirmed_ids = self._media_sequence.complete_insertion(
                decision=decision,
                ok=ok,
                observation_after=observation_after,
                completed_candidate_ids=self._completed_candidate_ids,
                context=self._input_context,
            )
            if (
                confirmed_ids
                and str((decision.args or {}).get("editor_ref") or "").strip()
            ):
                self._completed_editor_media_candidate_ids.update(confirmed_ids)
            self._last_owner = ""
            return
        if self._last_owner != "form":
            return
        field_key = self._last_field_key
        candidate_id = self._last_candidate_id
        self._last_owner = ""
        self._last_field_key = ""
        self._last_candidate_id = ""
        if not field_key:
            return
        if not ok:
            self._blocked_keys.add(field_key)
            return
        before_field = next((
            field for field in discover_fields(self._last_observation)
            if field.field_key == field_key
        ), None) if self._last_observation is not None else None
        self._mutated_field_keys.add(field_key)
        if candidate_id and decision.tool in {
            "browser_fill", "browser_select", "browser_upload_file",
        }:
            self._completed_candidate_ids.add(candidate_id)
        refreshed = {field.field_key: field for field in discover_fields(observation_after)}
        field = refreshed.get(field_key)
        if field is None or field.current_value.strip() or decision.tool == "browser_upload_file":
            self._completed_keys.add(field_key)
            self._bindings.pop(field_key, None)
        else:
            # The verified-fill layer may report success before a framework
            # commits its controlled input.  Hand this field to exploration
            # instead of repeatedly overwriting it.
            self._blocked_keys.add(field_key)
        self._requeue_editor_media_after_replacement(before_field, decision)

    def on_decision_rejected(
        self,
        decision: Decision,
        observation: Observation,
        *,
        category: str,
        reason: str,
    ) -> None:
        """Release observation-local state when a mutation never dispatched."""
        owner = self._last_owner
        field_key = self._last_field_key
        if owner == "fallback":
            self._fallback.on_decision_rejected(
                decision,
                observation,
                category=category,
                reason=reason,
            )
        elif owner == "form" and field_key:
            self._bindings.pop(field_key, None)
            if category == "cross_form_target":
                self._blocked_keys.add(field_key)
            else:
                self._blocked_keys.discard(field_key)
            # Re-resolve model-only fields after the mandatory fresh
            # observation. Deterministic bindings are rebuilt locally.
            self._model_attempted_signatures.clear()
        elif owner == "media_activation":
            self._media_sequence.reset()
            self._media_activation_attempts.clear()
        elif owner in {"commit", "commit_refresh"}:
            self._commit_attempts.clear()
            self._commit_refreshed_scopes.clear()
        self._last_owner = ""
        self._last_field_key = ""
        self._last_candidate_id = ""
        self._last_observation = observation

    def prepare_dispatch(
        self,
        decision: Decision,
        observation: Observation,
    ) -> Decision:
        self._last_observation = observation
        if (
            self._capability_id not in _WRITE_CAPABILITIES
            or _auth_blocks_input(observation)
        ):
            return decision
        fields = discover_fields(observation)
        decision = normalize_authoritative_fill(
            decision=decision,
            fields=fields,
            context=self._input_context,
        )
        commit_guard = guard_dirty_form_commit(
            decision=decision,
            observation=observation,
            fields=fields,
            mutated_field_keys=self._mutated_field_keys,
            bound_action_keys=self._commit_bindings.bound_action_keys,
        )
        if commit_guard.decision is not None:
            target = _element_by_ref(
                observation,
                str((decision.args or {}).get("ref") or "").strip(),
            )
            if target is not None:
                self._commit_bindings.reject(
                    target=target,
                    fields=fields,
                    reason=commit_guard.reason,
                    page_url=observation.url,
                )
            logger.info(
                "browser out-of-scope commit action guarded",
                extra={
                    "event": "browser.form_commit_dispatch_guarded",
                    "from_tool": decision.tool,
                    "from_ref": str((decision.args or {}).get("ref") or ""),
                    "reason": commit_guard.reason,
                },
            )
            self._last_owner = "commit_refresh"
            return commit_guard.decision
        guarded = guard_media_dispatch(
            decision=decision,
            observation=observation,
            context=self._input_context,
            completed_candidate_ids=self._completed_candidate_ids,
        )
        if guarded.decision is None:
            return decision
        logger.info(
            "browser final media dispatch guarded",
            extra={
                "event": "browser.media_dispatch_guarded",
                "from_tool": decision.tool,
                "to_tool": guarded.decision.tool,
                "from_ref": str((decision.args or {}).get("ref") or ""),
                "to_ref": str((guarded.decision.args or {}).get("ref") or ""),
            },
        )
        return self._adopt_media_resolution(guarded)

    def export_checkpoint_state(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "completed_field_keys": sorted(self._completed_keys),
            "completed_candidate_ids": sorted(self._completed_candidate_ids),
            "completed_editor_media_candidate_ids": sorted(
                self._completed_editor_media_candidate_ids
            ),
            "mutated_field_keys": sorted(self._mutated_field_keys),
            "blocked_field_keys": sorted(self._blocked_keys),
            "skipped_field_keys": sorted(self._skipped_keys),
            "interaction_stage": self._stage.export_state(),
            "commit_unresolved_counts": dict(self._commit_unresolved_counts),
            "form_resource_identity": self._resource_identity.export_state(),
            "fallback_state": self._fallback.export_checkpoint_state(),
        }

    def restore_checkpoint_state(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        self._completed_keys = _string_set(state.get("completed_field_keys"))
        self._completed_candidate_ids = _string_set(
            state.get("completed_candidate_ids")
        )
        self._completed_editor_media_candidate_ids = _string_set(
            state.get("completed_editor_media_candidate_ids")
        ) & self._completed_candidate_ids
        self._mutated_field_keys = _string_set(state.get("mutated_field_keys"))
        self._blocked_keys = _string_set(state.get("blocked_field_keys"))
        self._skipped_keys = _string_set(state.get("skipped_field_keys"))
        # Commit controls and scope refs are observation-local. Re-resolve
        # them from the live DOM after resume instead of checkpointing them.
        self._commit_refreshed_scopes.clear()
        self._commit_attempts.clear()
        self._commit_unresolved_counts = {
            str(key): max(0, int(value))
            for key, value in dict(state.get("commit_unresolved_counts") or {}).items()
        }
        self._commit_bindings.reset()
        self._resource_identity.restore_state(state.get("form_resource_identity"))
        self._active_transaction_key = (
            self._resource_identity.active.key
            if self._resource_identity.active is not None
            else ""
        )
        self._transaction_memories.clear()
        self._post_commit_transition_guard = False
        self._media_activation_attempts.clear()
        self._media_sequence.reset()
        # Bindings contain user/upstream text and are intentionally not
        # checkpointed.  Model-attempt markers are therefore process-local as
        # well: after a real resume the live page is rediscovered and unresolved
        # fields may be resolved again.
        self._model_attempted_signatures.clear()
        self._stage.restore_state(state.get("interaction_stage"))
        fallback_state = state.get("fallback_state")
        if isinstance(fallback_state, dict):
            self._fallback.restore_checkpoint_state(fallback_state)
        self._bindings.clear()
        self._last_owner = ""
        self._last_field_key = ""
        self._last_candidate_id = ""
        self._last_observation = None

    def _activate_form_transaction(
        self,
        observation: Observation,
        fields: Sequence[FieldDescriptor],
    ) -> None:
        transition = self._resource_identity.observe(
            resolve_form_resource_identity(observation, fields),
            allow_change=not self._post_commit_transition_guard,
        )
        next_key = transition.identity.key
        if not self._active_transaction_key:
            self._active_transaction_key = next_key
            return
        if transition.upgraded:
            self._active_transaction_key = next_key
            return
        if not transition.changed or next_key == self._active_transaction_key:
            return

        self._transaction_memories[self._active_transaction_key] = (
            self._capture_transaction_memory()
        )
        memory = self._transaction_memories.get(
            next_key,
            FormTransactionMemory(),
        )
        self._completed_keys = set(memory.completed_keys)
        self._mutated_field_keys = set(memory.mutated_field_keys)
        self._blocked_keys = set(memory.blocked_keys)
        self._skipped_keys = set(memory.skipped_keys)
        self._commit_attempts = set(memory.commit_attempts)
        self._commit_unresolved_counts = dict(memory.commit_unresolved_counts)
        self._model_attempted_signatures.clear()
        self._bindings.clear()
        self._commit_refreshed_scopes.clear()
        self._commit_bindings.reset()
        self._active_transaction_key = next_key
        logger.info(
            "browser form resource transaction changed",
            extra={
                "event": "browser.form_transaction_changed",
                "identity_source": transition.identity.source,
                "identity_evidence": transition.identity.evidence[:160],
            },
        )

    def _capture_transaction_memory(self) -> FormTransactionMemory:
        return FormTransactionMemory(
            completed_keys=set(self._completed_keys),
            mutated_field_keys=set(self._mutated_field_keys),
            blocked_keys=set(self._blocked_keys),
            skipped_keys=set(self._skipped_keys),
            commit_attempts=set(self._commit_attempts),
            commit_unresolved_counts=dict(self._commit_unresolved_counts),
        )

    def apply_resume_signal(
        self,
        signal: Dict[str, Any],
        observation: Optional[Observation] = None,
    ) -> None:
        if str(signal.get("type") or "") != "human_intervention_completed":
            return
        # The fresh observation is intentionally required.  It prevents a
        # checkpoint-era acknowledgement from being applied before the live
        # tab/page has been reconciled.
        if observation is not None and not observation.fresh:
            return
        requested = {
            str(item).strip()
            for item in list(signal.get("media_completed_candidate_ids") or [])
            if str(item).strip()
        }
        valid = {
            item.candidate_id
            for item in self._input_context.candidates
            if item.value_kind == "file"
        }
        completed = requested & valid
        if not completed:
            contract = resume_contract(signal)
            if (
                str(contract.get("kind") or "") == FORM_FILL_CATEGORY
                and resume_outcome(signal, expected_kind=FORM_FILL_CATEGORY) == "completed"
            ):
                # Do not mark a stale field ref as complete. next_step will
                # rediscover the live fields and adopt their actual values.
                self._blocked_keys.clear()
                self._model_attempted_signatures.clear()
            return
        self._completed_candidate_ids.update(completed)
        self._media_activation_attempts.clear()
        self._media_sequence.reset()
        logger.info(
            "browser manual media upload adopted",
            extra={
                "event": "browser.manual_media_upload_adopted",
                "candidate_ids": sorted(completed),
            },
        )

    def _requeue_editor_media_after_replacement(
        self,
        field: Optional[FieldDescriptor],
        decision: Decision,
    ) -> None:
        if (
            not self._completed_editor_media_candidate_ids
            or not replacement_invalidates_editor_media(field, decision)
        ):
            return
        requeued = set(self._completed_editor_media_candidate_ids)
        self._completed_candidate_ids.difference_update(requeued)
        self._completed_editor_media_candidate_ids.clear()
        self._media_activation_attempts.clear()
        self._media_sequence.reset()
        logger.info(
            "browser editor media requeued after body replacement",
            extra={
                "event": "browser.editor_media_requeued",
                "field_key": field.field_key if field is not None else "",
                "candidate_ids": sorted(requeued),
            },
        )

    async def _delegate(
        self,
        goal: str,
        history: List[StepRecord],
        observation: Observation,
        state_ledger: Optional[Dict[str, Any]],
        *,
        allow_media: bool = True,
        pending_fields: Sequence[FieldDescriptor] = (),
    ) -> Decision:
        paste_requested = prefers_media_paste(
            self._input_context.original_request,
        )
        if allow_media:
            requested_paste = resolve_requested_media_paste(
                observation=observation,
                context=self._input_context,
                completed_candidate_ids=self._completed_candidate_ids,
                attempted_keys=self._media_activation_attempts,
            )
            if requested_paste.decision is not None:
                return self._adopt_media_resolution(requested_paste)

        if allow_media and not paste_requested:
            activation = resolve_media_activation(
                observation=observation,
                context=self._input_context,
                completed_candidate_ids=self._completed_candidate_ids,
                attempted_keys=self._media_activation_attempts,
                preferred_target_hint=self._media_sequence.preferred_target_hint,
            )
            if activation.decision is not None:
                return self._adopt_media_resolution(activation)

        media_ledger = augment_media_handoff_ledger(
            observation=observation,
            context=self._input_context,
            completed_candidate_ids=self._completed_candidate_ids,
            state_ledger=self._commit_bindings.augment_planner_state(
                observation=observation,
                fields=discover_fields(observation),
                state_ledger=state_ledger,
            ),
        )
        if pending_fields:
            media_ledger = augment_pending_field_ledger(
                media_ledger,
                pending_fields,
            )
        decision = await self._fallback.next_step(
            goal, history, observation, state_ledger=media_ledger,
        )
        fields = discover_fields(observation)
        decision = await replan_rejected_commit(
            ledger=self._commit_bindings,
            planner=self._fallback,
            decision=decision,
            goal=goal,
            history=history,
            observation=observation,
            fields=fields,
            state_ledger=media_ledger,
        )
        if not allow_media and is_direct_media_mutation(decision):
            self._last_owner = "field_gate"
            return Decision(
                tool="browser_observe",
                args={},
                rationale=(
                    "[form_input_driver] unresolved text fields must be filled "
                    "or explicitly skipped before media insertion"
                ),
            )
        normalized_paste = normalize_media_paste_decision(
            decision=decision,
            observation=observation,
            context=self._input_context,
            completed_candidate_ids=self._completed_candidate_ids,
        )
        if allow_media and normalized_paste.decision is not None:
            logger.info(
                "browser model paste adopted by media transaction",
                extra={
                    "event": "browser.media_paste_adopted",
                    "ref": normalized_paste.candidate_refs[0]
                    if normalized_paste.candidate_refs else "",
                    "candidate_ids": sorted(normalized_paste.candidate_ids),
                },
            )
            return self._adopt_media_resolution(normalized_paste)
        if allow_media and paste_requested and decision.tool == "browser_upload_file":
            return Decision(
                tool="browser_observe",
                args={},
                rationale=(
                    "clipboard image insertion was requested; refresh the live "
                    "rich editor and use browser_paste_image"
                ),
            )
        if allow_media and not paste_requested:
            normalized_upload = normalize_media_upload_decision(
                decision=decision,
                observation=observation,
                context=self._input_context,
                completed_candidate_ids=self._completed_candidate_ids,
            )
            if normalized_upload.decision is not None:
                logger.info(
                    "browser model upload adopted by media transaction",
                    extra={
                        "event": "browser.media_upload_adopted",
                        "ref": normalized_upload.candidate_refs[0]
                        if normalized_upload.candidate_refs else "",
                        "candidate_ids": sorted(normalized_upload.candidate_ids),
                    },
                )
                return self._adopt_media_resolution(normalized_upload)
        promoted_media = promote_media_control_decision(
            decision=decision,
            observation=observation,
            context=self._input_context,
            completed_candidate_ids=self._completed_candidate_ids,
        )
        if not allow_media and promoted_media.decision is not None:
            self._last_owner = "field_gate"
            return Decision(
                tool="browser_observe",
                args={},
                rationale=(
                    "[form_input_driver] complete the current form text fields "
                    "before activating an upload control"
                ),
            )
        if allow_media and promoted_media.decision is not None:
            if paste_requested:
                return Decision(
                    tool="browser_observe",
                    args={},
                    rationale=(
                        "clipboard image insertion was requested; locate the live "
                        "rich editor and use browser_paste_image instead of the "
                        "upload control"
                    ),
                )
            logger.info(
                "browser media click promoted to upload",
                extra={
                    "event": "browser.media_click_promoted_to_upload",
                    "from_tool": decision.tool,
                    "ref": promoted_media.candidate_refs[0]
                    if promoted_media.candidate_refs else "",
                },
            )
            return self._adopt_media_resolution(promoted_media)
        if (
            media_ledger
            and media_ledger.get("pending_media_count")
            and _decision_targets_commit(
                decision,
                observation,
                fields=discover_fields(observation),
            )
        ):
            decision = Decision(
                tool="browser_observe",
                args={},
                rationale=(
                    "generated media is still pending; verify or upload it before "
                    "the final form commit"
                ),
            )
        if (
            decision.tool == "browser_done"
            and media_ledger
            and media_ledger.get("pending_media_count")
        ):
            decision = Decision(
                tool="browser_observe",
                args={},
                rationale="pending upstream media must be placed before this browser task can finish",
            )
        self._last_owner = "fallback"
        self._last_field_key = ""
        return decision

    def _adopt_media_resolution(
        self,
        resolution: MediaActivationResolution,
    ) -> Decision:
        """Bind rule/model media decisions to one attempt/result ledger."""
        assert resolution.decision is not None
        if resolution.attempt_key:
            self._media_activation_attempts.add(resolution.attempt_key)
        self._media_sequence.begin(
            resolution,
            self._last_observation,
        )
        self._last_owner = "media_activation"
        self._last_field_key = ""
        return resolution.decision

    def _model_fields(self, fields):
        has_file_input = any(
            candidate.value_kind == "file" for candidate in self._input_context.candidates
        )
        requests_file = bool(_FILE_INTENT_RE.search(self._input_context.original_request or ""))
        return [
            field for field in fields
            if not field.sensitive
            and (
                field.control_kind != "file"
                or has_file_input
                or requests_file
            )
        ]


def _binding_decision(field, binding: FieldBinding, lang: str) -> Optional[Decision]:
    rationale = f"{_DRIVER_TAG} {binding.rationale}".strip()
    if binding.action == "fill":
        value = str(binding.value or "")
        args = {"ref": field.ref, "value": value}
        content_editable_mode = str(
            field.raw.get("contentEditableMode")
            or field.raw.get("content_editable_mode")
            or ""
        ).strip().lower()
        if (
            field.control_kind == "rich_text"
            and binding.rich_html
            and content_editable_mode != "plaintext-only"
        ):
            args["value"] = str(binding.plain_text or value)
            args["rich_html"] = binding.rich_html
        return Decision(
            tool="browser_fill",
            args=args,
            rationale=rationale,
        )
    if binding.action == "select":
        return Decision(
            tool="browser_select",
            args={"ref": field.ref, "value": str(binding.value or "")},
            rationale=rationale,
        )
    if binding.action == "upload":
        sources = [str(item) for item in list(binding.value or []) if str(item).strip()]
        if sources:
            return Decision(
                tool="browser_upload_file",
                args={"ref": field.ref, "sources": sources},
                rationale=rationale,
            )
        return None
    return None


def _element_by_ref(
    observation: Observation,
    ref: str,
) -> Optional[Dict[str, Any]]:
    if not ref:
        return None
    return next((
        item for item in observation.elements
        if isinstance(item, dict)
        and str(item.get("ref") or "").strip() == ref
    ), None)


def _ordered_fields(fields):
    # Python's sort is stable, so fields with the same requiredness retain
    # their live DOM order.  This avoids jumping to hidden attachment inputs
    # before the visible title/body controls that precede them.
    return sorted(fields, key=lambda field: 0 if field.required else 1)


def _auth_blocks_input(observation: Observation) -> bool:
    auth = getattr(observation, "auth", None)
    state = str(auth.get("state") if isinstance(auth, dict) else "")
    return bool(getattr(observation, "login_detected", False)) or state in {
        "required", "registration_required", "authenticating", "failed",
    }


def _decision_targets_commit(
    decision: Decision,
    observation: Observation,
    *,
    fields,
) -> bool:
    if decision.tool != "browser_click":
        return False
    ref = str((decision.args or {}).get("ref") or "").strip()
    if not ref:
        return False
    target = next((
        element
        for element in list(observation.elements or [])
        if isinstance(element, dict)
        and str(element.get("ref") or "").strip() == ref
    ), None)
    return bool(
        target
        and is_commit_control_for_fields(
            target,
            fields=fields,
            require_hit_testable=False,
        )
    )


def _commit_candidates(observation: Observation) -> List[Dict[str, Any]]:
    return [
        dict(element)
        for element in list(observation.elements or [])
        if isinstance(element, dict)
        and is_semantic_commit_control(
            element,
            require_hit_testable=False,
        )
    ]


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value if str(item).strip()}


_FILE_INTENT_RE = re.compile(
    r"(?:附件|上传|附上|添加文件|添加文档|attach(?:ment)?|upload|add\s+(?:a\s+)?file)",
    re.I,
)
