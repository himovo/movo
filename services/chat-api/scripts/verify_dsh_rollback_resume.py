#!/usr/bin/env python3
"""Verify that a session created by the rollback train resumes on the active DSH."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import yaml

from dsh_upgrade.checks import cross_version_session, verify_installed_release_train
from dsh_upgrade.process import run_command
from dsh_upgrade.workspace import CandidateWorkspace


def executable(value: str) -> str:
    resolved = shutil.which(value)
    if resolved is None:
        raise ValueError(f"executable not found: {value}")
    return resolved


def configured_rollback_release(chat_api_root: Path) -> str:
    matrix_path = chat_api_root / "dsh" / "compatibility-matrix.yaml"
    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    releases = [
        str(row["dsh_release_train"])
        for row in matrix.get("supported_releases", [])
        if row.get("status") == "rollback"
    ]
    if len(releases) != 1:
        raise ValueError("compatibility matrix must declare exactly one rollback release")
    return releases[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", nargs="?", help="exact DSH version used by the rollback release")
    parser.add_argument("--node", default="node")
    parser.add_argument("--pnpm", default="pnpm")
    args = parser.parse_args()
    chat_api_root = Path(__file__).resolve().parents[1]
    active_host = chat_api_root / "dsh" / "runtime-host"
    baseline = args.baseline or configured_rollback_release(chat_api_root)

    with CandidateWorkspace(active_host, baseline) as rollback_host:
        install = run_command(
            "rollback_install",
            [executable(args.pnpm), "install", "--lockfile=false", "--ignore-scripts", "--registry=https://registry.npmjs.org"],
            cwd=rollback_host,
            timeout=300,
        )
        train, installed = verify_installed_release_train(rollback_host, baseline)
        result = cross_version_session(rollback_host, active_host, executable(args.node)) if install.passed and train.passed else {
            "checks": [], "created": False, "resumed": False,
        }
        payload = {
            "baseline": baseline,
            "install": install.to_dict(),
            "release_train": train.to_dict(),
            "installed": installed,
            "resume": {
                "created": result["created"],
                "resumed": result["resumed"],
                "checks": [check.to_dict() for check in result["checks"]],
                "baseline_session": result.get("baseline_session"),
                "active_session": result.get("candidate_session"),
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if install.passed and train.passed and result["created"] and result["resumed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
