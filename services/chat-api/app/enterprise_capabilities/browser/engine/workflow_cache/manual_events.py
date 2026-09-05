from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable

from .manual_inputs import infer_recorded_semantic
from .page_state import url_shape
from .recorded_event_evidence import (
    recorded_event_made_progress,
    unresolved_click_is_preparatory_fill,
)


@dataclass(frozen=True)
class NormalizedManualEvents:
    events: list[Dict[str, Any]]
    discarded_mutations: int = 0
    discarded_diagnostics: int = 0


def normalize_manual_events(events: Iterable[Dict[str, Any]]) -> NormalizedManualEvents:
    """Remove browser noise and collapse mirrored writes without site rules.

    Reactive editors may expose one user edit through a native input and one or
    more contenteditable mirrors. Only the final portable write is useful to a
    replay plan. Click/navigation boundaries are retained so separate business
    interactions are never folded together.
    """
    ordered = sorted(
        (dict(item) for item in events if isinstance(item, dict)),
        key=lambda item: int(item.get("sequence") or 0),
    )
    output: list[Dict[str, Any]] = []
    mutation_burst: list[Dict[str, Any]] = []
    pending_tab: Dict[str, Any] | None = None
    discarded = 0
    discarded_diagnostics = 0

    def flush() -> None:
        nonlocal discarded, pending_tab
        if mutation_burst:
            normalized = _normalize_mutation_burst(mutation_burst)
            discarded += len(mutation_burst) - len(normalized)
            output.extend(normalized)
            mutation_burst.clear()
        if pending_tab is not None:
            output.append(pending_tab)
            pending_tab = None

    for index, event in enumerate(ordered):
        kind = str(event.get("type") or "").strip().lower()
        target = event.get("target") if isinstance(event.get("target"), dict) else {}
        following = ordered[index + 1] if index + 1 < len(ordered) else None
        if kind == "unresolved_click" and (
            not recorded_event_made_progress(event)
            or unresolved_click_is_preparatory_fill(event, following)
        ):
            # Capturing-phase listeners see incidental clicks on page chrome,
            # overlays, and rich-editor placeholders. A same-document click
            # immediately superseded by a fill is focus preparation, not a
            # separately replayable business action.
            discarded_diagnostics += 1
            continue
        if kind == "fill" and str(target.get("type") or "").strip().casefold() == "file":
            discarded += 1
            continue
        if kind in {"fill", "select"}:
            if _is_route_hydration_duplicate(event, output):
                # Some reactive sites restore the submitted search value after
                # Enter has navigated to the results route. The resulting DOM
                # input event is browser hydration, not a second human edit.
                discarded += 1
                continue
            if pending_tab is not None and not _mutation_belongs_before_tab(event, pending_tab):
                flush()
            mutation_burst.append(event)
            continue
        # Tab merely flushes/focuses editors and belongs to the same mutation
        # burst. Other actions establish a causal boundary.
        if kind == "press" and str(event.get("key") or "") == "Tab":
            if pending_tab is not None:
                flush()
            pending_tab = event
            continue
        flush()
        output.append(event)
    flush()
    output = [dict(item, _recording_order=index) for index, item in enumerate(output)]
    return NormalizedManualEvents(
        events=output,
        discarded_mutations=discarded,
        discarded_diagnostics=discarded_diagnostics,
    )


