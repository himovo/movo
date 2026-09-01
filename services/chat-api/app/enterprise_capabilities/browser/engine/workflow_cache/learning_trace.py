from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List

from pydantic import BaseModel, Field

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord

from .page_state import url_shape
from .action_policy import action_disposition, stable_locator_required
from .terminal_semantics import locator_has_terminal_intent
from .recorded_target_identity import stabilize_recorded_target_identities


_LOCATOR_FIELDS = (
    "selector", "role", "name", "text", "description", "placeholder",
    "semanticPurpose", "scopeName", "scopeRole", "hasPopup", "frameDepth",
    "type", "accept", "activationVerified",
)


class LearningTraceEntry(BaseModel):
    sequence: int = 0
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    locator: Dict[str, Any] = Field(default_factory=dict)
    before_url: str = ""
    after_url: str = ""
    before_fingerprint: str = ""
    after_fingerprint: str = ""
    before_state_key: str = ""
    after_state_key: str = ""
    before_tab_id: str = ""
    after_tab_id: str = ""
    before_auth_state: str = "unknown"
    after_auth_state: str = "unknown"
    rationale: str = ""
    provenance: str = "agent"
    recording_id: str = ""


class LearningTraceGap(BaseModel):
    sequence: int = 0
    tool: str
    reason: str
    before_url: str = ""
    after_url: str = ""
    before_state_key: str = ""
    after_state_key: str = ""
    before_tab_id: str = ""
    after_tab_id: str = ""


