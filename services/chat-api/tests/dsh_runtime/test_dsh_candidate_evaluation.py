from __future__ import annotations

import json
from pathlib import Path

from scripts.dsh_upgrade.diffing import capability_delta, dependency_delta, public_api_delta
from scripts.dsh_upgrade.checks import verify_installed_release_train
from scripts.dsh_upgrade.models import EvaluationReport
from scripts.dsh_upgrade.reporting import write_report
from scripts.dsh_upgrade.workspace import CandidateWorkspace


def test_dependency_delta_reports_add_remove_and_change() -> None:
    result = dependency_delta(
        {"same": "1", "changed": "1", "removed": "1"},
        {"same": "1", "changed": "2", "added": "1"},
    )
    assert result["added"] == ["added"]
    assert result["removed"] == ["removed"]
    assert result["version_changes"] == {"changed": {"before": "1", "after": "2"}}


def test_candidate_workspace_pins_only_dsh_train(tmp_path: Path) -> None:
    host = tmp_path / "host"
    for directory in ("src", "config", "tests", "scripts"):
        (host / directory).mkdir(parents=True)
    (host / "package.json").write_text(json.dumps({
        "dependencies": {
            "@deepseek-ai/dsh": "0.1.0-rc.6",
            "@deepseek-ai/dsh-agent": "0.1.0-rc.6",
            "@deepseek-ai/cordis": "4.0.1",
        },
    }), encoding="utf-8")
    (host / "src" / "host-protocol.mjs").write_text(
        "export const ASKAI_DSH_KERNEL_VERSION = '0.1.0-rc.6'\n", encoding="utf-8",
    )

    with CandidateWorkspace(host, "0.1.1-rc.2") as candidate:
        package = json.loads((candidate / "package.json").read_text(encoding="utf-8"))
        assert package["dependencies"]["@deepseek-ai/dsh"] == "0.1.1-rc.2"
        assert package["dependencies"]["@deepseek-ai/dsh-agent"] == "0.1.1-rc.2"
        assert package["dependencies"]["@deepseek-ai/cordis"] == "4.0.1"
        assert "0.1.1-rc.2" in (candidate / "src" / "host-protocol.mjs").read_text()
    assert host.exists()


def test_public_api_and_capability_delta_are_explicit(tmp_path: Path) -> None:
    before = tmp_path / "before"
    after = tmp_path / "after"
    relative = Path("node_modules/@deepseek-ai/dsh-agent/package.json")
    for root, exports in ((before, {".": {}, "./old": {}}), (after, {".": {}, "./new": {}})):
        (root / relative).parent.mkdir(parents=True)
        (root / relative).write_text(json.dumps({"version": "v", "exports": exports}), encoding="utf-8")
    api = public_api_delta(before, after, ["@deepseek-ai/dsh-agent"])
    assert api["@deepseek-ai/dsh-agent"]["added"] == ["./new"]
    assert api["@deepseek-ai/dsh-agent"]["removed"] == ["./old"]

    inventory_before = {
        "enabledModules": ["session"],
        "presets": {
            "ordinary": {"modelTools": [], "capabilityTools": []},
            "code": {"modelTools": ["run_code"], "capabilityTools": ["read"]},
        },
    }
    inventory_after = {
        "enabledModules": ["session", "new-module"],
        "presets": {
            "ordinary": {"modelTools": [], "capabilityTools": []},
            "code": {"modelTools": ["run_code"], "capabilityTools": ["read", "pwsh"]},
        },
    }
    capabilities = capability_delta(inventory_before, inventory_after)
    assert capabilities["enabled_modules"]["added"] == ["new-module"]
    assert capabilities["code_capability_tools"]["added"] == ["pwsh"]
    assert capabilities["ordinary_model_tool_contract_changes"] == {}


def test_capability_delta_reports_tool_schema_changes() -> None:
    base = {
        "enabledModules": [],
        "presets": {
            name: {"modelTools": ["web_search"], "capabilityTools": [], "toolContracts": {
                "modelTools": [{"name": "web_search", "schema": {"type": "object"}}],
                "capabilityTools": [],
            }} for name in ("ordinary", "code")
        },
    }
    changed = json.loads(json.dumps(base))
    changed["presets"]["ordinary"]["toolContracts"]["modelTools"][0]["schema"] = {
        "type": "object", "required": ["queries"],
    }
    delta = capability_delta(base, changed)
    assert list(delta["ordinary_model_tool_contract_changes"]) == ["web_search"]


def test_report_never_claims_release_ready(tmp_path: Path) -> None:
    report = EvaluationReport(
        baseline_version="old",
        candidate_version="new",
        generated_at_utc="2026-08-25T00:00:00+00:00",
        package={},
        dependency_delta={"added": [], "removed": []},
        public_api_delta={},
        capability_delta={
            "enabled_modules": {"added": [], "removed": []},
            "code_capability_tools": {"added": [], "removed": []},
        },
        checks=[],
        old_session_resume={"created": True, "resumed": True},
        decision={
            "contract_ready": True,
            "release_ready": False,
            "release_requirements": ["full regression"],
        },
    )
    json_path, markdown_path = write_report(report, tmp_path)
    assert json.loads(json_path.read_text())["decision"]["release_ready"] is False
    assert "尚未接纳" in markdown_path.read_text()


def test_failed_report_remains_renderable_without_capability_inventory(tmp_path: Path) -> None:
    report = EvaluationReport(
        baseline_version="old",
        candidate_version="broken",
        generated_at_utc="2026-08-31T00:00:00+00:00",
        package={},
        dependency_delta={"added": [], "removed": []},
        checks=[],
        decision={
            "contract_ready": False,
            "release_ready": False,
            "release_requirements": ["fix candidate"],
        },
    )
    json_path, markdown_path = write_report(report, tmp_path)
    assert json_path.exists()
    assert "未通过契约评估" in markdown_path.read_text()


def test_installed_release_train_rejects_mixed_dsh_versions(tmp_path: Path) -> None:
    packages = {
        "a/node_modules/@deepseek-ai/dsh-agent/package.json": ("@deepseek-ai/dsh-agent", "new"),
        "b/node_modules/@deepseek-ai/dsh-tools/package.json": ("@deepseek-ai/dsh-tools", "old"),
    }
    for relative, (name, version) in packages.items():
        path = tmp_path / "node_modules" / ".pnpm" / relative
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")
    check, inventory = verify_installed_release_train(tmp_path, "new")
    assert check.passed is False
    assert inventory["@deepseek-ai/dsh-tools"] == ["old"]