def _normalize_mutation_burst(events: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    # First retain only the last value sent to the exact same DOM target.
    by_target: dict[tuple[str, str, str, str], Dict[str, Any]] = {}
    passthrough: list[Dict[str, Any]] = []
    for event in events:
        target = event.get("target") if isinstance(event.get("target"), dict) else {}
        selector = str(target.get("selector") or "").strip()
        if not selector:
            passthrough.append(event)
            continue
        key = (
            str(event.get("type") or "").casefold(),
            url_shape(str(event.get("before_url") or event.get("url") or "")),
            str(target.get("frameDepth") or 0),
            selector,
        )
        by_target[key] = event
    candidates = sorted(
        [*passthrough, *by_target.values()],
        key=lambda item: int(item.get("sequence") or 0),
    )

    # Then collapse adjacent mirrors only when both semantic role and final
    # value agree. Distinct fields with the same value remain separate unless
    # they independently identify the same business role.
    removed: set[int] = set()
    for left_index, left in enumerate(candidates):
        if left_index in removed:
            continue
        left_target = left.get("target") if isinstance(left.get("target"), dict) else {}
        left_semantic = infer_recorded_semantic(left_target, str(left.get("type") or ""), left_index)
        if left_semantic.startswith("field_"):
            continue
        left_value = _normalized_value(left.get("value"))
        for right_index in range(left_index + 1, len(candidates)):
            right = candidates[right_index]
            if int(right.get("sequence") or 0) - int(left.get("sequence") or 0) > 3:
                break
            right_target = right.get("target") if isinstance(right.get("target"), dict) else {}
            right_semantic = infer_recorded_semantic(
                right_target, str(right.get("type") or ""), right_index,
            )
            if (
                str(left.get("type") or "") != str(right.get("type") or "")
                or left_semantic != right_semantic
                or left_value != _normalized_value(right.get("value"))
                or url_shape(str(left.get("before_url") or left.get("url") or ""))
                != url_shape(str(right.get("before_url") or right.get("url") or ""))
            ):
                continue
            if _locator_quality(right_target, right) >= _locator_quality(left_target, left):
                removed.add(left_index)
                break
            removed.add(right_index)
    return [item for index, item in enumerate(candidates) if index not in removed]


def _normalized_value(value: Any) -> str:
    return " ".join(str(value or "").split())


def _mutation_belongs_before_tab(event: Dict[str, Any], tab: Dict[str, Any]) -> bool:
    if int(event.get("sequence") or 0) - int(tab.get("sequence") or 0) > 3:
        return False
    event_target = event.get("target") if isinstance(event.get("target"), dict) else {}
    tab_target = tab.get("target") if isinstance(tab.get("target"), dict) else {}
    event_selector = str(event_target.get("selector") or "").strip()
    tab_selector = str(tab_target.get("selector") or "").strip()
    if event_selector and event_selector == tab_selector:
        return True
    event_semantic = infer_recorded_semantic(event_target, str(event.get("type") or ""), 0)
    tab_semantic = infer_recorded_semantic(tab_target, "fill", 0)
    return event_semantic == tab_semantic and not event_semantic.startswith("field_")


def _is_route_hydration_duplicate(
    event: Dict[str, Any],
    output: list[Dict[str, Any]],
) -> bool:
    if len(output) < 2:
        return False
    previous, submit = output[-2], output[-1]
    if (
        str(previous.get("type") or "").casefold() not in {"fill", "select"}
        or str(submit.get("type") or "").casefold() != "press"
        or str(submit.get("key") or "") != "Enter"
        or int(event.get("sequence") or 0) - int(submit.get("sequence") or 0) > 3
        or _normalized_value(previous.get("value")) != _normalized_value(event.get("value"))
    ):
        return False
    submit_before = str(submit.get("before_url") or submit.get("url") or "")
    submit_after = str(submit.get("after_url") or submit.get("url") or "")
    event_before = str(event.get("before_url") or event.get("url") or "")
    if not submit_before or submit_before == submit_after or submit_after != event_before:
        return False
    previous_target = previous.get("target") if isinstance(previous.get("target"), dict) else {}
    event_target = event.get("target") if isinstance(event.get("target"), dict) else {}
    previous_selector = str(previous_target.get("selector") or "").strip()
    event_selector = str(event_target.get("selector") or "").strip()
    if previous_selector and previous_selector == event_selector:
        return True
    previous_semantic = infer_recorded_semantic(
        previous_target, str(previous.get("type") or ""), 0,
    )
    event_semantic = infer_recorded_semantic(
        event_target, str(event.get("type") or ""), 0,
    )
    return previous_semantic == event_semantic and not previous_semantic.startswith("field_")


def _locator_quality(target: Dict[str, Any], event: Dict[str, Any]) -> int:
    selector = str(target.get("selector") or "").strip()
    name = " ".join(str(target.get("name") or "").split())
    placeholder = " ".join(str(target.get("placeholder") or "").split())
    value = _normalized_value(event.get("value"))
    score = 0
    if re.fullmatch(r"#[A-Za-z_][\w:.-]*", selector):
        score += 50
    elif selector:
        score += max(0, 20 - len(selector) // 20)
    if str(target.get("role") or ""):
        score += 8
    if placeholder:
        score += 14
    if name and _normalized_value(name) != value:
        score += 10
    if len(name) > 120:
        score -= 20
    return score


__all__ = ["NormalizedManualEvents", "normalize_manual_events"]
