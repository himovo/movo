from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def set_delta(before: list[str], after: list[str]) -> dict[str, list[str]]:
    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "unchanged_count": len(set(before) & set(after)),
    }


def dependency_delta(before: dict[str, str], after: dict[str, str]) -> dict[str, Any]:
    names = sorted(set(before) | set(after))
    changed = {
        name: {"before": before.get(name), "after": after.get(name)}
        for name in names
        if before.get(name) != after.get(name) and name in before and name in after
    }
    return {
        **set_delta(list(before), list(after)),
        "version_changes": changed,
    }


def public_api_delta(baseline_root: Path, candidate_root: Path, package_names: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in package_names:
        relative = Path("node_modules") / Path(*name.split("/")) / "package.json"
        baseline_path = baseline_root / relative
        candidate_path = candidate_root / relative
        if not baseline_path.exists() or not candidate_path.exists():
            result[name] = {"missing": True}
            continue
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        before_exports = baseline.get("exports") or {}
        after_exports = candidate.get("exports") or {}
        before = list(before_exports) if isinstance(before_exports, dict) else ["."]
        after = list(after_exports) if isinstance(after_exports, dict) else ["."]
        result[name] = {
            "baseline_version": baseline.get("version"),
            "candidate_version": candidate.get("version"),
            **set_delta(before, after),
        }
    return result


def capability_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    def contracts(preset: str, surface: str) -> dict[str, Any]:
        before_rows = before["presets"][preset].get("toolContracts", {}).get(surface, [])
        after_rows = after["presets"][preset].get("toolContracts", {}).get(surface, [])
        before_by_name = {row["name"]: row for row in before_rows}
        after_by_name = {row["name"]: row for row in after_rows}
        return {
            name: {"before": before_by_name[name], "after": after_by_name[name]}
            for name in sorted(set(before_by_name) & set(after_by_name))
            if before_by_name[name] != after_by_name[name]
        }

    return {
        "enabled_modules": set_delta(before["enabledModules"], after["enabledModules"]),
        "ordinary_model_tools": set_delta(
            before["presets"]["ordinary"]["modelTools"],
            after["presets"]["ordinary"]["modelTools"],
        ),
        "ordinary_capability_tools": set_delta(
            before["presets"]["ordinary"]["capabilityTools"],
            after["presets"]["ordinary"]["capabilityTools"],
        ),
        "code_model_tools": set_delta(
            before["presets"]["code"]["modelTools"],
            after["presets"]["code"]["modelTools"],
        ),
        "code_capability_tools": set_delta(
            before["presets"]["code"]["capabilityTools"],
            after["presets"]["code"]["capabilityTools"],
        ),
        "ordinary_model_tool_contract_changes": contracts("ordinary", "modelTools"),
        "ordinary_capability_tool_contract_changes": contracts("ordinary", "capabilityTools"),
        "code_model_tool_contract_changes": contracts("code", "modelTools"),
        "code_capability_tool_contract_changes": contracts("code", "capabilityTools"),
    }
