from __future__ import annotations

import datetime
import json
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

import httpx

from app.api.time_utils import utc_iso
from app.core.db import get_db
from app.core.tenant import add_main_scope, resolve_main_id
from app.llm.factory import get_llm_client
from app.llm.types import Message, Role
from app.services.external_tool_limits import MCP_ENABLED_TOOL_LIMIT, enabled_mcp_tool_names, validate_mcp_activation


TOOL_TYPES = {"http", "mcp"}
TOOL_STATUSES = {"active", "disabled"}
MONGO_DOLLAR_PREFIX = "\uff04"
MONGO_DOT = "\uff0e"
logger = logging.getLogger("app.external_tools")


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _mongo_safe_key(key: Any) -> str:
    text = str(key)
    if text.startswith("$"):
        text = f"{MONGO_DOLLAR_PREFIX}{text[1:]}"
    return text.replace(".", MONGO_DOT)


def _mongo_restore_key(key: Any) -> str:
    text = str(key)
    if text.startswith(MONGO_DOLLAR_PREFIX):
        text = f"${text[1:]}"
    return text.replace(MONGO_DOT, ".")


def _mongo_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {_mongo_safe_key(key): _mongo_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_mongo_safe_value(item) for item in value]
    return value


def _mongo_restore_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {_mongo_restore_key(key): _mongo_restore_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_mongo_restore_value(item) for item in value]
    return value


def _serialize_time(value: Any) -> Optional[str]:
    return utc_iso(value) or None


