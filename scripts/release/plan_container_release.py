#!/usr/bin/env python3
"""Plan the smallest safe MOVO container release for a Git diff."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable


@dataclass(frozen=True)
class ImageDefinition:
    suffix: str
    context: str
    dockerfile: str
    build_args: str = ""
    inputs: tuple[str, ...] = ()

    def matrix_entry(self) -> dict[str, str]:
        return {
            "suffix": self.suffix,
            "context": self.context,
            "dockerfile": self.dockerfile,
            "build_args": self.build_args,
        }


IMAGES = (
    ImageDefinition(
        suffix="dsh-runtime-host",
        context="services/chat-api/dsh/runtime-host",
        dockerfile="services/chat-api/dsh/runtime-host/Dockerfile",
        inputs=("services/chat-api/dsh/runtime-host/**",),
    ),
    ImageDefinition(
        suffix="chat-api",
        context="services/chat-api",
        dockerfile="services/chat-api/Dockerfile",
        build_args=(
            "INSTALL_SYSTEM_DEPS_AT_BUILD=true\n"
            "INSTALL_PLAYWRIGHT_AT_BUILD=true\n"
            "PLAYWRIGHT_WITH_DEPS=true"
        ),
        inputs=(
            "services/chat-api/Dockerfile",
            "services/chat-api/entrypoint.sh",
            "services/chat-api/requirements.txt",
            "services/chat-api/.env.example",
            "services/chat-api/app/**",
        ),
    ),
    ImageDefinition(
        suffix="admin-api",
        context="services/admin-api",
        dockerfile="services/admin-api/Dockerfile",
        inputs=(
            "services/admin-api/Dockerfile",
            "services/admin-api/entrypoint.sh",
            "services/admin-api/requirements.txt",
            "services/admin-api/app/**",
        ),
    ),
    ImageDefinition(
        suffix="document-parser",
        context="services/document-parser",
        dockerfile="services/document-parser/Dockerfile",
        build_args=(
            "INSTALL_SYSTEM_DEPS_AT_BUILD=true\n"
            "INSTALL_PYTHON_DEPS_AT_BUILD=true\n"
            "INSTALL_DOCLING_MODELS_AT_BUILD=true\n"
            "PYTORCH_ACCELERATOR=cpu"
        ),
        inputs=("services/document-parser/**",),
    ),
    ImageDefinition(
        suffix="user-web",
        context="apps/user-web",
        dockerfile="apps/user-web/Dockerfile.prod",
        build_args="VITE_ADMIN_WEB_URL=/admin/",
        inputs=("apps/user-web/**",),
    ),
    ImageDefinition(
        suffix="admin-web",
        context="apps/admin-web",
        dockerfile="apps/admin-web/Dockerfile",
        build_args="VITE_BASE_PATH=/admin/\nVITE_ADMIN_API_BASE_URL=/admin-api",
        inputs=("apps/admin-web/**",),
    ),
    ImageDefinition(
        suffix="gateway",
        context="deploy/docker",
        dockerfile="deploy/docker/gateway.Dockerfile",
        inputs=("deploy/docker/gateway.Dockerfile",),
    ),
)

# A release mechanism change invalidates the planner itself, so the next release
# deliberately rebuilds every image once.
GLOBAL_INPUTS = (
    ".github/workflows/container-release.yml",
    "scripts/release/plan_container_release.py",
)


def _matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-3].rstrip("/") + "/")
    return PurePosixPath(path).match(pattern)


def select_images(
    changed_paths: Iterable[str], force_all: bool = False
) -> tuple[list[ImageDefinition], list[ImageDefinition]]:
    paths = tuple(path.strip() for path in changed_paths if path.strip())
    rebuild_all = force_all or any(
        _matches(path, pattern) for path in paths for pattern in GLOBAL_INPUTS
    )
    changed: list[ImageDefinition] = []
    unchanged: list[ImageDefinition] = []
    for image in IMAGES:
        affected = rebuild_all or any(
            _matches(path, pattern) for path in paths for pattern in image.inputs
        )
        (changed if affected else unchanged).append(image)
    return changed, unchanged


def git_changed_paths(base_ref: str, head_ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "-z", base_ref, head_ref],
        check=True,
        stdout=subprocess.PIPE,
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def build_plan(
    base_ref: str | None, head_ref: str, force_all: bool = False
) -> dict[str, object]:
    paths = git_changed_paths(base_ref, head_ref) if base_ref and not force_all else []
    changed, unchanged = select_images(paths, force_all=force_all or not base_ref)
    return {
        "base_ref": base_ref or "",
        "changed_paths": paths,
        "changed": [image.matrix_entry() for image in changed],
        "unchanged": [image.matrix_entry() for image in unchanged],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--force-all", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build_plan(args.base_ref, args.head_ref, args.force_all), separators=(",", ":")))


if __name__ == "__main__":
    main()
