#!/usr/bin/env python3
"""Prevent MOVO's three public web images from drifting across runtimes."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WEB_DOCKERFILES = (
    Path("apps/user-web/Dockerfile.prod"),
    Path("apps/admin-web/Dockerfile"),
    Path("deploy/docker/gateway.Dockerfile"),
)
SUPPORTED_RUNTIME_SUFFIX = "-trixie"
FROM_PATTERN = re.compile(r"^\s*FROM\s+([^\s]+)", re.IGNORECASE | re.MULTILINE)
ARG_PATTERN = re.compile(
    r"^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)", re.IGNORECASE | re.MULTILINE
)
HEALTH_TOOLS_PATTERN = re.compile(
    r"apt-get\s+install\s+-y\s+--no-install-recommends\s+curl\s+wget\b"
)


def final_base_image(contents: str, dockerfile: Path) -> str:
    images = FROM_PATTERN.findall(contents)
    if not images:
        raise ValueError(f"{dockerfile}: no FROM instruction found")
    image = images[-1]
    match = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", image)
    if not match:
        return image
    defaults = dict(ARG_PATTERN.findall(contents))
    try:
        return defaults[match.group(1)]
    except KeyError as exc:
        raise ValueError(
            f"{dockerfile}: final FROM argument {match.group(1)} has no default"
        ) from exc


def validate_web_runtime_baseline(
    repository_root: Path = REPOSITORY_ROOT,
    dockerfiles: Iterable[Path] = WEB_DOCKERFILES,
) -> list[str]:
    resolved = tuple(dockerfiles)
    runtimes = {
        dockerfile: final_base_image(
            (repository_root / dockerfile).read_text(encoding="utf-8"), dockerfile
        )
        for dockerfile in resolved
    }
    errors: list[str] = []
    distinct = set(runtimes.values())
    if len(distinct) != 1:
        details = ", ".join(
            f"{dockerfile}={runtime}" for dockerfile, runtime in runtimes.items()
        )
        errors.append(f"web runtime images must match exactly: {details}")
        return errors

    runtime = next(iter(distinct))
    if not runtime.startswith("nginx:") or not runtime.endswith(
        SUPPORTED_RUNTIME_SUFFIX
    ):
        errors.append(
            "web runtime must use the pinned official Debian/glibc nginx baseline "
            f"(*{SUPPORTED_RUNTIME_SUFFIX}); found {runtime}"
        )
    for dockerfile in resolved:
        contents = (repository_root / dockerfile).read_text(encoding="utf-8")
        if not HEALTH_TOOLS_PATTERN.search(contents):
            errors.append(
                f"{dockerfile}: web runtime must include curl and wget for "
                "current and legacy Compose health checks"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="repository root containing the three Dockerfiles",
    )
    args = parser.parse_args()
    errors = validate_web_runtime_baseline(args.repository_root.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    runtime = final_base_image(
        (args.repository_root / WEB_DOCKERFILES[0]).read_text(encoding="utf-8"),
        WEB_DOCKERFILES[0],
    )
    print(f"Web runtime baseline is aligned: {runtime}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
