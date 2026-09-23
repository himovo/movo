"""Approval initiator scoping (plan todo 16 / Q10) — real-mongod pinned matrix.

An approval raised during a turn is stamped with that turn's initiator; only
that initiator may list or decide it; other participants' pending lists exclude
it and a decide attempt returns 403. Today the stamp is the tool-token subject
(``claims.user_id``), which IS the turn's speaker under R1=A (the profile sync
at ``chat_service.py:187-192`` runs before ``claim_turn`` at ``:229``, and
``profile/resolver.py:40-46`` issues the token with
``user_id=subject_user_id``). Todo 14 records ``initiator_user_id`` in the
claimed turn's metadata; the stamp prefers that metadata when present and falls
back to the token subject. The matrix also pins the anti-widening invariants:
the profile-subject check and the kernel-session binding check still deny.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
import pytest
from pydantic import ValidationError

import app.enterprise_capabilities.tools.repository as tools_repository_module
from app.api.endpoints import dsh_tool_gateway
from app.dsh_runtime.application import dsh_runtime_application
from app.dsh_runtime.profile.models import RuntimeProfileSnapshot
from app.dsh_runtime.profile.tools import ToolProfileDefinition
from app.dsh_runtime.tool_gateway import ToolGatewayTokenService
from app.enterprise_capabilities.tools.contracts import (
    ApprovalAskRequest,
    ApprovalDecisionRequest,
    EnterpriseApproval,
    ToolExecuteRequest,
)
from app.enterprise_capabilities.tools.repository import EnterpriseToolRepository
from app.enterprise_capabilities.tools.service import EnterpriseToolService, ToolPolicyDenied

# allow: SIZE_OK — cohesive pinned matrix over the plan's todo-16 QA rows
# (baseline characterization + initiator scoping + anti-widening), T04/T07-T12
# precedent; the frozen plan pins this single seam for todo 16.

TENANT = "tenant-a"
CONVERSATION = "conversation-a"
KERNEL_SESSION = "session-a"
PROFILE_VERSION = "profile-a"
OWNER = "user-owner"
INITIATOR = "user-participant-a"
OTHER_PARTICIPANT = "user-participant-b"
TURN_METADATA_INITIATOR = "user-turn-initiator"


class FakeProfileStore:
    def __init__(self, profile: RuntimeProfileSnapshot) -> None:
        self.profile = profile

    async def get(self, version: str):
        assert version == self.profile.profile_version
        return self.profile


def _write_tool() -> ToolProfileDefinition:
    return ToolProfileDefinition(
        name="askai_mcp_write", version="v-write", source_type="mcp",
        external_tool_id="id-write", mcp_tool_name="native", description="write",
        input_schema={"type": "object"}, output_schema={}, risk_level="write",
        approval_required=True, required_scopes=("tools:write",),
        timeout_ms=1000,
    )


def _profile(subject: str = INITIATOR) -> RuntimeProfileSnapshot:
    # The profile's subject is the turn's speaker under R1=A: the profile sync
    # (chat_service.py:187-192) runs before claim_turn (:229), so the tool
    # token issued for this profile (resolver.py:40-46) carries the speaker.
    write = _write_tool()
    return RuntimeProfileSnapshot(
        profile_version=PROFILE_VERSION, content_hash="a" * 64,
        tenant_id=TENANT, subject_user_id=subject,
        model_source_tenant_id=TENANT, model_instance_id="model-a",
        provider_id="provider-a", provider_type="openai_compatible",
        provider_name="provider", model_name="model", display_name="model",
        capabilities=("chat", "tools"), tool_versions=(write.version,), tools=(write,),
    )


def _claims(*, user_id: str = INITIATOR):
    tokens = ToolGatewayTokenService("t16-tool-signing-secret")
    write = _write_tool()
    token = tokens.issue(
        tenant_id=TENANT, user_id=user_id, profile_version=PROFILE_VERSION,
        tool_names=[write.name], scopes=list(write.required_scopes),
    )
    return tokens.verify(token)


async def _seed_binding(
    harness, *, user_id: str = INITIATOR, turn_metadata: dict[str, Any] | None = None
) -> None:
    # Hand-seeded binding doc (the exact shape EnterpriseToolRepository
    # .session_binding reads) — the sibling worker is concurrently editing
    # bindings/repository.py, so tests never execute that file's code.
    await harness.db.agent_kernel_bindings.insert_one({
        "binding_id": "binding-a",
        "kernel_session_id": KERNEL_SESSION,
        "tenant_id": TENANT,
        "user_id": user_id,
        "conversation_id": CONVERSATION,
        "profile_version": PROFILE_VERSION,
        "execution_location": "server",
        "current": True,
        "active_turn": {
            "message_id": "message-a",
            "status": "running",
            "turn_context": {},
            "turn_metadata": dict(turn_metadata or {}),
        },
        "created_at": datetime.now(timezone.utc),
    })


def _approval_row(harness, action_id: str):
    return harness.db.enterprise_tool_approvals.find_one({"action_id": action_id})


def _ask(action_id: str) -> ApprovalAskRequest:
    return ApprovalAskRequest(
        profileVersion=PROFILE_VERSION, sessionId=KERNEL_SESSION,
        toolName="askai_mcp_write", actionId=action_id, reason="write",
        timeoutSeconds=2,
    )


def _execute_request() -> ToolExecuteRequest:
    return ToolExecuteRequest(
        profileVersion=PROFILE_VERSION, sessionId=KERNEL_SESSION,
        toolName="askai_mcp_write", actionId="action-exec",
        idempotencyKey="idem-exec", arguments={"id": 1},
    )


def _identity_seam(mapping: dict[str, tuple[str, str]]):
    async def _identity(authorization: str | None) -> tuple[str, str]:
        token = (authorization or "").removeprefix("Bearer ").strip()
        return mapping[token]

    return _identity


def _install_service(monkeypatch: pytest.MonkeyPatch, harness, profile: RuntimeProfileSnapshot) -> EnterpriseToolService:
    repo = EnterpriseToolRepository()
    service = EnterpriseToolService(repo, FakeProfileStore(profile))
    monkeypatch.setattr(tools_repository_module, "get_db", lambda: harness.db)
    monkeypatch.setattr(dsh_runtime_application, "tools", service)
    return service


def _wire_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dsh_tool_gateway, "_identity", _identity_seam({
        OWNER: (TENANT, OWNER),
        INITIATOR: (TENANT, INITIATOR),
        OTHER_PARTICIPANT: (TENANT, OTHER_PARTICIPANT),
    }))


def _raise_status(exc: BaseException) -> int:
    return getattr(exc, "status_code", 0)


def test_approval_is_stamped_with_the_tool_token_subject(
    monkeypatch: pytest.MonkeyPatch, real_mongo_db
) -> None:
    """Baseline characterization: with no turn-metadata initiator recorded, the
    approval is stamped with claims.user_id — the tool-token subject, which is
    the turn's speaker (the initiator) under R1=A."""
    harness = real_mongo_db
    service = _install_service(monkeypatch, harness, _profile())
    harness.run(service._repository.ensure_indexes())

    async def scenario():
        await _seed_binding(harness)
        pending = asyncio.create_task(service.request_approval(_ask("action-1"), _claims()))
        while await _approval_row(harness, "action-1") is None:
            await asyncio.sleep(0)
        await service.decide(
            "action-1", decision="approved", actor_id=INITIATOR,
            tenant_id=TENANT, subject_user_id=INITIATOR,
        )
        outcome = await pending
        row = await _approval_row(harness, "action-1")
        return outcome, row

    outcome, row = harness.run(scenario())
    assert outcome == "allowed-once"
    assert row["user_id"] == INITIATOR
    assert row["tenant_id"] == TENANT
    assert row["conversation_id"] == CONVERSATION
    assert row["message_id"] == "message-a"
    assert row["status"] == "approved"


