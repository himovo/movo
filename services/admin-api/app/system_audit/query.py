from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import json
import re

from app.core.db import get_db
from .constants import SYSTEM_AUDIT_COLLECTION


def iso(value: Any) -> str:
    if not isinstance(value, datetime):
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


class SystemAuditQuery:
    def __init__(self, db: Any | None = None) -> None:
        self.db = db or get_db()

    async def list_logs(
        self,
        *,
        main_id: str,
        category: str,
        page: int,
        page_size: int,
        keyword: str = "",
        result: str = "",
        module: str = "",
    ) -> dict[str, Any]:
        if category == "management":
            return await self._management(main_id, page, page_size, keyword, result, module)
        if category == "agent":
            return await self._agent(main_id, page, page_size, keyword, result)
        return await self._legacy(main_id, page, page_size, keyword)

    async def overview(self, main_id: str, since: datetime) -> dict[str, int]:
        management = {"main_id": main_id, "occurred_at": {"$gte": since}}
        return {
            "managementOperations": await self.db[SYSTEM_AUDIT_COLLECTION].count_documents(management),
            "failedOperations": await self.db[SYSTEM_AUDIT_COLLECTION].count_documents({**management, "result": "failed"}),
            "agentActivities": await self.db.position_role_audit_logs.count_documents({
                "main_id": main_id, "created_at": {"$gte": since}, "action": {"$regex": r"^capability\."},
            }),
            "permissionDenials": await self.db.position_role_audit_logs.count_documents({
                "main_id": main_id, "created_at": {"$gte": since}, "action": "capability.denied",
            }),
        }

    async def _management(self, main_id: str, page: int, page_size: int, keyword: str, result: str, module: str) -> dict[str, Any]:
        query: dict[str, Any] = {"main_id": main_id}
        if result in {"success", "failed"}:
            query["result"] = result
        if module:
            query["module"] = module
        if keyword.strip():
            pattern = re.escape(keyword.strip())
            query["$or"] = [
                {"actor": {"$regex": pattern, "$options": "i"}},
                {"module_label": {"$regex": pattern, "$options": "i"}},
                {"route": {"$regex": pattern, "$options": "i"}},
                {"target": {"$regex": pattern, "$options": "i"}},
            ]
        total = await self.db[SYSTEM_AUDIT_COLLECTION].count_documents(query)
        rows = await self.db[SYSTEM_AUDIT_COLLECTION].find(query).sort("occurred_at", -1).skip((page - 1) * page_size).limit(page_size).to_list(length=page_size)
        return self._page(page, page_size, total, [self._management_item(row) for row in rows])

    async def _agent(self, main_id: str, page: int, page_size: int, keyword: str, result: str) -> dict[str, Any]:
        limit = page * page_size
        position_query: dict[str, Any] = {"main_id": main_id, "action": {"$regex": r"^capability\."}}
        tool_query: dict[str, Any] = {"tenant_id": main_id}
        if result == "failed":
            position_query["action"] = "capability.denied"
            tool_query["event"] = {"$regex": "denied|failed", "$options": "i"}
        elif result == "success":
            position_query["action"] = "capability.used"
            tool_query["event"] = {"$not": {"$regex": "denied|failed", "$options": "i"}}
        if keyword.strip():
            pattern = re.escape(keyword.strip())
            position_query["$or"] = [{"actor": {"$regex": pattern, "$options": "i"}}, {"details.target": {"$regex": pattern, "$options": "i"}}]
            tool_query["$or"] = [{"user_id": {"$regex": pattern, "$options": "i"}}, {"event": {"$regex": pattern, "$options": "i"}}, {"action_id": {"$regex": pattern, "$options": "i"}}]
        total = await self.db.position_role_audit_logs.count_documents(position_query) + await self.db.enterprise_tool_audit.count_documents(tool_query)
        position_rows = await self.db.position_role_audit_logs.find(position_query).sort("created_at", -1).limit(limit).to_list(length=limit)
        tool_rows = await self.db.enterprise_tool_audit.find(tool_query).sort("occurred_at", -1).limit(limit).to_list(length=limit)
        items = [self._position_item(row) for row in position_rows] + [self._tool_item(row) for row in tool_rows]
        items.sort(key=lambda item: item["occurredAt"], reverse=True)
        return self._page(page, page_size, total, items[(page - 1) * page_size:page * page_size])

    async def _legacy(self, main_id: str, page: int, page_size: int, keyword: str) -> dict[str, Any]:
        limit = page * page_size
        directory_query: dict[str, Any] = {"main_id": main_id}
        role_query: dict[str, Any] = {"main_id": main_id, "action": {"$not": {"$regex": r"^capability\."}}}
        if keyword.strip():
            pattern = re.escape(keyword.strip())
            directory_query["$or"] = [{"operator": {"$regex": pattern, "$options": "i"}}, {"action": {"$regex": pattern, "$options": "i"}}, {"target_type": {"$regex": pattern, "$options": "i"}}]
            role_query["$or"] = [{"actor": {"$regex": pattern, "$options": "i"}}, {"action": {"$regex": pattern, "$options": "i"}}, {"target_type": {"$regex": pattern, "$options": "i"}}]
        total = await self.db.audit_logs.count_documents(directory_query) + await self.db.position_role_audit_logs.count_documents(role_query)
        directory_rows = await self.db.audit_logs.find(directory_query).sort("created_at", -1).limit(limit).to_list(length=limit)
        role_rows = await self.db.position_role_audit_logs.find(role_query).sort("created_at", -1).limit(limit).to_list(length=limit)
        items = [self._legacy_directory_item(row) for row in directory_rows] + [self._position_item(row, category="legacy") for row in role_rows]
        items.sort(key=lambda item: item["occurredAt"], reverse=True)
        return self._page(page, page_size, total, items[(page - 1) * page_size:page * page_size])

    @staticmethod
    def _page(page: int, page_size: int, total: int, items: list[dict[str, Any]]) -> dict[str, Any]:
        return {"page": page, "pageSize": page_size, "total": total, "items": items}

    @staticmethod
    def _management_item(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row.get("_id") or ""), "category": "management", "module": str(row.get("module_label") or row.get("module") or "管理后台"),
            "action": str(row.get("action") or ""), "actor": str(row.get("actor") or ""), "target": str(row.get("target") or row.get("route") or ""),
            "result": str(row.get("result") or "success"), "statusCode": int(row.get("status_code") or 0), "occurredAt": iso(row.get("occurred_at")),
            "details": {"method": row.get("method"), "route": row.get("route"), "durationMs": row.get("duration_ms"), "clientIp": row.get("client_ip")},
        }

    @staticmethod
    def _position_item(row: dict[str, Any], category: str = "agent") -> dict[str, Any]:
        details = dict(row.get("details") or {})
        return {
            "id": str(row.get("_id") or ""), "category": category, "module": "Agent 能力", "action": str(row.get("action") or ""),
            "actor": str(row.get("actor") or ""), "target": str(details.get("target") or row.get("target_id") or ""),
            "result": "failed" if str(row.get("action") or "").endswith("denied") else "success", "statusCode": 0,
            "occurredAt": iso(row.get("created_at")), "details": details,
        }

    @staticmethod
    def _tool_item(row: dict[str, Any]) -> dict[str, Any]:
        try:
            details = json.loads(str(row.get("details_json") or "{}"))
        except (TypeError, ValueError):
            details = {}
        event = str(row.get("event") or "")
        return {
            "id": str(row.get("_id") or ""), "category": "agent", "module": "工具与 MCP", "action": event,
            "actor": str(row.get("user_id") or ""), "target": str(row.get("action_id") or ""),
            "result": "failed" if re.search("denied|failed", event, re.I) else "success", "statusCode": 0,
            "occurredAt": iso(row.get("occurred_at")), "details": details if isinstance(details, dict) else {},
        }

    @staticmethod
    def _legacy_directory_item(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row.get("_id") or ""), "category": "legacy", "module": str(row.get("target_type") or "历史管理操作"),
            "action": str(row.get("action") or ""), "actor": str(row.get("operator") or ""), "target": str(row.get("target_id") or ""),
            "result": "success", "statusCode": 0, "occurredAt": iso(row.get("created_at")), "details": dict(row.get("payload") or {}),
        }
