"""Execution-scoped transport for the existing ASKAI evidence bundle."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.db import get_db
from app.enterprise_capabilities.evidence.foundation import normalize_evidence_bundle


class ExecutionEvidenceRepository:
    """Attach upstream evidence to the active DSH turn without changing its schema."""

    COLLECTION = "agent_kernel_bindings"

    async def append(
        self,
        *,
        tenant_id: str,
        user_id: str,
        kernel_session_id: str,
        message_id: str,
        action_id: str,
        bundle: dict[str, Any],
    ) -> None:
        if not message_id or not bundle:
            return
        result = await get_db()[self.COLLECTION].update_one(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "kernel_session_id": kernel_session_id,
                "active_turn.message_id": message_id,
                "active_turn.status": "running",
            },
            {
                "$push": {
                    "active_turn.evidence_bundles": {
                        "$each": [{
                            "action_id": action_id,
                            "bundle": normalize_evidence_bundle(bundle),
                            "created_at": datetime.utcnow(),
                        }],
                        "$slice": -12,
                    }
                }
            },
        )
        if result.matched_count != 1:
            raise LookupError("active execution evidence scope is unavailable")

    async def load(
        self,
        *,
        tenant_id: str,
        user_id: str,
        kernel_session_id: str,
        message_id: str,
    ) -> dict[str, Any]:
        if not message_id:
            return {}
        row = await get_db()[self.COLLECTION].find_one(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "kernel_session_id": kernel_session_id,
                "active_turn.message_id": message_id,
            },
            {"active_turn.evidence_bundles": 1},
        )
        entries = list(((row or {}).get("active_turn") or {}).get("evidence_bundles") or [])
        if not entries:
            return {}

        merged: dict[str, Any] = {
            "results": [], "raw_tool_results": [], "confirmed_facts": [],
            "open_questions": [], "tools_used": [],
        }
        sufficiency: list[bool] = []
        for entry in entries:
            bundle = entry.get("bundle") if isinstance(entry, dict) else None
            if not isinstance(bundle, dict):
                continue
            for key in ("results", "raw_tool_results", "confirmed_facts", "open_questions", "tools_used"):
                merged[key].extend(list(bundle.get(key) or []))
            if "evidence_sufficient" in bundle:
                sufficiency.append(bool(bundle.get("evidence_sufficient")))
            if bundle.get("budget_exhausted"):
                merged["budget_exhausted"] = True
            if bundle.get("stop_reason"):
                merged["stop_reason"] = str(bundle.get("stop_reason"))
        normalized = normalize_evidence_bundle(merged)
        normalized["tools_used"] = list(dict.fromkeys(str(x) for x in merged["tools_used"] if str(x)))
        if sufficiency:
            normalized["evidence_sufficient"] = all(sufficiency)
        return normalized


__all__ = ["ExecutionEvidenceRepository"]