def test_approval_stamp_prefers_the_claimed_turn_initiator_metadata(
    monkeypatch: pytest.MonkeyPatch, real_mongo_db
) -> None:
    """Failing-first proof for the slot-in: once todo 14 records the turn's
    initiator in the claimed turn's metadata (server-built — chat_service.py
    :136-139 never copies client fields), the stamp follows the metadata."""
    harness = real_mongo_db
    service = _install_service(monkeypatch, harness, _profile())
    harness.run(service._repository.ensure_indexes())

    async def scenario():
        await _seed_binding(harness, turn_metadata={"initiator_user_id": TURN_METADATA_INITIATOR})
        pending = asyncio.create_task(service.request_approval(_ask("action-1"), _claims()))
        while await _approval_row(harness, "action-1") is None:
            await asyncio.sleep(0)
        await service.decide(
            "action-1", decision="approved", actor_id=TURN_METADATA_INITIATOR,
            tenant_id=TENANT, subject_user_id=TURN_METADATA_INITIATOR,
        )
        assert await pending == "allowed-once"
        return await _approval_row(harness, "action-1")

    row = harness.run(scenario())
    assert row["user_id"] == TURN_METADATA_INITIATOR


def test_initiator_sees_and_decides_their_own_pending_approval(
    monkeypatch: pytest.MonkeyPatch, real_mongo_db
) -> None:
    harness = real_mongo_db
    service = _install_service(monkeypatch, harness, _profile())
    _wire_identity(monkeypatch)
    harness.run(service._repository.ensure_indexes())

    async def scenario():
        await _seed_binding(harness)
        pending = asyncio.create_task(service.request_approval(_ask("action-1"), _claims()))
        while await _approval_row(harness, "action-1") is None:
            await asyncio.sleep(0)
        listed = await dsh_tool_gateway.pending_approvals(
            conversation_id=CONVERSATION, authorization=f"Bearer {INITIATOR}"
        )
        decided = await dsh_tool_gateway.decide_approval(
            "action-1",
            payload=ApprovalDecisionRequest(decision="approved"),
            authorization=f"Bearer {INITIATOR}",
        )
        outcome = await pending
        return listed, decided, outcome

    listed, decided, outcome = harness.run(scenario())
    assert [row["action_id"] for row in listed["data"]] == ["action-1"]
    assert decided["data"]["status"] == "approved"
    assert decided["data"]["decided_by"] == INITIATOR
    assert outcome == "allowed-once"