class WorkflowLearningTrace:
    """Run-scoped, replay-safe action journal that survives human pauses.

    Planner history is deliberately compacted at checkpoints and drops live DOM
    refs.  This journal stores the semantic locator that the ref represented at
    execution time, so a resumed run can still learn the complete workflow.
    """

    def __init__(
        self,
        *,
        entries: Iterable[LearningTraceEntry] = (),
        gaps: Iterable[LearningTraceGap] = (),
        legacy_gap_count: int = 0,
        processed_records: int = 0,
    ) -> None:
        self.entries = list(entries)
        self.gaps = list(gaps)
        self.legacy_gap_count = max(0, int(legacy_gap_count))
        self._processed_records = max(0, int(processed_records))
        self._next_sequence = 1 + max(
            [int(item.sequence) for item in [*self.entries, *self.gaps]] or [-1]
        )

    @classmethod
    def restore(cls, payload: Dict[str, Any] | None, *, history_size: int) -> "WorkflowLearningTrace":
        data = payload if isinstance(payload, dict) else {}
        entries = []
        for index, item in enumerate(list(data.get("entries") or [])):
            if isinstance(item, dict):
                entries.append(LearningTraceEntry.model_validate({
                    **item, "sequence": int(item.get("sequence", index)),
                }))
        raw_gaps = data.get("gaps")
        legacy_gap_count = (
            int(raw_gaps or 0) if isinstance(raw_gaps, int)
            else int(data.get("legacy_gap_count") or 0)
        )
        gaps = [
            LearningTraceGap.model_validate(item)
            for item in list(raw_gaps or [])
            if isinstance(item, dict)
        ] if isinstance(raw_gaps, list) else []
        return cls(
            entries=entries,
            gaps=gaps,
            legacy_gap_count=legacy_gap_count,
            # Restored planner records are evidence only.  They have already
            # been journaled before suspension and no longer contain locators.
            processed_records=history_size,
        )

    def capture_new(self, history: List[StepRecord]) -> None:
        start = min(self._processed_records, len(history))
        for record in history[start:]:
            self._capture_record(record)
        self._processed_records = len(history)

    def capture_recorded(
        self,
        events: Iterable[Dict[str, Any]],
        *,
        input_context: Any,
    ) -> None:
        """Merge durable human-recorder events into the replay-safe journal."""
        file_candidates = [
            item for item in list(getattr(input_context, "candidates", None) or [])
            if str(getattr(item, "value_kind", "")) == "file"
        ]
        media_index = 0
        for event in stabilize_recorded_target_identities(events):
            kind = str(event.get("type") or "").strip().lower()
            if kind in {"recording_started", "recording_stopped", ""}:
                continue
            tool = {
                "click": "browser_click",
                "fill": "browser_fill",
                "select": "browser_select",
                "upload": "browser_upload_file",
                "paste_image": "browser_paste_image",
                "press": "browser_press",
                "navigate": "browser_navigate",
            }.get(kind, "")
            if not tool:
                self.gaps.append(LearningTraceGap(
                    sequence=self._take_sequence(),
                    tool=f"human:{kind}",
                    reason="unsupported_human_action",
                    before_url=str(event.get("before_url") or event.get("url") or ""),
                    after_url=str(event.get("after_url") or event.get("url") or ""),
                    before_tab_id=str(event.get("before_tab_id") or ""),
                    after_tab_id=str(event.get("after_tab_id") or ""),
                ))
                continue
            target = _recorded_locator(event.get("target"))
            if stable_locator_required(tool, event) and not target:
                self.gaps.append(LearningTraceGap(
                    sequence=self._take_sequence(),
                    tool=tool,
                    reason="human_stable_locator_missing",
                    before_url=str(event.get("before_url") or event.get("url") or ""),
                    after_url=str(event.get("after_url") or event.get("url") or ""),
                    before_tab_id=str(event.get("before_tab_id") or ""),
                    after_tab_id=str(event.get("after_tab_id") or ""),
                ))
                continue
            if (
                tool == "browser_click"
                and not _recorded_event_made_progress(event)
                and not locator_has_terminal_intent(target)
            ):
                # Human recordings include bubbling wrappers and accidental
                # clicks. Keep only causal clicks, while preserving terminal
                # commits whose asynchronous confirmation may arrive later.
                continue
            args: Dict[str, Any] = {}
            if tool == "browser_navigate":
                args["url"] = str(event.get("after_url") or event.get("url") or "")
            elif tool in {"browser_fill", "browser_select"}:
                if bool(event.get("value_redacted")):
                    # Credentials and one-time codes are intentionally never replayed.
                    continue
                args["value"] = str(event.get("value") or "")
            elif tool in {"browser_upload_file", "browser_paste_image"}:
                candidate = file_candidates[min(media_index, len(file_candidates) - 1)] if file_candidates else None
                media_index += 1
                raw_sources = getattr(candidate, "value", None) if candidate is not None else None
                sources = (
                    list(raw_sources)
                    if isinstance(raw_sources, (list, tuple))
                    else ([str(raw_sources)] if raw_sources else [])
                )
                if not sources:
                    self.gaps.append(LearningTraceGap(
                        sequence=self._take_sequence(),
                        tool=tool,
                        reason="human_media_source_unbound",
                        before_url=str(event.get("before_url") or event.get("url") or ""),
                        after_url=str(event.get("after_url") or event.get("url") or ""),
                        before_tab_id=str(event.get("before_tab_id") or ""),
                        after_tab_id=str(event.get("after_tab_id") or ""),
                    ))
                    continue
                args["sources"] = sources
            elif tool == "browser_press":
                key = str(event.get("key") or "").strip()
                if key not in {"Enter", "Tab", "Escape"}:
                    continue
                args["key"] = key
            before_url = str(event.get("before_url") or event.get("url") or "")
            after_url = str(event.get("after_url") or event.get("url") or before_url)
            before_fp = str(event.get("before_fingerprint") or "")
            after_fp = str(event.get("after_fingerprint") or "")
            entry = LearningTraceEntry(
                sequence=self._take_sequence(),
                tool=tool,
                args=args,
                locator=target,
                before_url=before_url,
                after_url=after_url,
                before_fingerprint=before_fp,
                after_fingerprint=after_fp,
                before_state_key=f"{url_shape(before_url)}|{before_fp}",
                after_state_key=f"{url_shape(after_url)}|{after_fp}",
                before_tab_id=str(event.get("before_tab_id") or ""),
                after_tab_id=str(event.get("after_tab_id") or event.get("before_tab_id") or ""),
                before_auth_state=str(event.get("before_auth_state") or "unknown"),
                after_auth_state=str(event.get("after_auth_state") or "unknown"),
                rationale="[human_recording] observed semantic browser action",
                provenance="human",
                recording_id=str(event.get("recording_id") or ""),
            )
            if self.entries and _entry_digest(self.entries[-1]) == _entry_digest(entry):
                continue
            self.entries.append(entry)

    def export(self) -> Dict[str, Any]:
        return {
            "version": 2,
            "gaps": [gap.model_dump(mode="json") for gap in self.gaps],
            "legacy_gap_count": self.legacy_gap_count,
            "entries": [entry.model_dump(mode="json") for entry in self.entries],
        }

    @property
    def complete(self) -> bool:
        return not self.gaps and self.legacy_gap_count == 0 and bool(self.entries)

    def distill(self, *, site_id: str = ""):
        from .path_distiller import distill_success_path

        return distill_success_path(self.entries, self.gaps, site_id=site_id)

    def successful_path(self, *, site_id: str = "") -> List[StepRecord]:
        distilled = self.distill(site_id=site_id)
        return [_entry_as_record(entry, index) for index, entry in enumerate(distilled.entries)]

    def _capture_record(self, record: StepRecord) -> None:
        tool = str(record.decision.tool or "")
        if not record.ok:
            return
        disposition = action_disposition(tool)
        if disposition == "ignore":
            return
        if disposition == "unsupported":
            self._record_gap(record, reason="unsupported_tool")
            return
        if tool in {"browser_click", "browser_click_at", "browser_hover", "browser_scroll"} and not _made_progress(record):
            # Successful dispatch without an observable transition is usually
            # exploration noise (or a duplicate click), not a causal step.
            return
        locator = _locator_for_record(record)
        if stable_locator_required(tool, record.decision.args) and not locator:
            self._record_gap(record, reason="stable_locator_missing")
            return
        before = record.decision_observation
        after = record.observation
        entry = LearningTraceEntry(
            sequence=self._take_sequence(),
            tool=tool,
            args=_stable_action_args(record.decision.args),
            locator=locator,
            before_url=str((before or after).url or ""),
            after_url=str(after.url or ""),
            before_fingerprint=str((before.state_fingerprint if before else "") or ""),
            after_fingerprint=str(after.state_fingerprint or ""),
            before_state_key=_state_key(before or after),
            after_state_key=_state_key(after),
            before_auth_state=str(((before.auth if before else None) or {}).get("state") or "unknown"),
            after_auth_state=str((after.auth or {}).get("state") or "unknown"),
            rationale=str(record.decision.rationale or "")[:500],
            provenance="agent",
        )
        if self.entries and _entry_digest(self.entries[-1]) == _entry_digest(entry):
            return
        self.entries.append(entry)

    def _record_gap(self, record: StepRecord, *, reason: str) -> None:
        before = record.decision_observation
        after = record.observation
        self.gaps.append(LearningTraceGap(
            sequence=self._take_sequence(),
            tool=str(record.decision.tool or ""),
            reason=str(reason or "unknown"),
            before_url=str((before or after).url or ""),
            after_url=str(after.url or ""),
            before_state_key=_state_key(before or after),
            after_state_key=_state_key(after),
        ))

    def _take_sequence(self) -> int:
        value = self._next_sequence
        self._next_sequence += 1
        return value


