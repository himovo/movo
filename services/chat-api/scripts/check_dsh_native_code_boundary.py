from __future__ import annotations

import argparse
import json
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


def load_allowance(path: Path) -> Counter[Occurrence]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "askai.dsh-native-code-retired.v2":
        raise ValueError(f"unsupported baseline schema: {payload.get('schema_version')!r}")
    if payload.get("allowed_occurrences"):
        raise ValueError("retired ASKAI Code Agent production allowances must remain empty")
    allowed: Counter[Occurrence] = Counter()
    for item in payload.get("allowed_occurrences", []):
        occurrence = Occurrence(str(item["path"]), str(item["token"]))
        count = int(item["max_count"])
        if count < 0 or occurrence.token not in LEGACY_TOKENS:
            raise ValueError(f"invalid allowance: {item!r}")
        if occurrence in allowed:
            raise ValueError(f"duplicate allowance: {item!r}")
        allowed[occurrence] = count
    return allowed


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
    parser = argparse.ArgumentParser(description="Reject every production reference to the retired ASKAI Code Agent.")
    parser.add_argument("--root", type=Path, default=repo_root)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=repo_root / "docs" / "dsh-native-code-legacy-baseline.json",
    )
    args = parser.parse_args()
    failures = violations(scan_occurrences(args.root.resolve()), load_allowance(args.baseline.resolve()))
    if failures:
        print("DSH native Code boundary guard failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("DSH native Code boundary guard passed: the retired ASKAI Code Agent has zero production references.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