def test_other_participants_pending_lists_exclude_the_initiators_approval(
    monkeypatch: pytest.MonkeyPatch, real_mongo_db
) -> None:
    harness = real_mongo_db
    service = _install_service(monkeypatch, harness, _profile())
    _wire_identity(monkeypatch)
    harness.run(service._repository.ensure_indexes())

    async def scenario():
        await _seed_binding(harness)
        pending = asyncio.create_task(service.request_approval(_ask("action-1"), _claims()))
        while await _approval_row(harness, "action-1") is None:
            await asyncio.sleep(0)
        participant_view = await dsh_tool_gateway.pending_approvals(
            conversation_id=CONVERSATION, authorization=f"Bearer {OTHER_PARTICIPANT}"
        )
        owner_view = await dsh_tool_gateway.pending_approvals(
            conversation_id=CONVERSATION, authorization=f"Bearer {OWNER}"
        )
        return participant_view, owner_view, pending

    participant_view, owner_view, pending = harness.run(scenario())
    assert participant_view == {"code": 0, "data": []}
    assert owner_view == {"code": 0, "data": []}
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        harness.run(pending)


def test_second_participants_decide_attempt_returns_403(
    monkeypatch: pytest.MonkeyPatch, real_mongo_db
) -> None:
    harness = real_mongo_db
    service = _install_service(monkeypatch, harness, _profile())
    _wire_identity(monkeypatch)
    harness.run(service._repository.ensure_indexes())

    async def scenario():
        await _seed_binding(harness)
        pending = asyncio.create_task(service.request_approval(_ask("action-1"), _claims()))
        while await _approval_row(harness, "action-1") is None:
            await asyncio.sleep(0)
        try:
            await dsh_tool_gateway.decide_approval(
                "action-1",
                payload=ApprovalDecisionRequest(decision="approved"),
                authorization=f"Bearer {OTHER_PARTICIPANT}",
            )
        except HTTPException as exc:
            row = await _approval_row(harness, "action-1")
            return exc, row, pending
        raise AssertionError("participant decide attempt was not denied")

    exc, row, pending = harness.run(scenario())
    assert exc.status_code == 403
    assert "approval_subject_mismatch" in str(exc.detail)
    # A denied decide mutates nothing: the approval stays pending for its initiator.
    assert row["status"] == "pending"
    assert row["user_id"] == INITIATOR
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        harness.run(pending)


