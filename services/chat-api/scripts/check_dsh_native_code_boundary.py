from __future__ import annotations

import argparse
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


LEGACY_TOKENS = (
    "local-code-agent",
    "CodeAgentSidecar",
    "LocalCodeBridge",
    "coding.local_task",
    "code_task",
    "/code-agent/connect",
    "ASKAI_CODE_BACKEND_WS",
    "ASKAI_CODE_WORKSPACE_ROOTS",
)

SCANNED_SUFFIXES = {
    ".cjs", ".js", ".json", ".md", ".mjs", ".py", ".ts", ".tsx", ".vue", ".yaml", ".yml",
}

SKIPPED_DIRECTORIES = {
    ".git", ".idea", ".venv", ".vscode", "__pycache__", "dist", "docs", "node_modules", "tests", "venv",
}

SKIPPED_FILES = {
    "services/chat-api/scripts/check_dsh_native_code_boundary.py",
}


@dataclass(frozen=True)
class Occurrence:
    path: str
    token: str


def iter_source_files(root: Path) -> Iterable[Path]:
    for current, directories, filenames in os.walk(root):
        directories[:] = sorted(name for name in directories if name not in SKIPPED_DIRECTORIES)
        current_path = Path(current)
        for filename in sorted(filenames):
            path = current_path / filename
            if path.suffix.lower() not in SCANNED_SUFFIXES:
                continue
            relative = path.relative_to(root)
            if relative.as_posix() in SKIPPED_FILES or ".test." in path.name:
                continue
            yield path


def scan_occurrences(root: Path) -> Counter[Occurrence]:
    found: Counter[Occurrence] = Counter()
    for path in iter_source_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        relative = path.relative_to(root).as_posix()
        for token in LEGACY_TOKENS:
            count = text.count(token)
            if count:
                found[Occurrence(relative, token)] = count
    return found


def violations(found: Counter[Occurrence], allowed: Counter[Occurrence]) -> list[str]:
    failures: list[str] = []
    for occurrence, count in sorted(found.items(), key=lambda item: (item[0].path, item[0].token)):
        maximum = allowed.get(occurrence, 0)
        if count > maximum:
            failures.append(
                f"{occurrence.path}: {occurrence.token!r} occurs {count} time(s), allowed {maximum}"
            )
    return failures


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Reject every production reference to the retired legacy Code Agent.")
    parser.add_argument("--root", type=Path, default=repo_root)
    args = parser.parse_args()
    # Community releases permit no production exceptions, so a historical
    # migration baseline is neither required nor accepted.
    failures = violations(scan_occurrences(args.root.resolve()), Counter())
    if failures:
        print("DSH native Code boundary guard failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("DSH native Code boundary guard passed: the retired legacy Code Agent has zero production references.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
