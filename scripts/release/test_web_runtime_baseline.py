#!/usr/bin/env python3

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.check_web_runtime_baseline import (
    WEB_DOCKERFILES,
    final_base_image,
    validate_web_runtime_baseline,
)


class WebRuntimeBaselineTest(unittest.TestCase):
    def write_dockerfiles(self, root: Path, images: tuple[str, ...]) -> None:
        for dockerfile, image in zip(WEB_DOCKERFILES, images, strict=True):
            path = root / dockerfile
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f"FROM {image}\n"
                "RUN apt-get install -y --no-install-recommends curl wget\n",
                encoding="utf-8",
            )

    def test_accepts_one_debian_glibc_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_dockerfiles(root, ("nginx:1.31.5-trixie",) * 3)
            self.assertEqual([], validate_web_runtime_baseline(root))

    def test_rejects_runtime_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_dockerfiles(
                root,
                (
                    "nginx:1.31.5-trixie",
                    "nginx:1.29.8-alpine",
                    "nginx:1.31.5-trixie",
                ),
            )
            errors = validate_web_runtime_baseline(root)
            self.assertEqual(1, len(errors))
            self.assertIn("must match exactly", errors[0])

    def test_rejects_aligned_alpine_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_dockerfiles(root, ("nginx:1.31.5-alpine3.24-slim",) * 3)
            errors = validate_web_runtime_baseline(root)
            self.assertEqual(1, len(errors))
            self.assertIn("Debian/glibc", errors[0])

    def test_rejects_missing_legacy_healthcheck_tool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_dockerfiles(root, ("nginx:1.31.6-trixie",) * 3)
            (root / WEB_DOCKERFILES[1]).write_text(
                "FROM nginx:1.31.6-trixie\n"
                "RUN apt-get install -y --no-install-recommends curl\n",
                encoding="utf-8",
            )
            errors = validate_web_runtime_baseline(root)
            self.assertEqual(1, len(errors))
            self.assertIn("legacy Compose health checks", errors[0])

    def test_uses_final_stage_for_multi_stage_dockerfile(self) -> None:
        self.assertEqual(
            "nginx:1.31.5-trixie",
            final_base_image(
                "FROM node:20-slim AS build\nFROM nginx:1.31.5-trixie\n",
                Path("Dockerfile"),
            ),
        )

    def test_resolves_default_for_overridable_runtime(self) -> None:
        self.assertEqual(
            "nginx:1.31.6-trixie",
            final_base_image(
                "ARG NGINX_RUNTIME_IMAGE=nginx:1.31.6-trixie\n"
                "FROM ${NGINX_RUNTIME_IMAGE}\n",
                Path("Dockerfile"),
            ),
        )

    def test_rejects_runtime_argument_without_default(self) -> None:
        with self.assertRaisesRegex(ValueError, "has no default"):
            final_base_image(
                "ARG NGINX_RUNTIME_IMAGE\nFROM ${NGINX_RUNTIME_IMAGE}\n",
                Path("Dockerfile"),
            )


if __name__ == "__main__":
    unittest.main()
