from __future__ import annotations

import asyncio
import logging
from typing import Any, Set

from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import StepRecord
from app.enterprise_capabilities.browser.engine.business_site_scope import resolve_site_from_history, scope_node

from .contracts import CachedBrowserWorkflow, CachedCompletionContract
from .compiler import compile_parameterized_workflow
from .distiller import distill_field_bindings, dynamic_input_roles
from .identity import build_workflow_identity, site_id_for_node
from .matching import (
    request_fingerprint,
    select_strong_matching_workflow,
    workflow_match_score,
)
from .repository import BrowserWorkflowCacheRepository, CURRENT_WORKFLOW_ADMISSION_REVISION
from .quality import workflow_plan_hash, workflow_quality_score
from .coverage import assess_cached_workflow, assess_compiled_workflow
from .replay_plan import build_replay_plan


logger = logging.getLogger(__name__)
_background_tasks: Set[asyncio.Task[Any]] = set()


class BrowserWorkflowCacheService:
    def __init__(
        self,
        repository: BrowserWorkflowCacheRepository | None = None,
    ) -> None:
        self.repository = repository or BrowserWorkflowCacheRepository()

    async def lookup(
        self,
        *,
        user_id: str,
        main_id: str,
        node: CapabilityTask,
        input_context: BrowserInputContext,
        preferred_workflow_id: str = "",
        allow_quarantined_preferred: bool = False,
    ) -> CachedBrowserWorkflow | None:
        identity = build_workflow_identity(
            user_id=user_id,
            main_id=main_id,
            node=node,
            input_context=input_context,
        )
        try:
            capability_id = str((node.meta or {}).get("capability_id") or "")
            if preferred_workflow_id:
                workflow = await self.repository.find_by_id(
                    preferred_workflow_id,
                    include_quarantined=allow_quarantined_preferred,
                )
                if not _preferred_resume_compatible(
                    workflow,
                    identity=identity,
                    user_id=user_id,
                    context=input_context,
                    capability_id=capability_id,
                ):
                    return None
            else:
                # Cache reuse is an optional local optimization.  Without a
                # resolved site there is no safe deterministic scope, so DSH
                # exploration owns the task instead of a cross-site model
                # classification blocking the browser critical path.
                site_id = site_id_for_node(node, input_context=input_context)
                if not site_id:
                    return None
                candidates = await self.repository.find_candidates(
                    user_id=user_id,
                    site_id=site_id,
                )
                candidates = await self._exclude_pre_revision_failures(candidates)
                workflow = self._select_site_candidate(
                    candidates=candidates,
                    identity=identity,
                    site_id=site_id,
                    input_context=input_context,
                    capability_id=capability_id,
                )
        except Exception as exc:
            logger.warning(
                "browser workflow cache lookup failed",
                extra={"event": "browser.workflow_cache_lookup_failed", "error": str(exc)},
            )
            return None
        if workflow is None or (not workflow.steps and not workflow.field_bindings):
            return None
        replay_plan = build_replay_plan(workflow, input_context)
        logger.info(
            "browser workflow replay coverage planned",
            extra={
                "event": "browser.workflow_cache_replay_planned",
                "workflow_id": workflow.workflow_id,
                "mode": replay_plan.mode,
                "covered_input_roles": list(replay_plan.covered_roles),
                "missing_input_roles": list(replay_plan.missing_roles),
                "terminal_action_deferred": replay_plan.terminal_deferred,
                "replay_steps": len(replay_plan.steps),
            },
        )
        coverage = assess_cached_workflow(workflow)
        if not coverage.allowed:
            await self.repository.quarantine(workflow.workflow_id, ",".join(coverage.reasons))
            logger.info(
                "browser workflow cache quarantined incomplete workflow",
                extra={
                    "event": "browser.workflow_cache_quarantined",
                    "workflow_id": workflow.workflow_id,
                    "reasons": list(coverage.reasons),
                },
            )
            return None
        return workflow

    async def _exclude_pre_revision_failures(
        self,
        candidates: list[CachedBrowserWorkflow],
    ) -> list[CachedBrowserWorkflow]:
        usable: list[CachedBrowserWorkflow] = []
        for workflow in candidates:
            legacy_manual = str(workflow.created_from_run_id or "").startswith("manual_")
            known_failure = int(workflow.failure_count or 0) > 0
            admission_revision = int(workflow.admission_revision or 0)
            obsolete_manual = (
                legacy_manual
                and admission_revision < CURRENT_WORKFLOW_ADMISSION_REVISION
            )
            obsolete_failed = known_failure and admission_revision < 2
            if obsolete_manual or obsolete_failed:
                quarantine = getattr(self.repository, "quarantine", None)
                if callable(quarantine):
                    await quarantine(
                        workflow.workflow_id,
                        (
                            "superseded_by_recording_semantics_v3"
                            if obsolete_manual else
                            "superseded_by_recording_admission_v2"
                        ),
                    )
                continue
            usable.append(workflow)
        return usable

    def _select_site_candidate(
        self,
        *,
        candidates: list[CachedBrowserWorkflow],
        identity,
        site_id: str,
        input_context: BrowserInputContext,
        capability_id: str,
    ) -> CachedBrowserWorkflow | None:
        if not candidates:
            return None
        workflow = select_strong_matching_workflow(
            candidates,
            identity=identity,
            context=input_context,
            capability_id=capability_id,
        )
        if workflow is None:
            logger.info(
                "browser workflow cache found no deterministic match",
                extra={
                    "event": "browser.workflow_cache_deterministic_no_match",
                    "site_id": site_id,
                    "candidate_count": len(candidates),
                    "operation_id": (
                        identity.operation_id if identity is not None else ""
                    ),
                },
            )
            return None
        logger.info(
            "browser workflow selected deterministically",
            extra={
                "event": "browser.workflow_cache_deterministic_match",
                "site_id": site_id,
                "workflow_id": workflow.workflow_id,
                "operation_id": workflow.identity.operation_id,
                "candidate_count": len(candidates),
            },
        )
        return workflow

    def _schedule_success_capture(
        self,
        *,
        user_id: str,
        main_id: str,
        node: CapabilityTask,
        input_context: BrowserInputContext,
        history: list[StepRecord],
        run_id: str,
        replayed: bool,
        matched_workflow: CachedBrowserWorkflow | None = None,
        trace_complete: bool = True,
        replay_failed: bool = False,
        display_name: str = "",
    ) -> asyncio.Task[bool] | None:
        identity = build_workflow_identity(
            user_id=user_id,
            main_id=main_id,
            node=node,
            input_context=input_context,
        )
        if identity is None:
            node = scope_node(node, resolve_site_from_history(history))
            identity = build_workflow_identity(
                user_id=user_id,
                main_id=main_id,
                node=node,
                input_context=input_context,
            )
        if identity is None:
            return None
        if matched_workflow is not None and (replayed or replay_failed):
            identity = matched_workflow.identity
        compiled = compile_parameterized_workflow(list(history), input_context)
        steps = compiled.steps
        field_bindings = distill_field_bindings(list(history), input_context)
        complete = bool(trace_complete and compiled.complete)
        if not complete or not steps:
            logger.info(
                "browser workflow cache skipped incomplete trace",
                extra={
                    "event": "browser.workflow_cache_skipped",
                    "reason": "incomplete_success_path",
                    "trace_complete": bool(trace_complete),
                    "skipped_actions": int(compiled.skipped_actions),
                    "steps": len(steps),
                },
            )
            return None
        completion = CachedCompletionContract(
            capability_id=str((node.meta or {}).get("capability_id") or ""),
            file_direction=(
                "upload"
                if any(
                    record.decision.tool in {"browser_upload_file", "browser_paste_image"}
                    for record in history
                )
                else "download"
            ),
        )
        coverage = assess_compiled_workflow(
            steps=steps,
            context=input_context,
            capability_id=completion.capability_id,
            dynamic_roles=dynamic_input_roles(input_context),
        )
        if not coverage.allowed:
            logger.info(
                "browser workflow cache skipped insufficient coverage",
                extra={
                    "event": "browser.workflow_cache_skipped",
                    "reason": "insufficient_business_coverage",
                    "coverage_reasons": list(coverage.reasons),
                },
            )
            return None
        plan_hash = workflow_plan_hash(steps, field_bindings, completion)
        quality_score = workflow_quality_score(
            steps, field_bindings, complete=complete,
        )
        task = asyncio.create_task(self._persist_success(
            identity=identity,
            steps=steps,
            field_bindings=field_bindings,
            request_template=compiled.request_template,
            request_fingerprint=request_fingerprint(input_context.original_request),
            completion=completion,
            roles=dynamic_input_roles(input_context),
            run_id=run_id,
            replayed=replayed,
            plan_hash=plan_hash,
            quality_score=quality_score,
            matched_workflow_id=(matched_workflow.workflow_id if matched_workflow is not None else ""),
            replay_failed=replay_failed,
            display_name=display_name,
        ))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return task

    def schedule_success_capture(self, **kwargs: Any) -> bool:
        """Queue automatic/assisted learning without delaying task completion."""
        return self._schedule_success_capture(**kwargs) is not None

    async def capture_success(self, **kwargs: Any) -> bool:
        """Persist an explicit recording before reporting success to the user."""
        task = self._schedule_success_capture(**kwargs)
        return bool(task is not None and await task)

    def failure_reporter(self, workflow: CachedBrowserWorkflow | None):
        if workflow is None:
            return None

        def report(reason: str) -> None:
            task = asyncio.create_task(self._persist_failure(workflow.workflow_id, reason))
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)

        return report

    async def _persist_failure(self, workflow_id: str, reason: str) -> None:
        try:
            await self.repository.mark_failure(workflow_id, reason)
        except Exception as exc:
            logger.warning(
                "browser workflow cache failure feedback failed",
                extra={"event": "browser.workflow_cache_failure_feedback_failed", "error": str(exc)},
            )

    async def _persist_success(
        self, *, identity, steps, field_bindings, request_template, request_fingerprint,
        completion, roles, run_id, replayed, plan_hash, quality_score,
        matched_workflow_id, replay_failed, display_name="",
    ) -> bool:
        try:
            saved = await self.repository.upsert_success(
                identity=identity,
                steps=steps,
                field_bindings=field_bindings,
                request_template=request_template,
                request_fingerprint=request_fingerprint,
                completion=completion,
                dynamic_input_roles=roles,
                display_name=display_name,
                run_id=run_id,
                replayed=replayed,
                plan_hash=plan_hash,
                quality_score=quality_score,
                matched_workflow_id=matched_workflow_id,
                replay_failed=replay_failed,
            )
            logger.info(
                "browser workflow cache learned",
                extra={
                    "event": "browser.workflow_cache_learned",
                    "workflow_id": saved.workflow_id,
                    "site_id": identity.site_id,
                    "operation_id": identity.operation_id,
                    "steps": len(steps),
                    "field_bindings": len(field_bindings),
                    "replayed": replayed,
                    "replay_failed": replay_failed,
                    "quality_score": quality_score,
                },
            )
            return True
        except Exception as exc:
            logger.warning(
                "browser workflow cache persistence failed",
                extra={"event": "browser.workflow_cache_persist_failed", "error": str(exc)},
            )
            return False


browser_workflow_cache = BrowserWorkflowCacheService()


def _preferred_resume_compatible(
    workflow: CachedBrowserWorkflow | None,
    *,
    identity,
    user_id: str,
    context: BrowserInputContext,
    capability_id: str,
) -> bool:
    """Validate a checkpoint-pinned workflow without re-inferring its label."""

    if workflow is None:
        return False
    if workflow.identity.user_id != str(user_id):
        return False
    if identity is not None and workflow.identity.site_id != identity.site_id:
        return False
    if workflow.version < 2:
        return True
    return workflow_match_score(
        workflow,
        context=context,
        capability_id=capability_id,
    ) >= 0


__all__ = ["BrowserWorkflowCacheService", "browser_workflow_cache"]