def test_owner_cannot_decide_a_participants_approval(
    monkeypatch: pytest.MonkeyPatch, real_mongo_db
) -> None:
    harness = real_mongo_db
    service = _install_service(monkeypatch, harness, _profile())
    _wire_identity(monkeypatch)
    harness.run(service._repository.ensure_indexes())

    async def scenario():
        await _seed_binding(harness)
        pending = asyncio.create_task(service.request_approval(_ask("action-1"), _claims()))
        while await _approval_row(harness, "action-1") is None:
            await asyncio.sleep(0)
        try:
            await dsh_tool_gateway.decide_approval(
                "action-1",
                payload=ApprovalDecisionRequest(decision="approved"),
                authorization=f"Bearer {OWNER}",
            )
        except HTTPException as exc:
            row = await _approval_row(harness, "action-1")
            return exc, row, pending
        raise AssertionError("owner decide attempt was not denied")

    exc, row, pending = harness.run(scenario())
    # Q10: the approval is the participant-initiator's, not the owner's.
    assert exc.status_code == 403
    assert "approval_subject_mismatch" in str(exc.detail)
    assert row["status"] == "pending"
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        harness.run(pending)


def test_second_participant_cannot_see_or_decide_the_owners_approval(
    monkeypatch: pytest.MonkeyPatch, real_mongo_db
) -> None:
    """QA failure row ('...nor the owner's'): an OWNER-initiated approval is
    excluded from the second participant's pending list and their decide
    attempt returns 403 — the owner gets no super-user decide right (Q10).
    The stamp also follows an owner-initiated run: user_id == OWNER."""
    harness = real_mongo_db
    service = _install_service(monkeypatch, harness, _profile(subject=OWNER))
    _wire_identity(monkeypatch)
    harness.run(service._repository.ensure_indexes())

    async def scenario():
        await _seed_binding(harness, user_id=OWNER)
        pending = asyncio.create_task(
            service.request_approval(_ask("action-1"), _claims(user_id=OWNER))
        )
        while await _approval_row(harness, "action-1") is None:
            await asyncio.sleep(0)
        participant_view = await dsh_tool_gateway.pending_approvals(
            conversation_id=CONVERSATION, authorization=f"Bearer {OTHER_PARTICIPANT}"
        )
        try:
            await dsh_tool_gateway.decide_approval(
                "action-1",
                payload=ApprovalDecisionRequest(decision="approved"),
                authorization=f"Bearer {OTHER_PARTICIPANT}",
            )
        except HTTPException as exc:
            row = await _approval_row(harness, "action-1")
            return participant_view, exc, row, pending
        raise AssertionError("participant decide attempt on the owner's approval was not denied")

    participant_view, exc, row, pending = harness.run(scenario())
    assert participant_view == {"code": 0, "data": []}
    assert exc.status_code == 403
    assert "approval_subject_mismatch" in str(exc.detail)
    # A denied decide mutates nothing: the approval stays pending for its initiator.
    assert row["status"] == "pending"
    assert row["user_id"] == OWNER
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        harness.run(pending)


