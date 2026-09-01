from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .input_context import BrowserInputContext
from .media_handoff import pending_media_candidates
from .media_target_affinity import (
    MediaTargetHint,
    capture_media_target_hint,
)

if TYPE_CHECKING:
    from .media_activation import MediaActivationResolution


@dataclass
class MediaInsertionSequence:
    """Keep sequential media insertions bound to fresh DOM and their editor."""

    in_flight_candidate_ids: set[str] = field(default_factory=set)
    in_flight_target_hint: Optional[MediaTargetHint] = None
    preferred_target_hint: Optional[MediaTargetHint] = None
    refresh_required: bool = False

    def begin(
        self,
        resolution: "MediaActivationResolution",
        observation: Optional[Observation],
    ) -> None:
        self.in_flight_candidate_ids = set(resolution.candidate_ids)
        args = resolution.decision.args or {}
        ref = str(args.get("ref") or args.get("editor_ref") or "").strip()
        self.in_flight_target_hint = capture_media_target_hint(
            observation,
            ref,
        )

    def complete_insertion(
        self,
        *,
        decision: Decision,
        ok: bool,
        observation_after: Observation,
        completed_candidate_ids: set[str],
        context: BrowserInputContext,
    ) -> set[str]:
        confirmed_ids: set[str] = set()
        if _insertion_confirmed(decision, ok, observation_after):
            confirmed_ids = set(self.in_flight_candidate_ids)
            completed_candidate_ids.update(confirmed_ids)
            self.preferred_target_hint = self.in_flight_target_hint
            self.refresh_required = bool(
                pending_media_candidates(context, completed_candidate_ids)
            )
        self.in_flight_candidate_ids.clear()
        self.in_flight_target_hint = None
        return confirmed_ids

    def complete_refresh(self, ok: bool) -> None:
        self.refresh_required = not ok

    def reset(self) -> None:
        self.in_flight_candidate_ids.clear()
        self.in_flight_target_hint = None
        self.preferred_target_hint = None
        self.refresh_required = False


def _insertion_confirmed(
    decision: Decision,
    ok: bool,
    observation_after: Observation,
) -> bool:
    if not ok or decision.tool not in {
        "browser_upload_file",
        "browser_paste_image",
    }:
        return False
    editor_ref = str((decision.args or {}).get("editor_ref") or "").strip()
    if not editor_ref:
        return True
    diagnostics = (
        observation_after.diagnostics
        if isinstance(observation_after.diagnostics, dict)
        else {}
    )
    if decision.tool == "browser_upload_file":
        receipt = diagnostics.get("upload")
    else:
        receipt = diagnostics.get("mediaInsert")
    return isinstance(receipt, dict) and str(
        receipt.get("status") or "",
    ).strip().lower() == "confirmed"


MediaUploadSequence = MediaInsertionSequence


__all__ = ["MediaInsertionSequence", "MediaUploadSequence"]
