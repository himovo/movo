from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .models import CommandResult
from .process import run_command


def last_json(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("probe produced no JSON object")


def verify_artifact(root: Path, package, npm: str) -> tuple[CommandResult, dict[str, Any]]:
    artifact_dir = root / ".candidate-artifact"
    artifact_dir.mkdir()
    result = run_command(
        "candidate_artifact_integrity",
        [
            npm, "pack", f"{package.name}@{package.version}", "--json", "--ignore-scripts",
            "--registry=https://registry.npmjs.org",
        ],
        cwd=artifact_dir,
        timeout=120,
    )
    evidence: dict[str, Any] = {}
    if result.passed:
        try:
            packed = json.loads(result.stdout)[0]
            evidence = {
                "filename": packed.get("filename"),
                "integrity": packed.get("integrity"),
                "shasum": packed.get("shasum"),
            }
            if (
                evidence["integrity"] != package.dist.get("integrity")
                or evidence["shasum"] != package.dist.get("shasum")
            ):
                result = CommandResult(
                    name=result.name, command=result.command, returncode=2,
                    duration_seconds=result.duration_seconds, stdout=result.stdout,
                    stderr="npm pack evidence differs from registry metadata",
                )
        except (IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
            result = CommandResult(
                name=result.name, command=result.command, returncode=2,
                duration_seconds=result.duration_seconds, stdout=result.stdout,
                stderr=f"invalid npm pack evidence: {error}",
            )
    evidence["verified"] = result.passed
    return result, evidence


def verify_installed_release_train(root: Path, expected: str) -> tuple[CommandResult, dict[str, list[str]]]:
    versions: dict[str, set[str]] = {}
    for path in (root / "node_modules" / ".pnpm").glob("*/node_modules/@deepseek-ai/dsh*/package.json"):
        package = json.loads(path.read_text(encoding="utf-8"))
        name = str(package.get("name") or "")
        if name == "@deepseek-ai/dsh" or name.startswith("@deepseek-ai/dsh-"):
            versions.setdefault(name, set()).add(str(package.get("version") or ""))
    normalized = {name: sorted(values) for name, values in sorted(versions.items())}
    mismatched = {name: values for name, values in normalized.items() if values != [expected]}
    passed = bool(normalized) and not mismatched
    return CommandResult(
        name="candidate_single_release_train",
        command=[],
        returncode=0 if passed else 2,
        duration_seconds=0,
        stdout=json.dumps(normalized, ensure_ascii=False),
        stderr="" if passed else f"mixed DSH release train: {mismatched}",
    ), normalized


def inventory(name: str, root: Path, node: str) -> tuple[CommandResult, dict[str, Any]]:
    result = run_command(
        name, [node, str(root / "scripts" / "runtime-inventory-probe.mjs")],
        cwd=root, timeout=60,
    )
    if not result.passed:
        return result, {}
    try:
        return result, last_json(result.stdout)
    except ValueError as error:
        return CommandResult(
            name=result.name, command=result.command, returncode=2,
            duration_seconds=result.duration_seconds, stdout=result.stdout,
            stderr=f"{result.stderr}\n{error}",
        ), {}


def cross_version_session(host_root: Path, candidate_root: Path, node: str) -> dict[str, Any]:
    session_root = Path(tempfile.mkdtemp(prefix="askai-dsh-session-probe-"))
    arguments = [
        "--storage-root", str(session_root),
        "--session-id", "upgrade-cross-version-code",
        "--isolation-key", "upgrade:cross-version",
    ]
    try:
        create = run_command(
            "baseline_session_create",
            [node, str(host_root / "scripts" / "session-compatibility-probe.mjs"), "--mode", "create", *arguments],
            cwd=host_root, timeout=60,
        )
        resume = run_command(
            "candidate_session_resume",
            [node, str(candidate_root / "scripts" / "session-compatibility-probe.mjs"), "--mode", "resume", *arguments],
            cwd=candidate_root, timeout=60,
        ) if create.passed else CommandResult(
            name="candidate_session_resume", command=[], returncode=125,
            duration_seconds=0, stdout="", stderr="baseline session creation failed",
        )
        created_payload = last_json(create.stdout) if create.passed else {}
        resumed_payload = last_json(resume.stdout) if resume.passed else {}
        return {
            "checks": [create, resume],
            "created": bool(created_payload.get("ok")),
            "resumed": bool(resumed_payload.get("ok")),
            "baseline_session": created_payload.get("session"),
            "candidate_session": resumed_payload.get("session"),
        }
    finally:
        shutil.rmtree(session_root, ignore_errors=True)
