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
PRIVATE_DEPLOYMENT_PATTERNS = (
    (
        re.compile(r"(?i)https?://(?:[a-z0-9-]+\.)*askbot\.cn\b"),
        "AskBot deployment URL",
    ),
    (re.compile(r"(?i)https?://askbot\d+\.openai\.azure\.com\b"), "private Azure OpenAI endpoint"),
    (re.compile(r"(?i)registry-vpc\.[^\s/]+/guoran\b"), "private container registry"),
    (re.compile(r"(?i)[\w.+-]+@(?:guoranbot|askbot)\.com\b"), "private organization email"),
)
SECRET_PATTERNS = (
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"\bLTAI[A-Za-z0-9]{12,}\b"), "Alibaba Cloud access key"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "OpenAI-compatible API key"),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        "JWT",
    ),
    (
        re.compile(
            r"(?i)\b(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis)://"
            r"[^\s:/]+:[^\s@/]+@"
        ),
        "credential-bearing connection URI",
    ),
)
ENV_SECRET_PATTERN = re.compile(
    r"(?im)^[ \t]*[A-Z0-9_]*(?:API_KEY|ACCESS_KEY_ID|ACCESS_KEY_SECRET|"
    r"CLIENT_SECRET|JWT_SECRET|PASSWORD|TOKEN)[ \t]*=[ \t]*"
    r"(?![ \t]*(?:$|<[^>]+>|change-me|your-|example|dummy|test))[^\s#]{16,}"
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


def publication_files() -> list[str]:
    """Return tracked and untracked, non-ignored files that a release could include."""
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
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
    for relative in publication_files():
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
        for pattern, label in PRIVATE_DEPLOYMENT_PATTERNS:
            if pattern.search(content):
                failures.append(f"{label}: {relative}")
        for pattern, label in SECRET_PATTERNS:
            if pattern.search(content):
                failures.append(f"possible {label}: {relative}")
        if name == ".env.example" and ENV_SECRET_PATTERN.search(content):
            failures.append(f"non-placeholder environment secret: {relative}")

    if failures:
        print("Open-source hygiene check failed:")
        for item in sorted(set(failures)):
            print(f"- {item}")
        return 1
    print("Open-source hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
