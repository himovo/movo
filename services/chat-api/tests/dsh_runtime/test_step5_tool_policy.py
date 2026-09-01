from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

import pytest

import app.enterprise_capabilities.tools.service as service_module
from app.dsh_runtime.profile.models import RuntimeProfileSnapshot
from app.dsh_runtime.profile.tools import ToolProfileCompiler, ToolProfileDefinition
from app.dsh_runtime.tool_gateway import ToolGatewayTokenService
from app.dsh_runtime.contracts import KernelEventEnvelope, KernelEventSource
from app.dsh_runtime.events import KernelEventProjector
from app.dsh_runtime.model_gateway.service import ModelGatewayRequest, ModelGatewayService
from app.dsh_runtime.model_gateway.token import ModelGatewayTokenService
from app.llm.base import BaseLLMClient
from app.llm.types import LLMResponse, Message, Role
from datetime import datetime, timezone
from app.enterprise_capabilities.tools.contracts import (
    ApprovalAskRequest,
    EnterpriseActionReceipt,
    EnterpriseApproval,
    EnterpriseSessionApprovalGrant,
    ToolExecuteRequest,
)
from app.enterprise_capabilities.tools.service import EnterpriseToolService, ToolPolicyDenied
from app.enterprise_capabilities.tools.result_projection import canonical_tool_result
from app.enterprise_capabilities.content.invocation_contract import ResolvedContentInvocation


class FakeToolCatalog:
    async def list_enabled(self, tenant_id: str, user_id: str):
        assert (tenant_id, user_id) == ("tenant-a", "user-a")
        return deepcopy([
            {
                "id": "http-read", "name": "Lookup customer", "type": "http", "description": "Lookup",
                "config": {"method": "GET", "timeoutSeconds": 2, "authToken": "MUST_NOT_LEAK"},
                "inputSchema": [{"name": "id", "type": "String", "required": True}],
                "outputSchema": [
                    {"name": "message", "type": "String", "required": False},
                    {
                        "name": "data", "type": "Object", "required": False,
                        "children": [{
                            "name": "stores", "type": "Array", "required": False,
                            "children": [
                                {"name": "store_id", "type": "String", "required": False},
                                {"name": "sales", "type": "Object", "required": False, "children": [
                                    {"name": "actual_amount", "type": "Integer", "required": False},
                                ]},
                            ],
                        }],
                    },
                ],
            },
            {
                "id": "http-write", "name": "Publish record", "type": "http", "description": "Publish",
                "config": {"method": "POST"}, "inputSchema": [],
            },
            {
                "id": "mcp-a", "name": "CRM", "type": "mcp", "description": "CRM MCP", "config": {},
                "discoveredTools": [
                    {
                        "name": "search",
                        "description": "Search",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "stage": {
                                    "type": "string",
                                    "enum": ["lead", "needs_confirmed", "proposal"],
                                },
                                "facts": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {"field": {"type": "string"}, "value": {}},
                                        "required": ["field", "value"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                        },
                        "annotations": {"readOnlyHint": True},
                    },
                    {"name": "delete", "description": "Delete", "inputSchema": {"type": "object"}, "annotations": {"destructiveHint": True}},
                ],
            },
        ])


def test_tool_profile_compiler_is_stable_secret_free_and_risk_aware() -> None:
    async def run():
        compiler = ToolProfileCompiler(FakeToolCatalog())
        first = await compiler.compile(tenant_id="tenant-a", user_id="user-a")
        assert first == await compiler.compile(tenant_id="tenant-a", user_id="user-a")
        assert len(first) == 4
        assert len({item.name for item in first}) == 4
        assert {item.risk_level for item in first} == {"read", "write", "dangerous"}
        assert sum(item.approval_required for item in first) == 2
        assert "MUST_NOT_LEAK" not in str(first)
        http_read = next(item for item in first if item.external_tool_id == "http-read")
        assert http_read.input_schema["required"] == ["id"]
        assert http_read.output_validation == "none"
        message_schema = http_read.output_schema["properties"]["message"]
        assert message_schema["anyOf"][-1] == {"type": "null"}
        data_schema = http_read.output_schema["properties"]["data"]["anyOf"][0]
        stores_schema = data_schema["properties"]["stores"]["anyOf"][0]
        assert stores_schema["type"] == "array"
        assert stores_schema["items"]["type"] == "object"
        assert set(stores_schema["items"]["properties"]) == {"store_id", "sales"}
        sales_schema = stores_schema["items"]["properties"]["sales"]["anyOf"][0]
        assert sales_schema["properties"]["actual_amount"]["anyOf"][0]["type"] == "integer"
        assert next(item for item in first if item.mcp_tool_name == "search").display_name == "CRM"
        assert next(item for item in first if item.mcp_tool_name == "search").output_validation == "strict"
        nested = next(item for item in first if item.mcp_tool_name == "search").input_schema
        assert nested["properties"]["facts"]["items"]["required"] == ["field", "value"]
        assert nested["properties"]["facts"]["items"]["additionalProperties"] is False
        assert nested["properties"]["stage"]["enum"] == ["lead", "needs_confirmed", "proposal"]

    asyncio.run(run())


