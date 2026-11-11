#!/usr/bin/env python3
"""Retry an APT operation against independent Debian mirrors.

Each attempt refreshes package indexes from one coherent source set. APT's
download retries alone cannot recover from an out-of-sync mirror index.
"""

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


SOURCE_FILES = (
    Path("/etc/apt/sources.list"),
    Path("/etc/apt/sources.list.d/debian.sources"),
)
INDEX_DIR = Path("/var/lib/apt/lists")
FALLBACKS = (
    ("Aliyun", "https://mirrors.aliyun.com/debian", "https://mirrors.aliyun.com/debian-security"),
    ("TUNA", "https://mirrors.tuna.tsinghua.edu.cn/debian", "https://mirrors.tuna.tsinghua.edu.cn/debian-security"),
    ("Debian", "http://deb.debian.org/debian", "http://deb.debian.org/debian-security"),
)
DEBIAN_URL = re.compile(r"https?://[^\s]+/debian(?:-security)?(?=\s|$)")


def replace_mirror(source: str, main: str, security: str) -> str:
    def replacement(match: re.Match[str]) -> str:
        return security if match.group().endswith("/debian-security") else main

    return DEBIAN_URL.sub(replacement, source)


def run_apt(*args: str) -> None:
    subprocess.run(
        ["apt-get", "-o", "Acquire::Retries=3", "-o", "Acquire::http::Timeout=30",
         "-o", "Acquire::https::Timeout=30", *args],
        env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
        check=True,
    )


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("install", "upgrade"):
        print("Usage: apt_with_mirror_fallback.py install <packages...> | upgrade", file=sys.stderr)
        return 2
    if sys.argv[1] == "install" and len(sys.argv) < 3:
        return 2

    originals = {path: path.read_text() for path in SOURCE_FILES if path.exists()}
    if not originals:
        print("No Debian APT source file found", file=sys.stderr)
        return 2

    configured_main = os.environ.get("MOVO_APT_MIRROR", "").rstrip("/")
    configured_security = os.environ.get("MOVO_APT_SECURITY_MIRROR", "").rstrip("/")
    candidates = [("configured", configured_main, configured_security)] if configured_main else []
    candidates += list(FALLBACKS)
    if not configured_main:
        candidates.insert(0, candidates.pop())

    seen = set()
    attempts = []
    for candidate in candidates:
        if candidate[1:] not in seen:
            attempts.append(candidate)
            seen.add(candidate[1:])

    try:
        for number, (name, main_url, security_url) in enumerate(attempts, 1):
            print(f"[apt-mirror] Attempt {number}/{len(attempts)} with {name}: {main_url}", flush=True)
            for path, original in originals.items():
                path.write_text(replace_mirror(original, main_url, security_url or "http://deb.debian.org/debian-security"))
            if INDEX_DIR.exists():
                shutil.rmtree(INDEX_DIR)
            INDEX_DIR.mkdir(parents=True, exist_ok=True)
            try:
                run_apt("update")
                if sys.argv[1] == "install":
                    run_apt("install", "-y", "--no-install-recommends", *sys.argv[2:])
                else:
                    run_apt("upgrade", "-y")
                print(f"[apt-mirror] Completed with {name}", flush=True)
                return 0
            except subprocess.CalledProcessError as exc:
                print(f"[apt-mirror] {name} failed (exit {exc.returncode}); switching mirror", file=sys.stderr, flush=True)
                if number < len(attempts):
                    time.sleep(5)
    finally:
        for path, original in originals.items():
            path.write_text(original)
        if INDEX_DIR.exists():
            shutil.rmtree(INDEX_DIR)
    return 1


if __name__ == "__main__":
    sys.exit(main())
