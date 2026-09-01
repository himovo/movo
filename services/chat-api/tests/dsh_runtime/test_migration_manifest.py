from __future__ import annotations

import json
from pathlib import Path

import yaml


CHAT_API_ROOT = Path(__file__).parents[2]
REPOSITORY_ROOT = CHAT_API_ROOT.parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "docs" / "dsh-migration-manifest.yaml"
DATA_BOUNDARIES_PATH = REPOSITORY_ROOT / "docs" / "dsh-data-boundaries.yaml"
DSH_LOCK_PATH = CHAT_API_ROOT / "dsh" / "runtime-host" / "pnpm-lock.yaml"
DSH_PACKAGE_PATH = CHAT_API_ROOT / "dsh" / "runtime-host" / "package.json"


def _expand_single_brace_pattern(pattern: str) -> list[str]:
    """Expand the one brace group used by the human-readable migration ledger."""

    if "{" not in pattern:
        return [pattern]
    prefix, remainder = pattern.split("{", 1)
    choices, suffix = remainder.split("}", 1)
    return [f"{prefix}{choice}{suffix}" for choice in choices.split(",")]


def test_migration_manifest_is_complete_and_policy_locked() -> None:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "askai.dsh-migration-manifest.v1"
    assert manifest["policy"] == {
        "no_legacy_fallback": True,
        "no_in_place_dsh_adapters": True,
        "unverified_capability_behavior": "explicit_unsupported",
        "statuses": ["frozen", "extracting", "verified", "retired"],
    }

    capabilities = manifest["capabilities"]
    ids = [capability["id"] for capability in capabilities]
    assert len(ids) == len(set(ids))

    required_fields = {
        "id",
        "source",
        "owner",
        "disposition",
        "target",
        "old_runtime_dependencies",
        "golden_tests",
        "status",
        "verified_at",
    }
    allowed_owners = {"dsh", "askai-control-plane", "enterprise-capability", "enterprise-workflow"}
    allowed_dispositions = {"replace", "extract", "retain", "retire"}
    allowed_statuses = set(manifest["policy"]["statuses"])
    for capability in capabilities:
        assert required_fields <= capability.keys(), capability["id"]
        assert capability["owner"] in allowed_owners, capability["id"]
        assert capability["disposition"] in allowed_dispositions, capability["id"]
        assert capability["status"] in allowed_statuses, capability["id"]
        if capability["status"] == "frozen":
            assert capability["verified_at"] is None, capability["id"]
        else:
            assert capability["verified_at"], capability["id"]

    by_id = {capability["id"]: capability for capability in capabilities}
    assert by_id["model_management_and_gateway"]["status"] == "verified"


def test_retired_legacy_runtime_roots_are_absent_and_recorded_in_the_ledger() -> None:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    source_patterns = [
        expanded
        for capability in manifest["capabilities"]
        for expanded in _expand_single_brace_pattern(capability["source"])
    ]

    for root in ("runtime", "orchestrator", "pipeline", "skillsystem", "capabilities"):
        assert not (CHAT_API_ROOT / "app" / root).exists(), root
    assert any(pattern.startswith("services/chat-api/app/runtime/") for pattern in source_patterns)


def test_dsh_data_stores_are_versioned_and_do_not_replace_conversation_authority() -> None:
    boundaries = yaml.safe_load(DATA_BOUNDARIES_PATH.read_text(encoding="utf-8"))
    assert boundaries["schema_version"] == "askai.dsh-data-boundaries.v1"
    assert boundaries["policy"]["existing_collections_are_not_repurposed"] is True

    stores = boundaries["stores"]
    by_name = {store["name"]: store for store in stores}
    assert len(by_name) == len(stores)
    assert by_name["chat_sessions"]["authority"] == "askai"
    assert by_name["chat_messages"]["authority"] == "askai-projection"
    assert by_name["dsh_session_persistence"]["authority"] == "dsh"

    for store in stores:
        if store["lifecycle"].startswith("new-"):
            assert store["schema_version"], store["name"]


def test_runtime_host_lock_keeps_every_dsh_package_on_one_release_train() -> None:
    lock = yaml.safe_load(DSH_LOCK_PATH.read_text(encoding="utf-8"))
    package = json.loads(DSH_PACKAGE_PATH.read_text(encoding="utf-8"))
    release_train = package["dependencies"]["@deepseek-ai/dsh"]
    dsh_packages = [
        package
        for package in lock["packages"]
        if package.startswith("@deepseek-ai/dsh@") or package.startswith("@deepseek-ai/dsh-")
    ]
    assert dsh_packages
    unexpected = [package for package in dsh_packages if f"@{release_train}" not in package]
    assert unexpected == []


def test_new_dsh_boundary_does_not_import_or_modify_legacy_agent_kernel() -> None:
    forbidden_imports = ("app.runtime", "app.orchestrator", "app.pipeline", "app.skillsystem")
    boundary = CHAT_API_ROOT / "app" / "dsh_runtime"
    offenders: list[str] = []
    for path in boundary.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(name in text for name in forbidden_imports):
            offenders.append(str(path.relative_to(CHAT_API_ROOT)))
    assert offenders == []

    assert all(
        not (CHAT_API_ROOT / "app" / root).exists()
        for root in ("runtime", "orchestrator", "pipeline", "skillsystem")
    )