def _stable_action_args(args: Dict[str, Any]) -> Dict[str, Any]:
    safe = dict(args or {})
    for key in ("ref", "editor_ref", "x", "y", "source_width", "source_height"):
        safe.pop(key, None)
    try:
        return json.loads(json.dumps(safe, ensure_ascii=False, default=str))
    except Exception:
        return {}


def _recorded_locator(value: Any) -> Dict[str, Any]:
    target = value if isinstance(value, dict) else {}
    aliases = {"aria_label": "name", "ancestor_contains_text": "scopeName", "ancestor_role": "scopeRole"}
    output: Dict[str, Any] = {}
    for raw_key, raw_value in target.items():
        key = aliases.get(str(raw_key), str(raw_key))
        if key not in _LOCATOR_FIELDS or raw_value in (None, "", False):
            continue
        output[key] = raw_value
    return output


def _recorded_event_made_progress(event: Dict[str, Any]) -> bool:
    before_tab = str(event.get("before_tab_id") or "")
    after_tab = str(event.get("after_tab_id") or "")
    if before_tab and after_tab and before_tab != after_tab:
        return True
    before_url = str(event.get("before_url") or event.get("url") or "")
    after_url = str(event.get("after_url") or event.get("url") or before_url)
    if before_url != after_url:
        return True
    before_fp = str(event.get("before_fingerprint") or "")
    after_fp = str(event.get("after_fingerprint") or "")
    return bool(before_fp and after_fp and before_fp != after_fp)


