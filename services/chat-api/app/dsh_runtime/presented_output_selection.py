"""Resolve DSH present declarations to files in one server conversation."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from app.execution_isolation.personal_space import conversation_space_key


def selected_paths(events: list[dict[str, Any]], conversation: Path, conversation_id: str) -> list[Path]:
    key = conversation_space_key(conversation_id)
    runtime_root = PurePosixPath('/job/home/conversations') / key
    selected: list[Path] = []
    seen: set[Path] = set()
    for event in events:
        if event.get('source', {}).get('native_event_type') != 'deliverables/presented':
            continue
        for item in event.get('payload', {}).get('files', []):
            if not isinstance(item, dict) or not isinstance(item.get('path'), str):
                continue
            declared = PurePosixPath(item['path'])
            try:
                relative = declared.relative_to(runtime_root) if declared.is_absolute() else declared
            except ValueError:
                continue
            if not relative.parts or '..' in relative.parts:
                continue
            candidate = conversation.joinpath(*relative.parts)
            try:
                resolved = candidate.resolve(strict=True)
                if not resolved.is_relative_to(conversation.resolve()) or not resolved.is_file():
                    continue
            except (OSError, RuntimeError):
                continue
            if resolved not in seen:
                seen.add(resolved)
                selected.append(resolved)
    return selected
