"""The server conversation directory reserved for one turn's final files."""

from pathlib import Path
from typing import Any

from app.execution_isolation.personal_space import conversation_space_key
from app.execution_isolation.script_backend import task_key


def turn_output_path(message_id: str) -> Path:
    return Path("deliverables") / task_key(message_id)


def turn_output_prompt(binding: dict[str, Any], message_id: str) -> str:
    if binding.get("execution_location") != "server":
        return ""
    directory = (
        Path("/job/home/conversations")
        / conversation_space_key(str(binding["conversation_id"]))
        / turn_output_path(message_id)
    )
    return (
        f"\n\n[MOVO file delivery] For final files created with DSH workspace tools, "
        f"create and use this turn's delivery directory: {directory}. "
        "Put only completed files for the user there and call present for them. "
        "Keep drafts and temporary files elsewhere. For run_script, use its own output_dir."
    )


def turn_output_files(conversation: Path, message_id: str) -> list[Path]:
    root = conversation.resolve()
    directory = root / turn_output_path(message_id)
    if directory.parent.is_symlink() or directory.is_symlink() or not directory.is_dir():
        return []
    return sorted(
        path for path in directory.rglob("*")
        if not path.is_symlink() and path.resolve() == path and path.is_file()
    )
