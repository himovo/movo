"""Sandboxed script execution should not wait for a user approval card."""

from app.enterprise_capabilities.runtime.catalog import InternalCapabilityCatalog
from app.enterprise_capabilities.tools.service import EnterpriseToolService
from app.dsh_runtime.profile.tools import ToolProfileDefinition


def _profile(capability) -> ToolProfileDefinition:
    return ToolProfileDefinition(
        name=capability.tool_name,
        version=capability.version,
        source_type="internal",
        capability_ref=capability.capability_ref,
        external_tool_id=capability.capability_ref,
        description=capability.description,
        risk_level=capability.risk_level,
        approval_required=capability.approval_required,
    )


def test_sandboxed_run_script_skips_approval_for_new_and_existing_profiles(monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_URL", "http://sandbox-manager:8300")
    capability = next(
        item for item in InternalCapabilityCatalog().definitions()
        if item.capability_ref == "data.run_script@v1"
    )
    assert capability.approval_required is False
    profile = _profile(capability)
    assert EnterpriseToolService._approval_required(profile, {"code": "print(1)"}) is False
    legacy_profile = profile.model_copy(update={"approval_required": True})
    assert EnterpriseToolService._approval_required(legacy_profile, {"code": "print(1)"}) is False


def test_unsandboxed_script_skips_approval_but_other_gates_remain(monkeypatch) -> None:
    monkeypatch.delenv("MOVO_SANDBOX_MANAGER_URL", raising=False)
    capabilities = {item.capability_ref: item for item in InternalCapabilityCatalog().definitions()}
    script = capabilities["data.run_script@v1"]
    assert script.approval_required is False
    assert EnterpriseToolService._approval_required(_profile(script), {}) is False
    legacy_profile = _profile(script).model_copy(update={"approval_required": True})
    assert EnterpriseToolService._approval_required(legacy_profile, {}) is False

    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_URL", "http://sandbox-manager:8300")
    table_fill = capabilities["document.fill_form@v1"]
    assert EnterpriseToolService._approval_required(_profile(table_fill), {}) is False
