#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLOCKED_PARTS = (
    "services/chat-api/storage/",
    "services/admin-api/data/admin-static/",
    "apps/official-website/docs/.vitepress/cache/",
)
PRIVATE_MARKERS = (
    "master.test.askbot.cn",
    "askbot2.openai.azure.com",
    "agentic_register@mail.guoranbot.com",
)


def tracked_files() -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files"], cwd=ROOT, text=True, encoding="utf-8"
    )
    return [item for item in output.splitlines() if item and (ROOT / item).exists()]


def main() -> int:
    failures: list[str] = []
    for relative in tracked_files():
        if relative == "scripts/check_open_source_hygiene.py":
            continue
        normalized = relative.replace("\\", "/")
        name = Path(relative).name
        if name.startswith(".env") and name != ".env.example":
            failures.append(f"tracked environment file: {relative}")
        if any(part in normalized for part in BLOCKED_PARTS):
            failures.append(f"tracked generated/runtime data: {relative}")

        path = ROOT / relative
        if path.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for marker in PRIVATE_MARKERS:
            if marker in content:
                failures.append(f"private deployment marker {marker!r}: {relative}")

    if failures:
        print("Open-source hygiene check failed:")
        for item in sorted(set(failures)):
            print(f"- {item}")
        return 1
    print("Open-source hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
