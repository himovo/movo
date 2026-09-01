#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLOCKED_PARTS = (
    "services/chat-api/storage/",
    "services/admin-api/data/admin-static/",
    "apps/official-website/docs/.vitepress/cache/",
)
BLOCKED_PREFIXES = (
    "apps/desktop-electron/",
    "apps/local-browser-agent/",
    "apps/official-website/",
    "apps/crm/",
    "services/crm-service/",
)
PRIVATE_MARKERS = (
    "master.test.askbot.cn",
    "askbot2.openai.azure.com",
    "agentic_register@mail.guoranbot.com",
)
SECRET_PATTERNS = (
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
)
REQUIRED_ROOT_FILES = (
    "LICENSE",
    "NOTICE",
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "SUPPORT.md",
    "CODE_OF_CONDUCT.md",
)
EXPECTED_MOVO_VOLUMES = 8


def tracked_files() -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files"], cwd=ROOT, text=True, encoding="utf-8"
    )
    return [item for item in output.splitlines() if item and (ROOT / item).exists()]


def main() -> int:
    failures: list[str] = []
    tracked = tracked_files()
    tracked_set = set(tracked)
    for required in REQUIRED_ROOT_FILES:
        if required not in tracked_set:
            failures.append(f"required publication file is not tracked: {required}")

    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    if re.search(r"^\s*name:\s*askai_", compose_text, flags=re.MULTILINE):
        failures.append("Compose reuses an AskAI physical volume name")
    volume_prefix_count = compose_text.count("${MOVO_VOLUME_PREFIX:-movo}_")
    if volume_prefix_count != EXPECTED_MOVO_VOLUMES:
        failures.append(
            "Compose must define exactly "
            f"{EXPECTED_MOVO_VOLUMES} MOVO-prefixed physical volumes; "
            f"found {volume_prefix_count}"
        )
    for relative in tracked:
        if relative == "scripts/check_open_source_hygiene.py":
            continue
        normalized = relative.replace("\\", "/")
        name = Path(relative).name
        if normalized.startswith(BLOCKED_PREFIXES):
            failures.append(f"blocked non-community source: {relative}")
        if name.startswith(".env") and name != ".env.example":
            failures.append(f"tracked environment file: {relative}")
        if any(part in normalized for part in BLOCKED_PARTS):
            failures.append(f"tracked generated/runtime data: {relative}")

        path = ROOT / relative
        if path.is_symlink():
            try:
                path.resolve(strict=True).relative_to(ROOT.resolve())
            except (OSError, ValueError):
                failures.append(f"symlink escapes repository: {relative}")
            continue
        if path.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for marker in PRIVATE_MARKERS:
            if marker in content:
                failures.append(f"private deployment marker {marker!r}: {relative}")
        for pattern, label in SECRET_PATTERNS:
            if pattern.search(content):
                failures.append(f"possible {label}: {relative}")

    if failures:
        print("Open-source hygiene check failed:")
        for item in sorted(set(failures)):
            print(f"- {item}")
        return 1
    print("Open-source hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
