from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.dsh_runtime.contracts import (
    AGENT_KERNEL_CONTRACT_VERSION,
    KERNEL_EVENT_VERSION,
    ContentBlock,
    CreateRuntimeRequest,
    KernelEventEnvelope,
    KernelEventSource,
    SendRequest,
    SessionSpec,
)
from app.api.endpoints.dsh_chat import DesktopSessionCommitRequest


def test_contract_versions_are_explicit_v1() -> None:
    assert AGENT_KERNEL_CONTRACT_VERSION == "askai.agent-kernel.v1"
    assert KERNEL_EVENT_VERSION == "askai.kernel-event.v1"


def test_runtime_and_send_contracts_are_strict_and_round_trip() -> None:
    runtime = CreateRuntimeRequest(
        tenant_id="tenant-a",
        profile_version="profile-1",
        isolation_key="tenant-a:profile-1:restricted",
    )
    assert CreateRuntimeRequest.model_validate_json(runtime.model_dump_json()) == runtime

    request = SendRequest(
        session_id="kernel-session-1",
        request_id="request-1",
        content=[ContentBlock(type="text", data={"text": "hello"})],
    )
    assert SendRequest.model_validate(request.model_dump()) == request

    with pytest.raises(ValidationError):
        CreateRuntimeRequest(
            tenant_id="tenant-a",
            profile_version="profile-1",
            isolation_key="isolation",
            unexpected=True,
        )


def test_session_spec_rejects_empty_enterprise_identity() -> None:
    with pytest.raises(ValidationError):
        SessionSpec(conversation_id="", tenant_id="tenant-a", user_id="user-a", profile_version="profile-1")


def test_session_preset_is_explicit_and_backward_compatible() -> None:
    ordinary = SessionSpec(
        conversation_id="conversation-a", tenant_id="tenant-a", user_id="user-a", profile_version="profile-1"
    )
    code = SessionSpec(
        conversation_id="conversation-code", tenant_id="tenant-a", user_id="user-a",
        profile_version="profile-1", preset_id="code", execution_location="desktop",
        workspace_id="workspace-a",
    )
    assert ordinary.preset_id == "askai-enterprise"
    assert SessionSpec.model_validate_json(code.model_dump_json()).preset_id == "code"
    assert code.execution_location == "desktop"
    assert code.workspace_id == "workspace-a"


def test_desktop_binding_wire_contract_rejects_absolute_path_fields() -> None:
    payload = {
        "runtime_id": "runtime-a", "kernel_session_id": "session-a",
        "dsh_workspace_id": "workspace-a", "source_workspace_id": "workspace-a",
        "profile_version": "rp-a", "model_instance_id": "model-a", "device_id": "device-a",
        "cwd": "/private/repository",
    }
    with pytest.raises(Exception, match="Extra inputs are not permitted"):
        DesktopSessionCommitRequest.model_validate(payload)
    with pytest.raises(ValidationError):
        SessionSpec(
            conversation_id="conversation-a", tenant_id="tenant-a", user_id="user-a",
            profile_version="profile-1", preset_id="",
        )


def test_desktop_binding_wire_contract_matches_electron_commit_payload() -> None:
    payload = {
        "runtime_id": "runtime-a", "kernel_session_id": "session-a",
        "dsh_workspace_id": "workspace-a", "source_workspace_id": "source-a",
        "profile_version": "rp-a", "model_instance_id": "model-a", "device_id": "device-a",
        "git_branch": "askai/task-a", "base_commit": "a" * 40, "worktree": True,
        "title": "Fix the tests",
    }
    # Optional Git identity fields are omitted by JSON.stringify when the
    # desktop has no value; the API restores their explicit contract defaults.
    assert DesktopSessionCommitRequest.model_validate(payload).model_dump(exclude_defaults=True) == payload
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DesktopSessionCommitRequest.model_validate({**payload, "preset_id": "code"})


def test_kernel_event_is_strict_replayable_and_timezone_aware() -> None:
    event = KernelEventEnvelope(
        event_id="evt-1",
        runtime_id="runtime-1",
        session_id="session-1",
        profile_version="profile-1",
        cursor=7,
        type="agent.message.completed",
        occurred_at=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
        payload={"text": "done"},
        source=KernelEventSource(kernel_version="0.1.0-rc.6", native_event_type="message/commit"),
    )
    restored = KernelEventEnvelope.model_validate_json(event.model_dump_json())
    assert restored == event
    assert restored.cursor == 7

    invalid = event.model_dump()
    invalid["occurred_at"] = datetime(2026, 8, 15, 12, 0)
    with pytest.raises(ValidationError, match="timezone-aware"):
        KernelEventEnvelope.model_validate(invalid)

    invalid = event.model_dump()
    invalid["cursor"] = -1
    with pytest.raises(ValidationError):
        KernelEventEnvelope.model_validate(invalid)


def test_contract_package_has_no_legacy_runtime_imports() -> None:
    contract_root = Path(__file__).parents[2] / "app" / "dsh_runtime" / "contracts"
    forbidden_prefixes = (
        "app.runtime",
        "app.orchestrator",
        "app.pipeline",
        "app.skillsystem",
    )
    offenders: list[str] = []
    for path in sorted(contract_root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name.startswith(forbidden_prefixes) for name in names):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
