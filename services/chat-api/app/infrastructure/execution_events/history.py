from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .legacy_history import LegacyHistoryImporter


def import_legacy_events(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    importer = LegacyHistoryImporter()
    converted: List[Dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if int(event.get("v") or 0) == 3:
            converted.append(dict(event))
        else:
            converted.extend(importer.translate(event))
    return converted


def validate_legacy_import(source: Iterable[Dict[str, Any]], converted: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    source_list = list(source)
    converted_list = list(converted)
    source_text = "".join(
        str((event.get("payload") or {}).get("text") or "")
        for event in source_list
        if event.get("type") == "text.delta"
    )
    completed_answers = [
        event for event in converted_list
        if event.get("type") == "item.completed" and event.get("item_kind") == "final_answer"
    ]
    converted_text = str((completed_answers[-1].get("payload") or {}).get("text") or "") if completed_answers else ""
    return {
        "valid": source_text == converted_text if source_text else True,
        "source_event_count": len(source_list),
        "converted_event_count": len(converted_list),
        "final_answer_matches": source_text == converted_text,
    }


def normalize_execution_history(
    events: Iterable[Dict[str, Any]] | None,
    *,
    resequence: bool = False,
) -> List[Dict[str, Any]]:
    """Return one V3 history contract from current or legacy persistence."""
    normalized = [dict(event) for event in list(events or []) if isinstance(event, dict)]
    if any(int(event.get("v") or 0) != 3 for event in normalized):
        normalized = import_legacy_events(normalized)
    if resequence:
        for sequence, event in enumerate(normalized, start=1):
            event["stream_seq"] = sequence
            event["stream_seq_end"] = sequence
    return normalized