def test_profile_subject_check_still_denies_a_mismatched_subject(
    monkeypatch: pytest.MonkeyPatch, real_mongo_db
) -> None:
    """Anti-widening: the profile-subject check (service.py:475) still denies a
    token whose subject is not the profile's subject — for approval requests
    AND execution."""
    harness = real_mongo_db
    service = _install_service(monkeypatch, harness, _profile())
    harness.run(service._repository.ensure_indexes())

    async def scenario():
        await _seed_binding(harness)
        forged = _claims(user_id=OTHER_PARTICIPANT)
        with pytest.raises(ToolPolicyDenied, match="Runtime Profile subject mismatch"):
            await service.request_approval(_ask("action-1"), forged)
        with pytest.raises(ToolPolicyDenied, match="Runtime Profile subject mismatch"):
            await service.execute(_execute_request(), forged)
        row = await _approval_row(harness, "action-1")
        return row

    row = harness.run(scenario())
    assert row is None


def test_kernel_session_binding_check_still_holds(
    monkeypatch: pytest.MonkeyPatch, real_mongo_db
) -> None:
    """Anti-widening: the kernel-session binding check (service.py:496-502)
    still denies when the binding's user is not the token subject — the R1=A
    speaker-binding invariant."""
    harness = real_mongo_db
    service = _install_service(monkeypatch, harness, _profile())
    harness.run(service._repository.ensure_indexes())

    async def scenario():
        await _seed_binding(harness)
        await harness.db.agent_kernel_bindings.update_one(
            {"kernel_session_id": KERNEL_SESSION, "current": True},
            {"$set": {"user_id": OTHER_PARTICIPANT}},
        )
        with pytest.raises(ToolPolicyDenied, match="Kernel Session scope mismatch"):
            await service.request_approval(_ask("action-1"), _claims())
        row = await _approval_row(harness, "action-1")
        return row

    row = harness.run(scenario())
    assert row is None


def test_an_expired_approval_is_not_listable_or_decidable(
    monkeypatch: pytest.MonkeyPatch, real_mongo_db
) -> None:
    """Deterministic expiry (adversarial class: no real-time waits) — the
    300s/900s deadline is simulated through durable state: an expired approval
    is excluded from every pending list and a decide attempt fails closed."""
    harness = real_mongo_db
    service = _install_service(monkeypatch, harness, _profile())
    harness.run(service._repository.ensure_indexes())

    async def scenario():
        seeded = EnterpriseApproval(
            action_id="action-exp", tenant_id=TENANT, user_id=INITIATOR,
            conversation_id=CONVERSATION, kernel_session_id=KERNEL_SESSION,
            profile_version=PROFILE_VERSION, tool_name="askai_mcp_write",
            message_id="message-a",
        )
        await service._repository.ensure_approval(seeded)
        expired = await service._repository.expire("action-exp")
        return expired

    expired = harness.run(scenario())
    assert expired is not None and expired.status == "expired"
    assert harness.run(service.list_pending(tenant_id=TENANT, user_id=INITIATOR)) == []
    with pytest.raises(ValueError, match="already expired"):
        harness.run(service.decide(
            "action-exp", decision="approved", actor_id=INITIATOR,
            tenant_id=TENANT, subject_user_id=INITIATOR,
        ))


def test_malformed_approval_payloads_are_rejected_at_the_boundary() -> None:
    """Adversarial class: new input parsing — malformed payloads raise a
    ValidationError at the boundary (FastAPI maps it to a clean 422), never a
    500 path."""
    with pytest.raises(ValidationError):
        ApprovalAskRequest(
            profileVersion=PROFILE_VERSION, sessionId=KERNEL_SESSION,
            toolName="askai_mcp_write", actionId="action-x",
            timeoutSeconds=901,  # max is 900
        )
    with pytest.raises(ValidationError):
        ApprovalAskRequest(
            profileVersion=PROFILE_VERSION, sessionId=KERNEL_SESSION,
            toolName="askai_mcp_write", actionId="action-x",
            unknownField="x",  # extra="forbid"
        )
    with pytest.raises(ValidationError):
        ApprovalDecisionRequest(decision="maybe")  # not an approved/rejected literal
