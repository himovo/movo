from __future__ import annotations

import hashlib
from typing import Any

from pymongo import ReturnDocument

from app.core.db import get_db

from .contracts import (
    EnterpriseActionReceipt,
    EnterpriseApproval,
    EnterpriseSessionApprovalGrant,
    utc_now,
)
from .persistence_codec import restore_json_field, store_json_field


class EnterpriseToolRepository:
    RECEIPTS = "enterprise_action_receipts"
    APPROVALS = "enterprise_tool_approvals"
    AUDIT = "enterprise_tool_audit"
    SESSION_GRANTS = "enterprise_session_approval_grants"

    async def ensure_indexes(self) -> None:
        db = get_db()
        await db[self.RECEIPTS].create_index("action_id", unique=True)
        await db[self.RECEIPTS].create_index("idempotency_key", unique=True)
        await db[self.RECEIPTS].create_index([("tenant_id", 1), ("user_id", 1), ("created_at", -1)])
        await db[self.APPROVALS].create_index("action_id", unique=True)
        await db[self.APPROVALS].create_index([("tenant_id", 1), ("user_id", 1), ("status", 1)])
        await db[self.APPROVALS].create_index(
            [("tenant_id", 1), ("user_id", 1), ("conversation_id", 1), ("status", 1)],
            name="pending_approval_by_conversation",
        )
        await db[self.AUDIT].create_index([("tenant_id", 1), ("occurred_at", -1)])
        await db[self.SESSION_GRANTS].create_index("grant_id", unique=True)
        await db[self.SESSION_GRANTS].create_index(
            [
                ("tenant_id", 1), ("user_id", 1), ("conversation_id", 1),
                ("profile_version", 1), ("scope_key", 1), ("status", 1),
            ],
            name="active_session_approval_grant",
        )

    async def session_binding(self, session_id: str) -> dict[str, Any] | None:
        return await get_db().agent_kernel_bindings.find_one({"kernel_session_id": session_id, "current": True})

    async def receipt_by_idempotency(self, key: str) -> EnterpriseActionReceipt | None:
        row = await get_db()[self.RECEIPTS].find_one({"idempotency_key": key})
        return self._receipt(row)

    async def start_receipt(self, receipt: EnterpriseActionReceipt) -> EnterpriseActionReceipt:
        existing = await self.receipt_by_idempotency(receipt.idempotency_key)
        if existing is not None:
            return existing
        try:
            document = store_json_field(receipt.model_dump(mode="python"), "result")
            await get_db()[self.RECEIPTS].insert_one(document)
            return receipt
        except Exception:
            concurrent = await self.receipt_by_idempotency(receipt.idempotency_key)
            if concurrent is None:
                raise
            return concurrent

    async def finish_receipt(
        self,
        action_id: str,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        error: str = "",
    ) -> EnterpriseActionReceipt:
        row = await get_db()[self.RECEIPTS].find_one_and_update(
            {"action_id": action_id},
            {"$set": {
                "status": status,
                "result_json": store_json_field({"result": dict(result or {})}, "result")["result_json"],
                "error": error[:2000],
                "updated_at": utc_now(),
            }},
            return_document=ReturnDocument.AFTER,
        )
        receipt = self._receipt(row)
        if receipt is None:
            raise LookupError("action receipt not found")
        return receipt

    async def ensure_approval(self, approval: EnterpriseApproval) -> EnterpriseApproval:
        document = store_json_field(approval.model_dump(mode="python"), "arguments")
        await get_db()[self.APPROVALS].update_one(
            {"action_id": approval.action_id},
            {"$setOnInsert": document},
            upsert=True,
        )
        row = await get_db()[self.APPROVALS].find_one({"action_id": approval.action_id})
        return EnterpriseApproval.model_validate(self._clean(row))

    async def approval(self, action_id: str) -> EnterpriseApproval | None:
        row = await get_db()[self.APPROVALS].find_one({"action_id": action_id})
        return EnterpriseApproval.model_validate(self._clean(row)) if row else None

    async def decide(self, action_id: str, *, decision: str, actor_id: str, tenant_id: str) -> EnterpriseApproval | None:
        row = await get_db()[self.APPROVALS].find_one_and_update(
            {"action_id": action_id, "tenant_id": tenant_id, "status": "pending"},
            {"$set": {"status": decision, "decided_by": actor_id, "updated_at": utc_now()}},
            return_document=ReturnDocument.AFTER,
        )
        return EnterpriseApproval.model_validate(self._clean(row)) if row else None

    async def set_approval_grant_scope(self, action_id: str, grant_scope: str) -> None:
        await get_db()[self.APPROVALS].update_one(
            {"action_id": action_id},
            {"$set": {"grant_scope": grant_scope, "updated_at": utc_now()}},
        )

    async def expire(self, action_id: str) -> EnterpriseApproval | None:
        row = await get_db()[self.APPROVALS].find_one_and_update(
            {"action_id": action_id, "status": "pending"},
            {"$set": {"status": "expired", "updated_at": utc_now()}},
            return_document=ReturnDocument.AFTER,
        )
        return EnterpriseApproval.model_validate(self._clean(row)) if row else None

    async def list_pending(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str | None = None,
    ) -> list[EnterpriseApproval]:
        query: dict[str, Any] = {"tenant_id": tenant_id, "user_id": user_id, "status": "pending"}
        if conversation_id:
            query["conversation_id"] = conversation_id
        cursor = get_db()[self.APPROVALS].find(query).sort("created_at", -1)
        return [EnterpriseApproval.model_validate(self._clean(row)) async for row in cursor]

    async def active_session_grant(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        profile_version: str,
        scope_key: str,
    ) -> EnterpriseSessionApprovalGrant | None:
        row = await get_db()[self.SESSION_GRANTS].find_one({
            "tenant_id": tenant_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "profile_version": profile_version,
            "scope_key": scope_key,
            "status": "active",
        })
        return EnterpriseSessionApprovalGrant.model_validate(self._clean(row)) if row else None

    async def grant_for_session(
        self,
        approval: EnterpriseApproval,
        *,
        actor_id: str,
    ) -> EnterpriseSessionApprovalGrant:
        grant_id_source = "\x1f".join((
            approval.tenant_id,
            approval.user_id,
            approval.conversation_id,
            approval.profile_version,
            approval.scope_key,
        ))
        grant = EnterpriseSessionApprovalGrant(
            grant_id=f"grant-{hashlib.sha256(grant_id_source.encode('utf-8')).hexdigest()}",
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
        await get_db()[self.SESSION_GRANTS].update_one(
            {"grant_id": grant.grant_id},
            {"$setOnInsert": grant.model_dump(mode="python")},
            upsert=True,
        )
        row = await get_db()[self.SESSION_GRANTS].find_one({"grant_id": grant.grant_id})
        return EnterpriseSessionApprovalGrant.model_validate(self._clean(row))

    async def audit(self, *, tenant_id: str, user_id: str, action_id: str, event: str, details: dict[str, Any]) -> None:
        await get_db()[self.AUDIT].insert_one({
            "tenant_id": tenant_id,
            "user_id": user_id,
            "action_id": action_id,
            "event": event,
            "details_json": store_json_field({"details": dict(details)}, "details")["details_json"],
            "occurred_at": utc_now(),
        })

    @staticmethod
    def _clean(row: dict[str, Any] | None) -> dict[str, Any]:
        result = dict(row or {})
        result.pop("_id", None)
        result = restore_json_field(result, "result")
        result = restore_json_field(result, "arguments")
        result = restore_json_field(result, "details")
        return result

    @classmethod
    def _receipt(cls, row: dict[str, Any] | None) -> EnterpriseActionReceipt | None:
        return EnterpriseActionReceipt.model_validate(cls._clean(row)) if row else None
