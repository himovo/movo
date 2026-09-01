from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .input_context import BrowserInputContext
from .media_activation import (
    MediaActivationResolution,
    _activation_score,
    _attempt_key,
    _content_ready_for_media,
    _editor_scope_ids,
    _upload_resolution,
    _usable_action,
)
from .media_compatibility import file_input_accepts_media, requested_media_kinds
from .media_editor import resolve_media_editor_ref
from .media_handoff import pending_media_candidates


def normalize_media_upload_decision(
    *,
    decision: Decision,
    observation: Observation,
    context: BrowserInputContext,
    completed_candidate_ids: Iterable[str],
) -> MediaActivationResolution:
    """Adopt a model-selected upload into the canonical media transaction."""

    if decision.tool != "browser_upload_file":
        return MediaActivationResolution()
    all_media = [
        candidate for candidate in context.candidates
        if candidate.value_kind == "file" and list(candidate.value or [])
    ]
    if not all_media:
        return MediaActivationResolution()

    pending = pending_media_candidates(context, completed_candidate_ids)
    if not pending:
        return MediaActivationResolution(
            decision=Decision(
                tool="browser_observe",
                args={},
                rationale=(
                    "[form_media_activation] all upstream media are already uploaded; "
                    "suppress duplicate upload and verify the current editor"
                ),
            ),
        )
    if not _content_ready_for_media(
        observation,
        context=context,
        completed_candidate_ids=completed_candidate_ids,
    ):
        return MediaActivationResolution(
            decision=Decision(
                tool="browser_observe",
                args={},
                rationale=(
                    "[form_media_activation] generated title/body must be written "
                    "before anchored media placement"
                ),
            ),
        )

    target = _ref_target(
        observation,
        str((decision.args or {}).get("ref") or "").strip(),
    )
    score = _media_upload_target_score(
        target,
        requested_kinds=requested_media_kinds(pending[:1]),
        editor_scopes=_editor_scope_ids(observation),
    )
    if target is None or score < 100:
        return MediaActivationResolution(
            decision=Decision(
                tool="browser_observe",
                args={},
                rationale=(
                    "[form_media_activation] model-selected upload target is stale "
                    "or is not a live media control; refresh the current editor"
                ),
            ),
        )

    candidate = pending[0]
    ref = str(target.get("ref") or "").strip()
    return _upload_resolution(
        target=target,
        pending=pending,
        score=score,
        attempt_key=_attempt_key(
            observation,
            ref,
            candidate_id=candidate.candidate_id,
        ),
        editor_ref=resolve_media_editor_ref(
            observation,
            target,
            anchor=candidate.metadata.get("media_anchor"),
        ),
    )


def _ref_target(
    observation: Observation,
    ref: str,
) -> Optional[Dict[str, Any]]:
    if not ref:
        return None
    return next((
        element
        for element in list(observation.elements or [])
        if isinstance(element, dict)
        and str(element.get("ref") or "").strip() == ref
    ), None)


def _media_upload_target_score(
    target: Optional[Dict[str, Any]],
    *,
    requested_kinds: set[str],
    editor_scopes: set[str],
) -> int:
    if target is None:
        return -1000
    if (
        str(target.get("type") or "").strip().lower() == "file"
        and not target.get("disabled")
    ):
        return 1000 if file_input_accepts_media(target, requested_kinds) else -1000
    if not _usable_action(target):
        return -1000
    return _activation_score(
        target,
        requested_kinds=requested_kinds,
        editor_scopes=editor_scopes,
    )


__all__ = ["normalize_media_upload_decision"]