def _short_text(value: Any, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    scope = str(doc.get("scope") or "organization").strip().lower()
    if scope not in {"user", "organization"}:
        scope = "organization"
    return {
        "id": str(doc.get("_id") or ""),
        "mainId": resolve_main_id(doc.get("main_id")),
        "scope": scope,
        "ownerUserId": str(doc.get("owner_user_id") or ""),
        "name": str(doc.get("name") or ""),
        "type": str(doc.get("type") or "http"),
        "description": str(doc.get("description") or ""),
        "usageHint": str(doc.get("usage_hint") or ""),
        "tags": [str(item) for item in _safe_list(doc.get("tags")) if str(item).strip()],
        "status": str(doc.get("status") or "disabled"),
        "config": _safe_dict(doc.get("config")),
        "lastTestStatus": str(doc.get("last_test_status") or "untested"),
        "lastTestAt": _serialize_time(doc.get("last_test_at")),
        "lastTestMessage": str(doc.get("last_test_message") or ""),
        "discoveredTools": _safe_list(_mongo_restore_value(doc.get("discovered_tools"))),
        "createdAt": _serialize_time(doc.get("created_at")),
        "updatedAt": _serialize_time(doc.get("updated_at")),
    }


def _normalize_payload(payload: Dict[str, Any], *, partial: bool = False) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    if not partial or "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("工具名称不能为空")
        patch["name"] = name[:120]
    if not partial or "type" in payload:
        tool_type = str(payload.get("type") or "http").strip().lower()
        if tool_type not in TOOL_TYPES:
            raise ValueError("工具类型只支持 HTTP 接口或 MCP 服务")
        patch["type"] = tool_type
    if "description" in payload or not partial:
        patch["description"] = str(payload.get("description") or "").strip()
    if "usageHint" in payload or "usage_hint" in payload or not partial:
        patch["usage_hint"] = str(payload.get("usageHint", payload.get("usage_hint", "")) or "").strip()
    if "tags" in payload or not partial:
        tags = []
        for item in _safe_list(payload.get("tags")):
            tag = str(item or "").strip()
            if tag and tag not in tags:
                tags.append(tag[:40])
        patch["tags"] = tags[:20]
    if "status" in payload or not partial:
        status = str(payload.get("status") or "disabled").strip().lower()
        if status not in TOOL_STATUSES:
            raise ValueError("状态只支持 active 或 disabled")
        patch["status"] = status
    if "config" in payload or not partial:
        patch["config"] = _safe_dict(payload.get("config"))
    return patch


def _merged_tool_state(existing: Dict[str, Any] | None, patch: Dict[str, Any]) -> Dict[str, Any]:
    existing = existing or {}
    return {
        "type": patch.get("type", existing.get("type", "http")),
        "status": patch.get("status", existing.get("status", "disabled")),
        "config": patch.get("config", existing.get("config", {})),
    }


class ExternalToolService:
    async def ensure_indexes(self) -> None:
        db = get_db()
        await db.external_tools.create_index([("main_id", 1), ("updated_at", -1)])
        await db.external_tools.create_index([("main_id", 1), ("status", 1), ("type", 1)])
        await db.external_tools.create_index([("main_id", 1), ("scope", 1), ("owner_user_id", 1), ("updated_at", -1)])

    async def list(
        self,
        main_id: str = "default",
        *,
        enabled_only: bool = False,
        scope: str = "organization",
        owner_user_id: str = "",
    ) -> List[Dict[str, Any]]:
        db = get_db()
        query: Dict[str, Any] = {}
        if enabled_only:
            query["status"] = "active"
        normalized_scope = str(scope or "organization").strip().lower()
        if normalized_scope == "user":
            query["scope"] = "user"
            query["owner_user_id"] = str(owner_user_id or "").strip()
        else:
            query["$or"] = [{"scope": "organization"}, {"scope": {"$exists": False}}, {"scope": ""}]
        cursor = db.external_tools.find(add_main_scope(query, main_id)).sort("updated_at", -1)
        return [_serialize(doc) async for doc in cursor]

    async def list_visible(self, main_id: str = "default", *, user_id: str = "", enabled_only: bool = False) -> List[Dict[str, Any]]:
        user_tools = await self.list(main_id, enabled_only=enabled_only, scope="user", owner_user_id=user_id) if str(user_id or "").strip() else []
        org_tools = await self.list(main_id, enabled_only=enabled_only, scope="organization")
        hidden_org_keys = {
            (str(item.get("type") or ""), str(item.get("name") or "").strip().lower())
            for item in user_tools
            if str(item.get("name") or "").strip()
        }
        visible = list(user_tools)
        for item in org_tools:
            key = (str(item.get("type") or ""), str(item.get("name") or "").strip().lower())
            if key in hidden_org_keys:
                continue
            visible.append(item)
        return visible

    async def get(
        self,
        tool_id: str,
        main_id: str = "default",
        *,
        scope: str = "organization",
        owner_user_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        db = get_db()
        query: Dict[str, Any] = {"_id": str(tool_id)}
        normalized_scope = str(scope or "organization").strip().lower()
        if normalized_scope == "user":
            query.update({"scope": "user", "owner_user_id": str(owner_user_id or "").strip()})
        elif normalized_scope == "any":
            pass
        else:
            query["$or"] = [{"scope": "organization"}, {"scope": {"$exists": False}}, {"scope": ""}]
        doc = await db.external_tools.find_one(add_main_scope(query, main_id))
        return _serialize(doc) if doc else None

    async def create(
        self,
        payload: Dict[str, Any],
        main_id: str = "default",
        *,
        scope: str = "organization",
        owner_user_id: str = "",
    ) -> Dict[str, Any]:
        db = get_db()
        now = _now()
        normalized_scope = "user" if str(scope or "").strip().lower() == "user" else "organization"
        doc = {
            "_id": uuid.uuid4().hex,
            "main_id": resolve_main_id(main_id),
            "scope": normalized_scope,
            "owner_user_id": str(owner_user_id or "").strip() if normalized_scope == "user" else "",
            **_normalize_payload(payload),
            "status": "disabled",
            "last_test_status": "untested",
            "last_test_at": None,
            "last_test_message": "",
            "discovered_tools": [],
            "created_at": now,
            "updated_at": now,
        }
        await db.external_tools.insert_one(doc)
        return _serialize(doc)

    async def update(
        self,
        tool_id: str,
        payload: Dict[str, Any],
        main_id: str = "default",
        *,
        scope: str = "organization",
        owner_user_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        db = get_db()
        patch = _normalize_payload(payload, partial=True)
        if not patch:
            return await self.get(tool_id, main_id, scope=scope, owner_user_id=owner_user_id)
        existing = await self.get(tool_id, main_id, scope=scope, owner_user_id=owner_user_id)
        if not existing:
            return None
        final_state = _merged_tool_state(existing, patch)
        validate_mcp_activation(
            tool_type=str(final_state.get("type") or ""),
            status=str(final_state.get("status") or ""),
            config=_safe_dict(final_state.get("config")),
        )
        patch["updated_at"] = _now()
        query: Dict[str, Any] = {"_id": str(tool_id)}
        if str(scope or "organization").strip().lower() == "user":
            query.update({"scope": "user", "owner_user_id": str(owner_user_id or "").strip()})
        else:
            query["$or"] = [{"scope": "organization"}, {"scope": {"$exists": False}}, {"scope": ""}]
        result = await db.external_tools.update_one(add_main_scope(query, main_id), {"$set": patch})
        if not result.matched_count:
            return None
        return await self.get(tool_id, main_id, scope=scope, owner_user_id=owner_user_id)

    async def delete(
        self,
        tool_id: str,
        main_id: str = "default",
        *,
        scope: str = "organization",
        owner_user_id: str = "",
    ) -> bool:
        db = get_db()
        query: Dict[str, Any] = {"_id": str(tool_id)}
        if str(scope or "organization").strip().lower() == "user":
            query.update({"scope": "user", "owner_user_id": str(owner_user_id or "").strip()})
        else:
            query["$or"] = [{"scope": "organization"}, {"scope": {"$exists": False}}, {"scope": ""}]
        result = await db.external_tools.delete_one(add_main_scope(query, main_id))
        return bool(result.deleted_count)

    async def test(
        self,
        tool_id: str,
        test_input: Dict[str, Any],
        main_id: str = "default",
        *,
        scope: str = "organization",
        owner_user_id: str = "",
    ) -> Dict[str, Any]:
        tool = await self.get(tool_id, main_id, scope=scope, owner_user_id=owner_user_id)
        if not tool:
            raise ValueError("工具连接不存在")
        logger.info(
            "external_tool_test_received tool_id=%s main_id=%s tool_type=%s tool_name=%s config=%s test_input=%s",
            tool_id,
            main_id,
            tool.get("type"),
            tool.get("name"),
            _short_text(tool.get("config"), 5000),
            _short_text(test_input, 5000),
        )
        started = time.monotonic()
        try:
            if tool["type"] == "mcp":
                result = await self._test_mcp(tool, test_input)
            else:
                result = await self._test_http(tool, test_input)
            logger.info(
                "external_tool_test_result tool_id=%s success=%s status=%s message=%s debug=%s",
                tool_id,
                result.get("success"),
                result.get("status"),
                result.get("message"),
                _short_text(result.get("debug"), 5000),
            )
            result["durationMs"] = int((time.monotonic() - started) * 1000)
            await self._record_test(tool_id, main_id, "passed" if result.get("success") else "failed", result.get("message", ""))
            return result
        except httpx.TimeoutException:
            timeout_seconds = float(_safe_dict(tool.get("config")).get("timeoutSeconds") or 15)
            message = f"请求超时：超过 {timeout_seconds:g} 秒未收到响应"
            result = {
                "success": False,
                "status": "failed",
                "errorCode": "timeout",
                "message": message,
                "responseSummary": message,
                "durationMs": int((time.monotonic() - started) * 1000),
            }
            await self._record_test(tool_id, main_id, "failed", message)
            return result
        except Exception as exc:
            logger.exception("external_tool_test_exception tool_id=%s err=%s", tool_id, str(exc))
            result = {
                "success": False,
                "status": "failed",
                "message": str(exc),
                "durationMs": int((time.monotonic() - started) * 1000),
            }
            await self._record_test(tool_id, main_id, "failed", str(exc))
            return result

    async def test_draft(self, payload: Dict[str, Any], test_input: Dict[str, Any], main_id: str = "default") -> Dict[str, Any]:
        started = time.monotonic()
        try:
            normalized = _normalize_payload(payload)
            tool = {
                "id": "draft",
                "mainId": resolve_main_id(main_id),
                "name": normalized.get("name") or "未保存工具",
                "type": normalized.get("type") or "http",
                "description": normalized.get("description") or "",
                "usageHint": normalized.get("usage_hint") or "",
                "tags": _safe_list(normalized.get("tags")),
                "status": normalized.get("status") or "active",
                "config": _safe_dict(normalized.get("config")),
                "discoveredTools": [],
            }
            logger.info(
                "external_tool_draft_test_received main_id=%s tool_type=%s tool_name=%s config=%s test_input=%s",
                main_id,
                tool.get("type"),
                tool.get("name"),
                _short_text(tool.get("config"), 5000),
                _short_text(test_input, 5000),
            )
            if tool["type"] == "mcp":
                result = await self._test_mcp(tool, test_input)
            else:
                result = await self._test_http(tool, test_input)
            result["durationMs"] = int((time.monotonic() - started) * 1000)
            return result
        except httpx.TimeoutException:
            timeout_seconds = float(_safe_dict(tool.get("config")).get("timeoutSeconds") or 15)
            message = f"请求超时：超过 {timeout_seconds:g} 秒未收到响应"
            return {
                "success": False,
                "status": "failed",
                "errorCode": "timeout",
                "message": message,
                "responseSummary": message,
                "durationMs": int((time.monotonic() - started) * 1000),
            }
        except Exception as exc:
            logger.exception("external_tool_draft_test_exception err=%s", str(exc))
            return {
                "success": False,
                "status": "failed",
                "message": str(exc),
                "durationMs": int((time.monotonic() - started) * 1000),
            }

    async def discover_mcp_tools(
        self,
        tool_id: str,
        main_id: str = "default",
        *,
        scope: str = "organization",
        owner_user_id: str = "",
    ) -> Dict[str, Any]:
        tool = await self.get(tool_id, main_id, scope=scope, owner_user_id=owner_user_id)
        if not tool:
            raise ValueError("工具连接不存在")
        if tool["type"] != "mcp":
            raise ValueError("只有 MCP 服务支持发现 tools")
        result = await self._mcp_jsonrpc(tool, "tools/list", {})
        tools = result.get("tools") if isinstance(result, dict) else []
        normalized = []
        for item in _safe_list(tools):
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "name": str(item.get("name") or ""),
                    "description": str(item.get("description") or ""),
                    "inputSchema": item.get("inputSchema") if isinstance(item.get("inputSchema"), dict) else {},
                    "outputSchema": item.get("outputSchema") if isinstance(item.get("outputSchema"), dict) else {},
                    "annotations": item.get("annotations") if isinstance(item.get("annotations"), dict) else {},
                }
            )
        db = get_db()
        update_fields: Dict[str, Any] = {"discovered_tools": _mongo_safe_value(normalized), "updated_at": _now()}
        if len(normalized) > MCP_ENABLED_TOOL_LIMIT:
            update_fields["status"] = "disabled"
        await db.external_tools.update_one(
            add_main_scope(
                {"_id": str(tool_id), **({"scope": "user", "owner_user_id": str(owner_user_id or "").strip()} if str(scope or "organization").strip().lower() == "user" else {})},
                main_id,
            ),
            {"$set": update_fields},
        )
        message = f"发现 {len(normalized)} 个 MCP tools"
        if len(normalized) > MCP_ENABLED_TOOL_LIMIT:
            message += f"，超过 {MCP_ENABLED_TOOL_LIMIT} 个，已保持禁用；请选择不超过 {MCP_ENABLED_TOOL_LIMIT} 个工具后再启用"
        return {"success": True, "tools": normalized, "message": message}

    async def execute_runtime(
        self,
        *,
        main_id: str = "default",
        external_tool_id: str,
        provider_type: str,
        mcp_tool_name: str = "",
        arguments: Dict[str, Any] | None = None,
        actor_user_id: str = "",
    ) -> Dict[str, Any]:
        """Execute an enabled enterprise tool from the runtime path.

        Admin tests and agent execution intentionally share the same low-level
        HTTP/MCP resolvers, but this method does not mutate last-test metadata.
        """
        started = time.monotonic()
        tool = await self.get(external_tool_id, main_id, scope="any")
        if not tool:
            raise ValueError("工具连接不存在")
        if str(tool.get("status") or "active") != "active":
            raise ValueError("工具连接未启用")
        if provider_type and str(tool.get("type") or "") != str(provider_type):
            raise ValueError("工具类型不匹配")
        args = _safe_dict(arguments)
        logger.info(
            "external_tool_runtime_execute_received main_id=%s tool_id=%s provider_type=%s tool_type=%s tool_name=%s mcp_tool_name=%s arg_keys=%s",
            main_id,
            external_tool_id,
            provider_type,
            tool.get("type"),
            tool.get("name"),
            mcp_tool_name,
            sorted([str(k) for k in args.keys()]),
        )
        if tool["type"] == "mcp":
            tool_name = str(mcp_tool_name or "").strip()
            if not tool_name:
                raise ValueError("MCP toolName 不能为空")
            config = _safe_dict(tool.get("config"))
            enabled = set(enabled_mcp_tool_names(config))
            if not enabled:
                raise ValueError("MCP 未选择可用工具，请先在工具配置中选择允许 Agent 使用的 MCP 工具")
            if len(enabled) > MCP_ENABLED_TOOL_LIMIT:
                raise ValueError(f"MCP 启用工具超过上限 {MCP_ENABLED_TOOL_LIMIT} 个，请减少后再调用")
            if tool_name not in enabled:
                raise ValueError(f"MCP 工具未启用：{tool_name}")
            result = await self._mcp_jsonrpc(
                tool,
                "tools/call",
                {"name": tool_name, "arguments": args},
                runtime_headers={
                    "X-MOVO-Main-ID": resolve_main_id(main_id),
                    "X-MOVO-User-ID": str(actor_user_id or "").strip(),
                    "X-AskAI-Main-ID": resolve_main_id(main_id),
                    "X-AskAI-User-ID": str(actor_user_id or "").strip(),
                },
            )
            logger.info(
                "external_tool_runtime_execute_result main_id=%s tool_id=%s provider_type=mcp mcp_tool_name=%s success=%s duration_ms=%s",
                main_id,
                external_tool_id,
                tool_name,
                True,
                int((time.monotonic() - started) * 1000),
            )
            return {
                "success": True,
                "status": "passed",
                "message": f"MCP tool {tool_name} 调用成功",
                "responseSummary": _short_text(result),
                "raw": result,
                "durationMs": int((time.monotonic() - started) * 1000),
            }
        resolved_input = self._build_http_runtime_input(tool, args)
        result = await self._test_http(tool, resolved_input)
        result["durationMs"] = int((time.monotonic() - started) * 1000)
        logger.info(
            "external_tool_runtime_execute_result main_id=%s tool_id=%s provider_type=http success=%s message=%s duration_ms=%s",
            main_id,
            external_tool_id,
            bool(result.get("success")),
            str(result.get("message") or ""),
            result["durationMs"],
        )
        return result

    async def generate_description(self, *, name: str, tool_type: str = "http", existing_description: str = "") -> Dict[str, Any]:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValueError("工具名称不能为空")
        normalized_type = str(tool_type or "http").strip().lower()
        if normalized_type not in TOOL_TYPES:
            normalized_type = "http"
        existing = str(existing_description or "").strip()

        system_prompt = (
            "你是资深平台产品经理，负责为 AI Agent 工具编写高质量工具说明。"
            "输出必须是简体中文，1 段话，60-120 字，重点说明该工具做什么、典型输入和输出、"
            "以及 agent 何时优先调用。不要使用项目符号、不要添加标题、不要输出多段。"
        )
        user_prompt = (
            f"工具名称：{normalized_name}\n"
            f"工具类型：{'MCP 服务' if normalized_type == 'mcp' else 'HTTP 工具'}\n"
            f"已有说明：{existing or '（无）'}\n"
            "请直接生成可用于“工具说明”输入框的最终文案。"
        )
        try:
            llm = get_llm_client(streaming=False, stage="admin_tool_description", intent="generation")
            resp = await llm.ainvoke(
                [
                    Message(role=Role.SYSTEM, content=system_prompt),
                    Message(role=Role.USER, content=user_prompt),
                ]
            )
            generated = str((resp.content if resp else "") or "").strip()
            if not generated:
                raise ValueError("empty llm response")
            generated = re.sub(r"\s+", " ", generated).strip()
            if len(generated) > 220:
                generated = generated[:220].rstrip("，,。.!！?？ ") + "。"
            return {"description": generated}
        except Exception:
            fallback = (
                f"{normalized_name}用于连接{'MCP 服务' if normalized_type == 'mcp' else '外部 HTTP 接口'}，"
                "帮助 Agent 在需要查询、执行或同步外部业务数据时完成调用，"
                "并返回结构化结果供后续分析与回复。"
            )
            return {"description": fallback}

    async def _record_test(self, tool_id: str, main_id: str, status: str, message: str) -> None:
        db = get_db()
        await db.external_tools.update_one(
            add_main_scope({"_id": str(tool_id)}, main_id),
            {
                "$set": {
                    "last_test_status": status,
                    "last_test_at": _now(),
                    "last_test_message": _short_text(message, 500),
                    "updated_at": _now(),
                }
            },
        )

    async def _test_http(self, tool: Dict[str, Any], test_input: Dict[str, Any]) -> Dict[str, Any]:
        resolved = self._resolve_http_request(tool, test_input)
        if resolved["executionMode"] == "plugin_gateway":
            result = await self._test_http_via_plugin_gateway(tool, resolved)
            result["debug"] = self._build_debug_trace(resolved, tool)
            return result
        result = await self._test_http_direct(resolved)
        result["debug"] = self._build_debug_trace(resolved, tool)
        return result

    def _build_http_runtime_input(self, tool: Dict[str, Any], arguments: Dict[str, Any]) -> Dict[str, Any]:
        config = _safe_dict(tool.get("config"))
        query: Dict[str, Any] = {}
        body: Dict[str, Any] = {}
        headers: Dict[str, Any] = {}
        path: Dict[str, Any] = {}
        schema = self._flatten_schema(_safe_list(config.get("inputSchema")))
        if not schema:
            return {"query": dict(arguments or {}), "body": {}, "headers": {}, "path": {}}
        for node in schema:
            name = str(node.get("name") or "").strip()
            if not name or name not in arguments:
                continue
            location = str(node.get("location") or "Query").strip().lower()
            value = arguments.get(name)
            if location == "path":
                path[name] = value
            elif location == "header":
                headers[name] = value
            elif location == "body":
                body[name] = value
            else:
                query[name] = value
        return {"query": query, "body": body, "headers": headers, "path": path}

    async def _test_http_direct(self, resolved: Dict[str, Any]) -> Dict[str, Any]:
        method = str(resolved.get("method") or "GET").strip().upper()
        url = str(resolved.get("url") or "").strip()
        if not url:
            raise ValueError("HTTP URL 不能为空")
        timeout = float(resolved.get("timeoutSeconds") or 15)
        headers = _safe_dict(resolved.get("headers"))
        query = _safe_dict(resolved.get("query"))
        body = resolved.get("body")
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.request(method, url, params=query or None, json=body if body not in ("", None) else None, headers=headers)
        content_type = response.headers.get("content-type", "")
        try:
            parsed_body: Any = response.json() if "json" in content_type else response.text
        except Exception:
            parsed_body = response.text
        ok = 200 <= response.status_code < 300
        return {
            "success": ok,
            "status": "passed" if ok else "failed",
            "message": f"HTTP {response.status_code}",
            "statusCode": response.status_code,
            "responseSummary": _short_text(parsed_body),
            "raw": parsed_body,
        }

    async def _test_http_via_plugin_gateway(self, tool: Dict[str, Any], resolved: Dict[str, Any]) -> Dict[str, Any]:
        config = _safe_dict(tool.get("config"))
        gateway_url = self._resolve_gateway_url(config)
        plugin_id = self._resolve_plugin_id(config, resolved)
        if not gateway_url:
            raise ValueError("plugin_gateway 模式缺少 gatewayUrl（且未能从 url/endpoint 自动推断）")
        if not plugin_id:
            raise ValueError("plugin_gateway 模式缺少 pluginId（可在 config.pluginId / config.plugin_id / 测试输入 pluginId 提供）")
        request_path = self._resolve_gateway_path(config, resolved)
        timeout = float(resolved.get("timeoutSeconds") or 15)
        request_params = self._build_gateway_params(config, resolved.get("resolvedParams", {}))
        payload = {
            "pluginId": plugin_id,
            "path": request_path,
            "method": str(resolved.get("method") or "GET").upper(),
            "uuid": uuid.uuid4().hex,
            "request": {"params": request_params},
        }
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.post(gateway_url, json=payload, headers=resolved.get("headers") or None)
        content_type = response.headers.get("content-type", "")
        try:
            parsed_body: Any = response.json() if "json" in content_type else response.text
        except Exception:
            parsed_body = response.text
        wrapped = parsed_body.get("response") if isinstance(parsed_body, dict) and isinstance(parsed_body.get("response"), dict) else parsed_body
        ok = bool(wrapped.get("success")) if isinstance(wrapped, dict) and "success" in wrapped else 200 <= response.status_code < 300
        return {
            "success": ok,
            "status": "passed" if ok else "failed",
            "message": f"HTTP {response.status_code}",
            "statusCode": response.status_code,
            "responseSummary": _short_text(wrapped),
            "raw": wrapped,
            "gatewayRequest": payload,
        }

    def _resolve_gateway_url(self, config: Dict[str, Any]) -> str:
        explicit = str(config.get("gatewayUrl") or "").strip()
        if explicit:
            return explicit
        # Systematic fallback: reuse existing endpoint-like config when users
        # migrate from older plugin debugger config and only filled URL.
        return str(config.get("endpoint") or config.get("url") or "").strip()

    def _resolve_gateway_path(self, config: Dict[str, Any], resolved: Dict[str, Any]) -> str:
        template = str(config.get("gatewayPath") or config.get("path") or "").strip()
        if template:
            path_params = _safe_dict(resolved.get("path"))
            for key, value in path_params.items():
                template = template.replace("{" + str(key) + "}", str(value))
            template = template.lstrip("/")
            return template
        parsed_url = urlparse(str(resolved.get("url") or ""))
        return parsed_url.path.lstrip("/") + ((f"?{parsed_url.query}") if parsed_url.query else "")

    def _resolve_plugin_id(self, config: Dict[str, Any], resolved: Dict[str, Any]) -> str:
        for value in (
            config.get("pluginId"),
            config.get("plugin_id"),
            config.get("pluginID"),
            resolved.get("pluginId"),
            resolved.get("plugin_id"),
        ):
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def _resolve_http_request(self, tool: Dict[str, Any], test_input: Dict[str, Any]) -> Dict[str, Any]:
        config = _safe_dict(tool.get("config"))
        url = str(config.get("url") or "").strip()
        if not url:
            raise ValueError("HTTP URL 不能为空")
        method = str(config.get("method") or "GET").strip().upper()
        execution_mode = str(config.get("executionMode") or "").strip().lower()
        if not execution_mode:
            execution_mode = "direct_http"
        normalized = self._normalize_test_input(test_input)
        headers = {str(k): str(v) for k, v in _safe_dict(config.get("headers")).items() if str(k).strip()}
        headers.update({str(k): str(v) for k, v in _safe_dict(normalized.get("headers")).items() if str(k).strip()})
        auth_type = str(config.get("authType") or "none").strip()
        token = str(config.get("authToken") or "").strip()
        if auth_type == "bearer" and token:
            headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "api_key" and token:
            key_name = str(config.get("apiKeyHeader") or "X-API-Key").strip() or "X-API-Key"
            headers[key_name] = token
        timeout = float(config.get("timeoutSeconds") or 15)
        query = _safe_dict(normalized.get("query"))
        path_params = _safe_dict(normalized.get("path"))
        used_path_keys = set()
        for key, value in path_params.items():
            token = "{" + str(key) + "}"
            if token in url:
                used_path_keys.add(str(key))
                url = url.replace(token, str(value))
        unused_path_keys = [key for key in path_params.keys() if str(key) not in used_path_keys]
        ignored_path_keys: List[str] = []
        if unused_path_keys:
            # If URL has no path-template placeholders, auto-append path params by
            # schema order (or key order fallback). This keeps tool-driven behavior
            # and avoids forcing users to hand-write URL templates.
            if "{" not in url and "}" not in url and url.endswith("/"):
                ordered_path_keys = self._ordered_path_keys_from_schema(config, path_params)
                base = url.rstrip("/")
                suffix = "/".join(quote(str(path_params[key]), safe="") for key in ordered_path_keys if key in path_params)
                if suffix:
                    url = f"{base}/{suffix}"
                    used_path_keys.update(ordered_path_keys)
                    unused_path_keys = [key for key in path_params.keys() if str(key) not in used_path_keys]
            # If URL is already a full fixed path (not ending with "/"), allow
            # direct request and ignore leftover Path params instead of hard-failing.
            elif "{" not in url and "}" not in url and not url.endswith("/"):
                ignored_path_keys = [str(k) for k in unused_path_keys]
                unused_path_keys = []
            if unused_path_keys:
                raise ValueError(f"Path 参数未被 URL 使用：{', '.join([str(k) for k in unused_path_keys])}。请在请求地址中使用 {{参数名}} 占位符")
        unresolved = re.findall(r"\{([^{}]+)\}", url)
        if unresolved:
            raise ValueError(f"缺少 Path 参数：{', '.join(unresolved)}")
        body = normalized.get("body")
        logger.info(
            "external_tool_http_resolved name=%s execution_mode=%s method=%s original_url=%s resolved_url=%s path_params=%s query=%s",
            tool.get("name"),
            execution_mode,
            method,
            str(config.get("url") or "").strip(),
            url,
            _short_text(path_params, 2000),
            _short_text(query, 2000),
        )
        return {
            "executionMode": execution_mode,
            "method": method,
            "url": url,
            "headers": headers,
            "query": query,
            "path": path_params,
            "body": body,
            "timeoutSeconds": timeout,
            "resolvedParams": normalized.get("resolvedParams", {}),
            "pluginId": str(test_input.get("pluginId") or test_input.get("plugin_id") or "").strip(),
            "ignoredPathParams": ignored_path_keys,
        }

    def _ordered_path_keys_from_schema(self, config: Dict[str, Any], path_params: Dict[str, Any]) -> List[str]:
        schema = _safe_list(config.get("inputSchema"))
        ordered: List[str] = []
        for node in self._flatten_schema(schema):
            if not isinstance(node, dict):
                continue
            if str(node.get("location") or "").strip() != "Path":
                continue
            name = str(node.get("name") or "").strip()
            if name and name in path_params and name not in ordered:
                ordered.append(name)
        for key in path_params.keys():
            text_key = str(key)
            if text_key not in ordered:
                ordered.append(text_key)
        return ordered

    def _normalize_test_input(self, test_input: Dict[str, Any]) -> Dict[str, Any]:
        # Backward compatibility: old plugin debugger payload contains request.params array.
        if isinstance(test_input.get("request"), dict) and isinstance(test_input.get("request", {}).get("params"), list):
            query: Dict[str, Any] = {}
            body: Dict[str, Any] = {}
            headers: Dict[str, Any] = {}
            path: Dict[str, Any] = {}
            resolved_params: Dict[str, Dict[str, Any]] = {}
            for item in _safe_list(test_input.get("request", {}).get("params")):
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                location = str(item.get("location") or "Query").strip().lower()
                value = item.get("value")
                resolved_params[name] = item
                if location == "path":
                    path[name] = value
                elif location == "header":
                    headers[name] = value
                elif location == "body":
                    body[name] = value
                else:
                    query[name] = value
            return {"query": query, "body": body, "headers": headers, "path": path, "resolvedParams": resolved_params}
        query = _safe_dict(test_input.get("query"))
        body = _safe_dict(test_input.get("body"))
        headers = _safe_dict(test_input.get("headers"))
        path = _safe_dict(test_input.get("path"))
        resolved_params: Dict[str, Dict[str, Any]] = {}
        for name, value in path.items():
            resolved_params[str(name)] = {"name": str(name), "location": "Path", "value": value}
        for name, value in query.items():
            resolved_params[str(name)] = {"name": str(name), "location": "Query", "value": value}
        for name, value in headers.items():
            resolved_params[str(name)] = {"name": str(name), "location": "Header", "value": value}
        for name, value in body.items():
            resolved_params[str(name)] = {"name": str(name), "location": "Body", "value": value}
        return {
            "query": query,
            "body": body,
            "headers": headers,
            "path": path,
            "resolvedParams": resolved_params,
        }

    def _build_gateway_params(self, config: Dict[str, Any], resolved_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        schema = _safe_list(config.get("inputSchema"))
        if not schema:
            params: List[Dict[str, Any]] = []
            for name, value in resolved_params.items():
                if isinstance(value, dict):
                    params.append(value)
            return params
        flat = self._flatten_schema(schema)
        params = []
        for node in flat:
            name = str(node.get("name") or "").strip()
            if not name:
                continue
            fallback = resolved_params.get(name) if isinstance(resolved_params, dict) else None
            value = node.get("value")
            if isinstance(fallback, dict) and "value" in fallback:
                value = fallback.get("value")
            params.append(
                {
                    "_id": str(node.get("id") or node.get("_id") or uuid.uuid4().hex),
                    "children": _safe_list(node.get("children")),
                    "desc": str(node.get("description") or node.get("desc") or ""),
                    "location": str(node.get("location") or "Query"),
                    "name": name,
                    "require": bool(node.get("required", node.get("require", False))),
                    "type": str(node.get("type") or "String"),
                    "value": value,
                }
            )
        return params

    def _flatten_schema(self, nodes: List[Any]) -> List[Dict[str, Any]]:
        flat: List[Dict[str, Any]] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            flat.append(node)
            flat.extend(self._flatten_schema(_safe_list(node.get("children"))))
        return flat

    def _build_debug_trace(self, resolved: Dict[str, Any], tool: Dict[str, Any]) -> Dict[str, Any]:
        config = _safe_dict(tool.get("config"))
        resolved_gateway_url = self._resolve_gateway_url(config)
        resolved_gateway_path = self._resolve_gateway_path(config, resolved)
        return {
            "executionMode": resolved.get("executionMode"),
            "method": resolved.get("method"),
            "resolvedUrl": resolved.get("url"),
            "pathParams": _safe_dict(resolved.get("path")),
            "ignoredPathParams": _safe_list(resolved.get("ignoredPathParams")),
            "queryParams": _safe_dict(resolved.get("query")),
            "headerKeys": sorted([str(k) for k in _safe_dict(resolved.get("headers")).keys()]),
            "hasBody": resolved.get("body") not in (None, "", {}),
            "pluginId": str(config.get("pluginId") or ""),
            "resolvedPluginId": self._resolve_plugin_id(config, resolved),
            "gatewayUrl": str(config.get("gatewayUrl") or ""),
            "gatewayPath": str(config.get("gatewayPath") or ""),
            "resolvedGatewayUrl": resolved_gateway_url,
            "resolvedGatewayPath": resolved_gateway_path,
        }

    async def _test_mcp(self, tool: Dict[str, Any], test_input: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = str(test_input.get("toolName") or "").strip()
        if not tool_name:
            discovered = await self._mcp_jsonrpc(tool, "tools/list", {})
            tools = _safe_list(discovered.get("tools") if isinstance(discovered, dict) else [])
            return {
                "success": True,
                "status": "passed",
                "message": f"MCP 连接成功，发现 {len(tools)} 个 tools",
                "responseSummary": _short_text(discovered),
                "raw": discovered,
            }
        result = await self._mcp_jsonrpc(tool, "tools/call", {"name": tool_name, "arguments": _safe_dict(test_input.get("arguments"))})
        return {
            "success": True,
            "status": "passed",
            "message": f"MCP tool {tool_name} 调用成功",
            "responseSummary": _short_text(result),
            "raw": result,
        }

    async def _mcp_jsonrpc(
        self,
        tool: Dict[str, Any],
        method: str,
        params: Dict[str, Any],
        runtime_headers: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        config = _safe_dict(tool.get("config"))
        endpoint = str(config.get("endpoint") or config.get("url") or "").strip()
        if not endpoint:
            raise ValueError("MCP 服务地址不能为空")
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        headers.update({str(k): str(v) for k, v in _safe_dict(config.get("headers")).items() if str(k).strip()})
        auth_type = str(config.get("authType") or "none").strip()
        token = str(config.get("authToken") or "").strip()
        if auth_type == "bearer" and token:
            headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "api_key" and token:
            key_name = str(config.get("apiKeyHeader") or "X-API-Key").strip() or "X-API-Key"
            headers[key_name] = token
        # Runtime identity is trusted platform context, not an LLM-editable tool
        # argument. Apply it last so configured headers cannot spoof the actor.
        headers.update(
            {
                str(key): str(value)
                for key, value in dict(runtime_headers or {}).items()
                if str(key).strip() and str(value).strip()
            }
        )
        payload = {"jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": method, "params": params}
        timeout = float(config.get("timeoutSeconds") or 20)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _short_text(response.text, 1000)
            raise ValueError(f"MCP 服务返回 HTTP {response.status_code}: {detail}") from exc
        data = self._parse_mcp_response(response.text)
        if isinstance(data, dict) and data.get("error"):
            raise ValueError(_short_text(data.get("error"), 1000))
        result = data.get("result") if isinstance(data, dict) else data
        return result if isinstance(result, dict) else {"result": result}

    @staticmethod
    def _parse_mcp_response(text: str) -> Any:
        stripped = str(text or "").strip()
        if not stripped:
            return {}
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as direct_error:
            events: List[str] = []
            current: List[str] = []
            for raw_line in stripped.splitlines():
                line = raw_line.strip()
                if not line:
                    if current:
                        events.append("\n".join(current))
                        current = []
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    candidate = line.replace("data:", "", 1).strip()
                    if candidate and candidate != "[DONE]":
                        current.append(candidate)
            if current:
                events.append("\n".join(current))

            for candidate in events:
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue

            preview = _short_text(stripped, 500)
            raise ValueError(f"MCP 服务返回非 JSON 响应：{preview}") from direct_error


external_tool_service = ExternalToolService()


class ExternalToolRegistry:
    async def list_enabled_descriptors(self, main_id: str = "default", *, user_id: str = "") -> List[Dict[str, Any]]:
        tools = await external_tool_service.list_visible(main_id, user_id=user_id, enabled_only=True)
        descriptors: List[Dict[str, Any]] = []
        for tool in tools:
            config = _safe_dict(tool.get("config"))
            if tool["type"] == "mcp":
                enabled = enabled_mcp_tool_names(config)
                if not enabled or len(enabled) > MCP_ENABLED_TOOL_LIMIT:
                    logger.warning(
                        "external_tool_registry_skip_mcp main_id=%s tool_id=%s enabled_tool_count=%s",
                        main_id,
                        tool.get("id"),
                        len(enabled),
                    )
                    continue
                enabled_set = set(enabled)
                discovered_tools = [
                    item for item in _safe_list(tool.get("discoveredTools"))
                    if isinstance(item, dict) and str(item.get("name") or "").strip() in enabled_set
                ]
            else:
                discovered_tools = []
            descriptors.append(
                {
                    "id": tool["id"],
                    "name": tool["name"],
                    "type": tool["type"],
                    "description": tool["description"],
                    "usageHint": tool["usageHint"],
                    "tags": tool["tags"],
                    "config": config,
                    "inputSchema": _safe_list(config.get("inputSchema")),
                    "outputSchema": _safe_list(config.get("outputSchema")),
                    "resultPath": str(config.get("resultPath") or ""),
                    "discoveredTools": discovered_tools,
                }
            )
        return descriptors


external_tool_registry = ExternalToolRegistry()
