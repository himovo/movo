"""Keep completed script output files in the user's durable conversation space."""

from __future__ import annotations

from pathlib import Path

from app.execution_isolation.personal_files import atomic_personal_copy, require_personal_parent
from app.execution_isolation.personal_space import ensure_personal_capacity


MAX_SAVED_BYTES = 512 * 1024 * 1024


def save_outputs(output_dir: Path, conversation_dir: Path, call_id: str) -> None:
    destination = conversation_dir / "outputs" / call_id
    personal_root = conversation_dir.parents[1]
    require_personal_parent(personal_root, destination.parent)
    total = 0
    sources: list[Path] = []
    for source in output_dir.rglob("*"):
        if source.is_symlink() or not source.is_file():
            continue
        total += source.stat().st_size
        if total > MAX_SAVED_BYTES:
            raise ValueError("Script outputs exceed the personal space limit")
        sources.append(source)
    if not sources:
        return
    ensure_personal_capacity(personal_root, total)
    destination.mkdir(parents=True, exist_ok=True)
    require_personal_parent(personal_root, destination)
    destination.parent.chmod(0o777)
    destination.chmod(0o777)
    for source in sources:
        target = destination / source.relative_to(output_dir)
        require_personal_parent(personal_root, target.parent)
        target.parent.mkdir(parents=True, exist_ok=True)
        require_personal_parent(personal_root, target.parent)
        target.parent.chmod(0o777)
        with source.open("rb") as input_file:
            atomic_personal_copy(personal_root, target, input_file)