def test_http_output_validation_requires_explicit_admin_opt_in() -> None:
    class StrictCatalog:
        async def list_enabled(self, _tenant_id: str, _user_id: str):
            return [{
                "id": "http-strict", "name": "Strict", "type": "http", "description": "Strict",
                "config": {"method": "GET", "strictOutputValidation": True},
                "inputSchema": [], "outputSchema": [{"name": "code", "type": "Integer", "required": True}],
            }]

    async def run():
        tool = (await ToolProfileCompiler(StrictCatalog()).compile(tenant_id="tenant-a", user_id="user-a"))[0]
        assert tool.output_validation == "strict"
        assert tool.output_schema["required"] == ["code"]

    asyncio.run(run())


def test_disabled_tool_disappears_from_new_compiled_profile() -> None:
    class MutableCatalog:
        rows = [{
            "id": "tool-a", "name": "A", "type": "http", "description": "A",
            "config": {"method": "GET"}, "inputSchema": [],
        }]

        async def list_enabled(self, _tenant_id: str, _user_id: str):
            return deepcopy(self.rows)

    async def run():
        catalog = MutableCatalog()
        compiler = ToolProfileCompiler(catalog)
        assert len(await compiler.compile(tenant_id="tenant-a", user_id="user-a")) == 1
        catalog.rows = []
        assert await compiler.compile(tenant_id="tenant-a", user_id="user-a") == ()

    asyncio.run(run())


class FakeProfileStore:
    def __init__(self, profile: RuntimeProfileSnapshot) -> None:
        self.profile = profile

    async def get(self, version: str):
        assert version == self.profile.profile_version
        return self.profile


