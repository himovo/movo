"""Resolve clipboard-based media insertion inside the existing media transaction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .input_context import BrowserInputContext, InputCandidate
from .media_activation import (
    MediaActivationResolution,
    _attempt_key,
    _content_ready_for_media,
)
from .media_delivery import prefers_media_paste
from .media_editor import normalize_media_editor_ref, resolve_media_editor_ref
from .media_handoff import pending_media_candidates


def resolve_requested_media_paste(
    *,
    observation: Observation,
    context: BrowserInputContext,
    completed_candidate_ids: Iterable[str],
    attempted_keys: Iterable[str],
) -> MediaActivationResolution:
    if not prefers_media_paste(context.original_request):
        return MediaActivationResolution()
    unit = _next_paste_unit(context, completed_candidate_ids)
    if unit is None or not _content_ready_for_media(
        observation,
        context=context,
        completed_candidate_ids=completed_candidate_ids,
    ):
        return MediaActivationResolution()
    return _paste_resolution(
        observation=observation,
        unit=unit,
        attempted_keys=attempted_keys,
    )


def normalize_media_paste_decision(
    *,
    decision: Decision,
    observation: Observation,
    context: BrowserInputContext,
    completed_candidate_ids: Iterable[str],
) -> MediaActivationResolution:
    """Adopt a model-selected paste into the canonical media transaction."""

    if decision.tool != "browser_paste_image":
        return MediaActivationResolution()
    unit = _next_paste_unit(context, completed_candidate_ids)
    if unit is None:
        return _observe_resolution(
            "all upstream media are already inserted; verify the current editor",
        )
    if not _content_ready_for_media(
        observation,
        context=context,
        completed_candidate_ids=completed_candidate_ids,
    ):
        return _observe_resolution(
            "generated title/body must be written before anchored media placement",
        )

    candidate = unit.candidate
    anchor = candidate.metadata.get("media_anchor")
    requested_ref = str((decision.args or {}).get("editor_ref") or "").strip()
    editor_ref = normalize_media_editor_ref(
        observation,
        requested_ref,
        anchor=anchor,
    )
    if not editor_ref:
        return _observe_resolution(
            "model-selected paste target is stale or is not the current body editor",
        )
    return _paste_resolution(
        observation=observation,
        unit=unit,
        attempted_keys=(),
        editor_ref=editor_ref,
    )


@dataclass(frozen=True)
class _PasteUnit:
    candidate: InputCandidate
    source: str
    unit_id: str
    completion_ids: tuple[str, ...]


def _paste_resolution(
    *,
    observation: Observation,
    unit: _PasteUnit,
    attempted_keys: Iterable[str],
    editor_ref: str = "",
) -> MediaActivationResolution:
    candidate = unit.candidate
    anchor = candidate.metadata.get("media_anchor")
    resolved_editor_ref = (
        normalize_media_editor_ref(
            observation,
            editor_ref,
            anchor=anchor,
        )
        if editor_ref
        else resolve_media_editor_ref(
            observation,
            {},
            anchor=anchor,
        )
    )
    if not resolved_editor_ref:
        return MediaActivationResolution()
    attempt_key = _attempt_key(
        observation,
        resolved_editor_ref,
        candidate_id=unit.unit_id,
    )
    if attempt_key in {str(item) for item in attempted_keys if str(item)}:
        return MediaActivationResolution()
    args: Dict[str, Any] = {
        "editor_ref": resolved_editor_ref,
        "sources": [unit.source],
    }
    if isinstance(anchor, dict):
        args["anchor"] = dict(anchor)
    return MediaActivationResolution(
        decision=Decision(
            tool="browser_paste_image",
            args=args,
            rationale=(
                "[form_media_paste] paste the upstream image at its generated "
                "rich-editor anchor"
            ),
        ),
        attempt_key=attempt_key,
        candidate_refs=(resolved_editor_ref,),
        candidate_ids=unit.completion_ids,
    )


def _next_paste_unit(
    context: BrowserInputContext,
    completed_candidate_ids: Iterable[str],
) -> _PasteUnit | None:
    completed = {str(item) for item in completed_candidate_ids if str(item)}
    for candidate in pending_media_candidates(context, completed):
        sources = [
            str(source)
            for source in list(candidate.value or [])
            if str(source).strip()
        ]
        for index, source in enumerate(sources):
            unit_id = (
                candidate.candidate_id
                if len(sources) == 1
                else f"{candidate.candidate_id}::paste::{index}"
            )
            if unit_id in completed:
                continue
            completion_ids = [unit_id]
            remaining_ids = {
                f"{candidate.candidate_id}::paste::{later}"
                for later in range(len(sources))
                if later != index
            }
            if candidate.candidate_id != unit_id and remaining_ids.issubset(completed):
                completion_ids.append(candidate.candidate_id)
            return _PasteUnit(
                candidate=candidate,
                source=source,
                unit_id=unit_id,
                completion_ids=tuple(completion_ids),
            )
    return None


def _observe_resolution(reason: str) -> MediaActivationResolution:
    return MediaActivationResolution(
        decision=Decision(
            tool="browser_observe",
            args={},
            rationale=f"[form_media_paste] {reason}",
        ),
    )


__all__ = [
    "normalize_media_paste_decision",
    "prefers_media_paste",
    "resolve_requested_media_paste",
]