def _locator_for_record(record: StepRecord) -> Dict[str, Any]:
    before = record.decision_observation
    if before is None:
        return {}
    tool = str(record.decision.tool or "")
    args = dict(record.decision.args or {})
    ref = str(args.get("editor_ref") if tool == "browser_paste_image" else args.get("ref") or "")
    target = next((
        item for item in before.elements
        if isinstance(item, dict) and ref and str(item.get("ref") or "") == ref
    ), None)
    if target is None and tool in {"browser_click_at", "browser_type_at"}:
        target = _target_at(before, args)
    if not isinstance(target, dict):
        return {}
    return {
        key: target[key]
        for key in _LOCATOR_FIELDS
        if target.get(key) not in (None, "", False)
    }


def _target_at(observation: Observation, args: Dict[str, Any]) -> Dict[str, Any] | None:
    try:
        x, y = float(args.get("x")), float(args.get("y"))
    except (TypeError, ValueError):
        return None
    matches = []
    for item in observation.elements:
        if not isinstance(item, dict):
            continue
        try:
            cx, cy = float(item.get("x")), float(item.get("y"))
            width, height = float(item.get("width")), float(item.get("height"))
        except (TypeError, ValueError):
            continue
        if cx - width / 2 <= x <= cx + width / 2 and cy - height / 2 <= y <= cy + height / 2:
            matches.append(item)
    return matches[0] if len(matches) == 1 else None


def _entry_as_record(entry: LearningTraceEntry, index: int) -> StepRecord:
    ref = f"trace-{index}"
    args = dict(entry.args)
    tool = entry.tool
    if entry.locator:
        args["editor_ref" if tool == "browser_paste_image" else "ref"] = ref
    before_element = {"ref": ref, **entry.locator} if entry.locator else None
    before = Observation(
        url=entry.before_url,
        title="",
        elements=[before_element] if before_element else [],
        state_fingerprint=entry.before_fingerprint,
        auth={"state": entry.before_auth_state},
    )
    after = Observation(
        url=entry.after_url,
        title="",
        elements=[],
        state_fingerprint=entry.after_fingerprint,
        auth={"state": entry.after_auth_state},
    )
    return StepRecord(
        observation=after,
        decision_observation=before,
        decision=Decision(tool=tool, args=args, rationale=entry.rationale),
        ok=True,
    )


def _entry_digest(entry: LearningTraceEntry) -> str:
    payload = entry.model_dump(mode="json")
    payload.pop("sequence", None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _made_progress(record: StepRecord) -> bool:
    before = record.decision_observation
    after = record.observation
    if before is None or before.url != after.url:
        return True
    if before.state_fingerprint and after.state_fingerprint:
        return before.state_fingerprint != after.state_fingerprint
    return before.page_text != after.page_text or before.elements != after.elements


def _state_key(observation: Observation) -> str:
    anchors = []
    for item in observation.elements:
        if not isinstance(item, dict) or item.get("visible", True) is False:
            continue
        token = "|".join(str(item.get(key) or "").strip().casefold() for key in (
            "role", "name", "placeholder", "semanticPurpose", "scopeName", "hasPopup",
        ))
        if token.strip("|"):
            anchors.append(token)
    stable = "\n".join(sorted(set(anchors))[:80])
    semantic = hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16] if stable else ""
    fingerprint = str(observation.state_fingerprint or "")
    return f"{url_shape(observation.url)}|{semantic or fingerprint}"


__all__ = ["LearningTraceEntry", "LearningTraceGap", "WorkflowLearningTrace"]