class FakeRepository:
    def __init__(self) -> None:
        self.receipts: dict[str, EnterpriseActionReceipt] = {}
        self.approvals: dict[str, EnterpriseApproval] = {}
        self.grants: dict[tuple[str, str, str, str, str], EnterpriseSessionApprovalGrant] = {}
        self.audit_rows: list[str] = []
        self.binding = {
            "tenant_id": "tenant-a", "user_id": "user-a", "conversation_id": "conversation-a",
            "kernel_session_id": "session-a", "profile_version": "profile-a", "current": True,
            "active_turn": {"turn_context": {"knowledge_qa_enabled": True, "knowledge_base_ids": ["kb-a"]}},
        }

    async def session_binding(self, session_id: str):
        return deepcopy(self.binding) if session_id == "session-a" else None

    async def receipt_by_idempotency(self, key: str):
        return next((deepcopy(row) for row in self.receipts.values() if row.idempotency_key == key), None)

    async def start_receipt(self, receipt):
        existing = await self.receipt_by_idempotency(receipt.idempotency_key)
        if existing:
            return existing
        self.receipts[receipt.action_id] = deepcopy(receipt)
        return receipt

    async def finish_receipt(self, action_id: str, *, status: str, result=None, error=""):
        row = self.receipts[action_id].model_copy(update={"status": status, "result": result or {}, "error": error})
        self.receipts[action_id] = row
        return deepcopy(row)

    async def ensure_approval(self, approval):
        self.approvals.setdefault(approval.action_id, deepcopy(approval))
        return deepcopy(self.approvals[approval.action_id])

    async def approval(self, action_id: str):
        row = self.approvals.get(action_id)
        return deepcopy(row) if row else None

    async def decide(self, action_id: str, *, decision: str, actor_id: str, tenant_id: str):
        row = self.approvals.get(action_id)
        if not row or row.tenant_id != tenant_id or row.status != "pending":
            return None
        row = row.model_copy(update={"status": decision, "decided_by": actor_id})
        self.approvals[action_id] = row
        return deepcopy(row)

    async def expire(self, action_id: str):
        if action_id in self.approvals:
            self.approvals[action_id] = self.approvals[action_id].model_copy(update={"status": "expired"})
            return deepcopy(self.approvals[action_id])
        return None

    async def list_pending(self, *, tenant_id: str, user_id: str, conversation_id=None):
        return [
            deepcopy(row) for row in self.approvals.values()
            if row.status == "pending"
            and row.tenant_id == tenant_id
            and row.user_id == user_id
            and (not conversation_id or row.conversation_id == conversation_id)
        ]

    async def active_session_grant(
        self, *, tenant_id, user_id, conversation_id, profile_version, scope_key
    ):
        return deepcopy(self.grants.get((tenant_id, user_id, conversation_id, profile_version, scope_key)))

    async def grant_for_session(self, approval, *, actor_id):
        grant = EnterpriseSessionApprovalGrant(
            grant_id=f"grant-{approval.action_id}",
            tenant_id=approval.tenant_id,
            user_id=approval.user_id,
            conversation_id=approval.conversation_id,
            profile_version=approval.profile_version,
            tool_name=approval.tool_name,
            scope_key=approval.scope_key,
            scope_label=approval.scope_label,
            granted_by=actor_id,
            source_action_id=approval.action_id,
        )
        self.grants[(
            grant.tenant_id, grant.user_id, grant.conversation_id,
            grant.profile_version, grant.scope_key,
        )] = grant
        return deepcopy(grant)

    async def set_approval_grant_scope(self, action_id: str, grant_scope: str):
        self.approvals[action_id] = self.approvals[action_id].model_copy(update={"grant_scope": grant_scope})

    async def audit(self, **kwargs):
        self.audit_rows.append(kwargs["event"])


class FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.delay = 0.0

    async def execute_runtime(self, **kwargs):
        self.calls.append(kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        return {"success": True, "raw": {"source": kwargs["provider_type"]}}


def _tool(name: str, *, source: str, approval: bool, timeout_ms: int = 1000) -> ToolProfileDefinition:
    return ToolProfileDefinition(
        name=name, version=f"v-{name}", source_type=source, external_tool_id=f"id-{name}",
        mcp_tool_name="native" if source == "mcp" else "", description=name,
        input_schema={"type": "object"}, output_schema={}, risk_level="write" if approval else "read",
        approval_required=approval, required_scopes=(("tools:write" if approval else "tools:read"),),
        timeout_ms=timeout_ms,
    )


def _profile(*tools: ToolProfileDefinition) -> RuntimeProfileSnapshot:
    return RuntimeProfileSnapshot(
        profile_version="profile-a", content_hash="a" * 64, tenant_id="tenant-a", subject_user_id="user-a",
        model_source_tenant_id="tenant-a", model_instance_id="model-a", provider_id="provider-a",
        provider_type="openai_compatible", provider_name="provider", model_name="model", display_name="model",
        capabilities=("chat", "tools"), tool_versions=tuple(item.version for item in tools), tools=tools,
    )


def _claims(tools: list[ToolProfileDefinition]):
    tokens = ToolGatewayTokenService("step-5-tool-signing-secret")
    token = tokens.issue(
        tenant_id="tenant-a", user_id="user-a", profile_version="profile-a",
        tool_names=[item.name for item in tools], scopes=[scope for item in tools for scope in item.required_scopes],
    )
    return tokens.verify(token)


def test_policy_approval_idempotency_mcp_scope_timeout_and_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run():
        read = _tool("askai_http_read", source="http", approval=False)
        mcp = _tool("askai_mcp_write", source="mcp", approval=True)
        slow = _tool("askai_http_slow", source="http", approval=False, timeout_ms=100)
        tools = [read, mcp, slow]
        repo = FakeRepository()
        executor = FakeExecutor()
        monkeypatch.setattr(service_module, "external_tool_service", executor)
        service = EnterpriseToolService(repo, FakeProfileStore(_profile(*tools)))
        claims = _claims(tools)

        read_request = ToolExecuteRequest(
            profileVersion="profile-a", sessionId="session-a", toolName=read.name,
            actionId="read-1", idempotencyKey="idem-read", arguments={"q": "x"},
        )
        assert (await service.execute(read_request, claims)).status == "succeeded"
        assert (await service.execute(read_request, claims)).status == "succeeded"
        assert len(executor.calls) == 1

        ask = ApprovalAskRequest(
            profileVersion="profile-a", sessionId="session-a", toolName=mcp.name,
            actionId="write-1", reason="write", timeoutSeconds=2,
        )
        pending = asyncio.create_task(service.request_approval(ask, claims))
        while "write-1" not in repo.approvals:
            await asyncio.sleep(0)
        await service.decide(
            "write-1", decision="approved", actor_id="user-a", tenant_id="tenant-a", subject_user_id="user-a"
        )
        assert await pending == "allowed-once"
        write_request = ToolExecuteRequest(
            profileVersion="profile-a", sessionId="session-a", toolName=mcp.name,
            actionId="write-1", idempotencyKey="idem-write", arguments={"id": 1},
        )
        assert (await service.execute(write_request, claims)).status == "succeeded"
        assert executor.calls[-1]["provider_type"] == "mcp"
        assert executor.calls[-1]["mcp_tool_name"] == "native"

        with pytest.raises(ToolPolicyDenied, match="outside"):
            await service.execute(read_request.model_copy(update={"toolName": "alias_bypass"}), claims)
        foreign = deepcopy(repo.binding)
        repo.binding = {**foreign, "tenant_id": "tenant-b"}
        with pytest.raises(ToolPolicyDenied, match="Session scope"):
            await service.execute(read_request.model_copy(update={"actionId": "read-2", "idempotencyKey": "idem-2"}), claims)
        repo.binding = foreign

        executor.delay = 0.2
        timed = await service.execute(ToolExecuteRequest(
            profileVersion="profile-a", sessionId="session-a", toolName=slow.name,
            actionId="slow-1", idempotencyKey="idem-slow", arguments={},
        ), claims)
        assert timed.status == "timed_out"

        executor.delay = 5
        cancel_task = asyncio.create_task(service.execute(ToolExecuteRequest(
            profileVersion="profile-a", sessionId="session-a", toolName=read.name,
            actionId="cancel-1", idempotencyKey="idem-cancel", arguments={},
        ), claims))
        while "cancel-1" not in repo.receipts:
            await asyncio.sleep(0)
        cancel_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancel_task
        assert repo.receipts["cancel-1"].status == "cancelled"
        assert {"approval.requested", "approval.approved", "tool.succeeded", "tool.timed_out"}.issubset(repo.audit_rows)

    asyncio.run(run())


def test_internal_capability_uses_trusted_turn_scope_and_argument_aware_approval() -> None:
    class Internal:
        def __init__(self):
            self.calls = []

        async def execute(self, capability_ref, arguments, context):
            self.calls.append((capability_ref, arguments, context))
            return {"success": True, "operation": arguments.get("operation")}

    async def run():
        browser = ToolProfileDefinition(
            name="browser_task", version="v-browser", source_type="internal",
            capability_ref="browser.task@v1", external_tool_id="browser.task@v1", description="browser",
            input_schema={"type": "object"}, output_schema={}, risk_level="dangerous",
            approval_required=False, approval_argument="operation", approval_values=("publish", "delete"),
            required_scopes=("capabilities:write",), timeout_ms=1000,
        )
        repo = FakeRepository()
        internal = Internal()
        service = EnterpriseToolService(repo, FakeProfileStore(_profile(browser)), internal)
        claims = _claims([browser])

        read_request = ToolExecuteRequest(
            profileVersion="profile-a", sessionId="session-a", toolName="browser_task",
            actionId="browser-read", idempotencyKey="browser-read", arguments={"operation": "read"},
        )
        assert (await service.execute(read_request, claims)).status == "succeeded"
        assert internal.calls[0][0] == "browser.task@v1"
        assert internal.calls[0][2].turn_context["knowledge_base_ids"] == ["kb-a"]

        publish_request = read_request.model_copy(update={
            "actionId": "browser-publish", "idempotencyKey": "browser-publish", "arguments": {"operation": "publish"},
        })
        with pytest.raises(ToolPolicyDenied, match="approval"):
            await service.execute(publish_request, claims)
        pending = asyncio.create_task(service.request_approval(ApprovalAskRequest(
            profileVersion="profile-a", sessionId="session-a", toolName="browser_task",
            actionId="browser-publish", arguments={"operation": "publish"}, timeoutSeconds=2,
        ), claims))
        while "browser-publish" not in repo.approvals:
            await asyncio.sleep(0)
        await service.decide(
            "browser-publish", decision="approved", actor_id="user-a", tenant_id="tenant-a",
            subject_user_id="user-a", grant_scope="session",
        )
        assert await pending == "allowed-once"
        assert (await service.execute(publish_request, claims)).status == "succeeded"

        second_publish = publish_request.model_copy(update={
            "actionId": "browser-publish-2", "idempotencyKey": "browser-publish-2",
        })
        assert await service.request_approval(ApprovalAskRequest(
            profileVersion="profile-a", sessionId="session-a", toolName="browser_task",
            actionId="browser-publish-2", arguments={"operation": "publish"}, timeoutSeconds=2,
        ), claims) == "allowed-once"
        assert "browser-publish-2" not in repo.approvals
        assert (await service.execute(second_publish, claims)).status == "succeeded"

        delete_ask = asyncio.create_task(service.request_approval(ApprovalAskRequest(
            profileVersion="profile-a", sessionId="session-a", toolName="browser_task",
            actionId="browser-delete", arguments={"operation": "delete"}, timeoutSeconds=2,
        ), claims))
        while "browser-delete" not in repo.approvals:
            await asyncio.sleep(0)
        delete_ask.cancel()
        with pytest.raises(asyncio.CancelledError):
            await delete_ask

    asyncio.run(run())


def test_research_evidence_is_carried_to_later_content_call_without_model_copying() -> None:
    class Internal:
        def __init__(self):
            self.content_context = None
            self.presentation_context = None

        async def execute(self, capability_ref, arguments, context):
            if capability_ref == "research.progressive@v1":
                bundle = {
                    "tools_used": ["progressive_research"],
                    "results": [{
                        "tool": "progressive_research",
                        "title": "Primary source",
                        "source_url": "https://example.test/source",
                        "content": "Verified source fact.",
                        "summary": "Verified source fact.",
                    }],
                    "confirmed_facts": ["Verified source fact."],
                    "evidence_sufficient": True,
                }
                return {
                    "success": True,
                    "evidence_bundle": {"sources": [{"title": "Primary source"}]},
                    "_execution_evidence_bundle": bundle,
                }
            if capability_ref == "content.produce@v1":
                self.content_context = context
                return {"success": True, "markdown": "# Grounded report"}
            self.presentation_context = context
            return {"success": True, "accepted": True}

    class Evidence:
        def __init__(self):
            self.bundle = {}

        async def append(self, **kwargs):
            assert kwargs["message_id"] == "message-a"
            self.bundle = deepcopy(kwargs["bundle"])

        async def load(self, **kwargs):
            assert kwargs["message_id"] == "message-a"
            return deepcopy(self.bundle)

    class ContentContracts:
        async def resolve(self, **kwargs):
            return ResolvedContentInvocation(dict(kwargs["arguments"]))

    class Deliveries:
        def __init__(self):
            self.saved = []
            self.accepted = None

        async def find_accepted(self, **kwargs):
            return deepcopy(self.accepted)

        async def save(self, **kwargs):
            self.saved.append(deepcopy(kwargs))
            if kwargs.get("accepted"):
                self.accepted = {
                    **deepcopy(kwargs),
                    "content": kwargs["markdown"],
                }

    async def run():
        search = ToolProfileDefinition(
            name="progressive_research", version="v-search", source_type="internal",
            capability_ref="research.progressive@v1", external_tool_id="research.progressive@v1",
            description="search", input_schema={"type": "object"}, output_schema={},
            risk_level="read", required_scopes=("capabilities:read",), timeout_ms=1000,
        )
        content = ToolProfileDefinition(
            name="content_production", version="v-content", source_type="internal",
            capability_ref="content.produce@v1", external_tool_id="content.produce@v1",
            description="content", input_schema={"type": "object"}, output_schema={},
            risk_level="read", required_scopes=("capabilities:read",), timeout_ms=1000,
        )
        presentation = ToolProfileDefinition(
            name="presentation_create", version="v-presentation", source_type="internal",
            capability_ref="presentation.create@v1", external_tool_id="presentation.create@v1",
            description="presentation", input_schema={"type": "object"}, output_schema={},
            risk_level="read", required_scopes=("capabilities:read",), timeout_ms=1000,
        )
        repo = FakeRepository()
        repo.binding["active_turn"] = {
            "message_id": "message-a", "status": "running", "turn_context": {}, "turn_metadata": {},
        }
        internal = Internal()
        evidence = Evidence()
        deliveries = Deliveries()
        service = EnterpriseToolService(
            repo, FakeProfileStore(_profile(search, content, presentation)), internal,
            execution_evidence=evidence,
            content_contracts=ContentContracts(),
            authoritative_deliveries=deliveries,
        )
        claims = _claims([search, content, presentation])
        search_receipt = await service.execute(ToolExecuteRequest(
            profileVersion="profile-a", sessionId="session-a", toolName="progressive_research",
            actionId="search-a", idempotencyKey="search-a", arguments={"query": "DSH"},
        ), claims)
        assert search_receipt.status == "succeeded"
        assert "_execution_evidence_bundle" not in search_receipt.result

        content_receipt = await service.execute(ToolExecuteRequest(
            profileVersion="profile-a", sessionId="session-a", toolName="content_production",
            actionId="content-a", idempotencyKey="content-a", arguments={"request": "write"},
        ), claims)
        assert content_receipt.status == "succeeded"
        carried = internal.content_context.turn_context["evidence_bundle"]
        assert carried["results"][0]["source_url"] == "https://example.test/source"
        assert carried["confirmed_facts"] == ["Verified source fact."]
        presentation_receipt = await service.execute(ToolExecuteRequest(
            profileVersion="profile-a", sessionId="session-a", toolName="presentation_create",
            actionId="presentation-a", idempotencyKey="presentation-a",
            arguments={"request": "make slides"},
        ), claims)
        assert presentation_receipt.status == "succeeded"
        assert internal.presentation_context.turn_context["evidence_bundle"] == carried
        assert deliveries.saved == [{
            "action_id": "content-a", "tenant_id": "tenant-a", "user_id": "user-a",
            "message_id": "message-a", "tool_name": "content_production",
            "markdown": "# Grounded report", "accepted": True, "acceptance": {},
        }]

    asyncio.run(run())


def test_accepted_content_is_reused_but_rejected_content_can_retry() -> None:
    class Internal:
        def __init__(self, results):
            self.results = list(results)
            self.calls = 0

        async def execute(self, capability_ref, arguments, context):
            self.calls += 1
            return deepcopy(self.results.pop(0))

    class ContentContracts:
        async def resolve(self, **kwargs):
            return ResolvedContentInvocation(dict(kwargs["arguments"]))

    class Evidence:
        async def load(self, **kwargs):
            return {}

        async def append(self, **kwargs):
            return None

    class Deliveries:
        def __init__(self):
            self.rows = []

        async def find_accepted(self, **scope):
            return next((
                deepcopy(row) for row in reversed(self.rows)
                if row["tenant_id"] == scope["tenant_id"]
                and row["user_id"] == scope["user_id"]
                and row["message_id"] == scope["message_id"]
                and row["tool_name"] == scope["tool_name"]
                and row["accepted"]
            ), None)

        async def save(self, **kwargs):
            self.rows.append({
                **deepcopy(kwargs),
                "content": kwargs["markdown"],
            })

    async def run():
        content = ToolProfileDefinition(
            name="content_production", version="v-content", source_type="internal",
            capability_ref="content.produce@v1", external_tool_id="content.produce@v1",
            description="content", input_schema={"type": "object"}, output_schema={},
            risk_level="read", required_scopes=("capabilities:read",), timeout_ms=1000,
        )
        repo = FakeRepository()
        repo.binding["active_turn"] = {
            "message_id": "message-a", "status": "running", "turn_context": {}, "turn_metadata": {},
        }
        accepted = {
            "success": True, "accepted": True, "markdown": "# Accepted",
            "acceptance": {"status": "accepted", "retry_allowed": False, "reasons": []},
        }
        internal = Internal([accepted, {**accepted, "markdown": "# New message"}])
        deliveries = Deliveries()
        service = EnterpriseToolService(
            repo, FakeProfileStore(_profile(content)), internal,
            execution_evidence=Evidence(), content_contracts=ContentContracts(),
            authoritative_deliveries=deliveries,
        )
        claims = _claims([content])

        first = await service.execute(ToolExecuteRequest(
            profileVersion="profile-a", sessionId="session-a", toolName=content.name,
            actionId="content-1", idempotencyKey="content-1", arguments={"request": "write"},
        ), claims)
        second = await service.execute(ToolExecuteRequest(
            profileVersion="profile-a", sessionId="session-a", toolName=content.name,
            actionId="content-2", idempotencyKey="content-2", arguments={"request": "rewrite"},
        ), claims)
        assert first.result["accepted"] is True
        assert second.result["reused"] is True
        assert second.result["source_action_id"] == "content-1"
        assert second.result["markdown"] == "# Accepted"
        assert internal.calls == 1

        repo.binding["active_turn"]["message_id"] = "message-b"
        third = await service.execute(ToolExecuteRequest(
            profileVersion="profile-a", sessionId="session-a", toolName=content.name,
            actionId="content-3", idempotencyKey="content-3", arguments={"request": "new turn"},
        ), claims)
        assert third.result.get("reused", False) is False
        assert third.result["markdown"] == "# New message"
        assert internal.calls == 2

        rejected_repo = FakeRepository()
        rejected_repo.binding["active_turn"] = deepcopy(repo.binding["active_turn"])
        rejected_internal = Internal([
            {
                "success": False, "accepted": False, "markdown": "# Missing image",
                "acceptance": {
                    "status": "rejected", "retry_allowed": True,
                    "reasons": ["required_visuals_missing"],
                },
                "message": "required visuals were not generated",
            },
            accepted,
        ])
        rejected_deliveries = Deliveries()
        rejected_service = EnterpriseToolService(
            rejected_repo, FakeProfileStore(_profile(content)), rejected_internal,
            execution_evidence=Evidence(), content_contracts=ContentContracts(),
            authoritative_deliveries=rejected_deliveries,
        )
        rejected_claims = _claims([content])
        rejected = await rejected_service.execute(ToolExecuteRequest(
            profileVersion="profile-a", sessionId="session-a", toolName=content.name,
            actionId="rejected-1", idempotencyKey="rejected-1", arguments={"request": "write"},
        ), rejected_claims)
        retried = await rejected_service.execute(ToolExecuteRequest(
            profileVersion="profile-a", sessionId="session-a", toolName=content.name,
            actionId="rejected-2", idempotencyKey="rejected-2", arguments={"request": "retry"},
        ), rejected_claims)
        # A governed rejection is a successful tool observation so DSH receives
        # the structured reasons and may issue a corrected retry.
        assert rejected.status == "succeeded"
        assert rejected.result["accepted"] is False
        assert retried.status == "succeeded"
        assert rejected_internal.calls == 2
        assert len(rejected_deliveries.rows) == 1

    asyncio.run(run())


def test_askai_approval_events_form_one_actionable_lifecycle() -> None:
    class TurnEvents:
        def __init__(self):
            self.rows = []

        def progress_sink(self, message_id, action_id):
            assert (message_id, action_id) == ("message-a", "write-a")

            async def publish(row):
                self.rows.append(deepcopy(row))

            return publish

    async def run():
        write = _tool("askai_mcp_write", source="mcp", approval=True)
        repo = FakeRepository()
        repo.binding["active_turn"] = {"message_id": "message-a"}
        turn_events = TurnEvents()
        service = EnterpriseToolService(
            repo, FakeProfileStore(_profile(write)), turn_events=turn_events
        )
        claims = _claims([write])
        pending = asyncio.create_task(service.request_approval(ApprovalAskRequest(
            profileVersion="profile-a", sessionId="session-a", toolName=write.name,
            actionId="write-a", arguments={"value": "x"}, timeoutSeconds=2,
        ), claims))
        while len(turn_events.rows) < 1:
            await asyncio.sleep(0)
        assert turn_events.rows[0]["type"] == "item.started"
        assert turn_events.rows[0]["item_id"] == "write-a"
        assert turn_events.rows[0]["payload"]["source"] == "askai-approval"
        await service.decide(
            "write-a", decision="approved", actor_id="user-a", tenant_id="tenant-a",
            subject_user_id="user-a",
        )
        assert await pending == "allowed-once"
        assert turn_events.rows[-1]["type"] == "item.completed"
        assert turn_events.rows[-1]["item_id"] == "write-a"
        assert turn_events.rows[-1]["revision"] > turn_events.rows[0]["revision"]

    asyncio.run(run())


def test_tool_gateway_token_tamper_and_subject_scope() -> None:
    service = ToolGatewayTokenService("step-5-tool-signing-secret")
    token = service.issue(
        tenant_id="tenant-a", user_id="user-a", profile_version="profile-a",
        tool_names=["tool-a"], scopes=["tools:read"],
    )
    claims = service.verify(token)
    assert claims.tool_names == {"tool-a"}
    with pytest.raises(ValueError):
        service.verify(token[:-1] + ("A" if token[-1] != "A" else "B"))


def test_model_gateway_preserves_native_tool_calls_and_results() -> None:
    class ToolCallingClient(BaseLLMClient):
        def __init__(self) -> None:
            self.messages = []
            self.kwargs = {}

        async def ainvoke(self, messages, **kwargs):
            raise NotImplementedError

        async def astream(self, messages, **kwargs):
            self.messages = messages
            self.kwargs = kwargs
            yield LLMResponse(message=Message(role=Role.ASSISTANT, content="", tool_calls=[{
                "index": 0, "id": "call-a", "name": "tool-a", "arguments_delta": "{\"x\":"
            }]))
            yield LLMResponse(message=Message(role=Role.ASSISTANT, content="", tool_calls=[{
                "index": 0, "arguments_delta": "1}"
            }]))

        async def ainvoke_structured(self, messages, schema, **kwargs):
            raise NotImplementedError

    async def run():
        client = ToolCallingClient()

        async def factory(*_args):
            return client

        tokens = ModelGatewayTokenService("step-5-model-signing-secret")
        claims = tokens.verify(tokens.issue(
            tenant_id="tenant-a", profile_version="profile-a", model_instance_id="model-a"
        ))
        request = ModelGatewayRequest(
            profileVersion="profile-a", modelInstanceId="model-a", provider="askai-model-gateway",
            model="model", tools=[{"name": "tool-a", "description": "A", "parameters": {"type": "object"}}],
            messages=[
                {"role": "assistant", "content": [{"type": "tool-call", "id": "old", "name": "tool-a", "arguments": "{}"}]},
                {"role": "user", "content": [{"type": "tool-result", "toolCallId": "old", "content": [{"type": "text", "text": "ok"}]}]},
            ],
        )
        stream = await ModelGatewayService(factory).stream(request, claims)
        events = [event async for event in stream]
        assert events[-2] == {"type": "tool-call", "id": "call-a", "name": "tool-a", "arguments": "{\"x\":1}"}
        assert events[-1] == {"type": "finish", "reason": {"kind": "tool-calls"}}
        assert [message.role for message in client.messages] == [Role.ASSISTANT, Role.TOOL]
        assert client.messages[0].tool_calls[0]["function"]["name"] == "tool-a"
        assert client.messages[1].tool_call_id == "old"
        assert client.kwargs["tools"] == [{
            "type": "function",
            "function": {
                "name": "tool-a",
                "description": "A",
                "parameters": {"type": "object"},
            },
        }]
        assert client.kwargs["tool_choice"] == "auto"

    asyncio.run(run())


def test_native_approval_events_remain_audit_only() -> None:
    source = KernelEventSource(kernel_version="0.1.0-rc.6", native_event_type="approval/asked")
    asked = KernelEventEnvelope(
        event_id="event-1", runtime_id="runtime", session_id="session", profile_version="profile-a",
        cursor=1, type="tool.approval.requested", occurred_at=datetime.now(timezone.utc),
        payload={"id": "approval-1", "callId": "action-1", "toolName": "publish", "reason": "write"},
        source=source,
    )
    assert KernelEventProjector().project(asked, message_id="message-a") is None


def test_mcp_structured_content_is_the_dsh_tool_output_value() -> None:
    result = canonical_tool_result({
        "success": True,
        "raw": {
            "content": [{"type": "text", "text": "transport rendering"}],
            "structuredContent": {"code": 0, "data": {"customers": []}},
            "isError": False,
        },
    })
    assert result == {"code": 0, "data": {"customers": []}}
