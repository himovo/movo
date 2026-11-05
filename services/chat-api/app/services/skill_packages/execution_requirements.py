"""Classify package execution requirements from install-time metadata."""

from typing import Any, Iterable


EXECUTION_TOOLS = frozenset({"run_script", "data.run_script@v1"})
EXECUTABLE_SUFFIXES = (".py", ".sh", ".js", ".mjs", ".ts")
EXECUTABLE_PATH_PATTERN = r"(^scripts/|^(requirements\.txt|package\.json|apt-packages\.txt)$|\.(py|sh|js|mjs|ts)$)"


def package_uses_execution(
    *, files: Iterable[dict[str, Any]], tools: Iterable[str], requires_environment: bool = False,
    declared_requirement: bool = False,
) -> bool:
    if declared_requirement or requires_environment or any(str(tool).strip() in EXECUTION_TOOLS for tool in tools):
        return True
    return any(
        str(item.get("path") or "").startswith("scripts/")
        or str(item.get("path") or "").endswith(EXECUTABLE_SUFFIXES)
        for item in files
    )
