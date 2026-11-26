from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, Iterable, List

import httpx

from app.services.http_proxy_policy import should_trust_environment_proxy


MCP_PROTOCOL_VERSION = "2025-06-18"
_LEGACY_INITIALIZE_HTTP_STATUSES = {400, 404, 405}


class McpTransportError(ValueError):
    """A Streamable HTTP or JSON-RPC protocol failure."""


class StreamableHttpMcpClient:
    """Execute one MCP operation inside a correctly initialized HTTP session."""

    def __init__(
        self,
        *,
        endpoint: str,
        headers: Dict[str, str] | None = None,
        timeout: float = 20,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._endpoint = str(endpoint or "").strip()
        self._headers = _coalesce_headers(headers or {})
        self._timeout = timeout
        self._transport = transport

    async def call(self, method: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if not self._endpoint:
            raise McpTransportError("MCP 服务地址不能为空")

        async with httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            transport=self._transport,
            trust_env=should_trust_environment_proxy(self._endpoint),
        ) as client:
            if method == "tools/list":
                try:
                    return await asyncio.wait_for(
                        self._list_tools(client, params or {}), timeout=self._timeout
                    )
                except asyncio.TimeoutError as exc:
                    raise McpTransportError("MCP tool discovery timed out") from exc

            headers = await self._session_headers(client)
            return await self._request(client, method, params or {}, headers)

    async def _session_headers(self, client: httpx.AsyncClient) -> Dict[str, str]:
        initialized = await self._initialize(client)
        headers = self._base_headers()
        if initialized is not None:
            session_id, protocol_version = initialized
            headers["MCP-Protocol-Version"] = protocol_version
            if session_id:
                headers["Mcp-Session-Id"] = session_id
            await self._notify_initialized(client, headers)
        return headers

    async def _list_tools(
        self, client: httpx.AsyncClient, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        headers = await self._session_headers(client)
        page = await self._request(client, "tools/list", params, headers)
        tools = []
        seen_cursors = set()
        while True:
            page_tools = page.get("tools")
            if not isinstance(page_tools, list):
                raise McpTransportError("MCP tools/list response is missing a tools array")
            tools.extend(page_tools)

            cursor = page.pop("nextCursor", None)
            if cursor is None:
                return {**page, "tools": tools}
            if not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
                raise McpTransportError("MCP tools/list returned an invalid or repeated cursor")
            seen_cursors.add(cursor)
            page = await self._request(client, "tools/list", {**params, "cursor": cursor}, headers)

    async def _initialize(self, client: httpx.AsyncClient) -> tuple[str, str] | None:
        request_id = uuid.uuid4().hex
        headers = self._base_headers()
        headers["MCP-Protocol-Version"] = MCP_PROTOCOL_VERSION
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "MOVO", "version": "0.1.0"},
            },
        }
        response = await client.post(self._endpoint, json=payload, headers=headers)
        if response.status_code in _LEGACY_INITIALIZE_HTTP_STATUSES:
            return None
        self._raise_for_http_error(response)

        message = parse_mcp_response(response.text, request_id=request_id)
        error = message.get("error") if isinstance(message, dict) else None
        if isinstance(error, dict) and error.get("code") == -32601:
            return None
        if error:
            raise McpTransportError(_short_text(error, 1000))

        result = message.get("result") if isinstance(message, dict) else None
        if not isinstance(result, dict):
            raise McpTransportError("MCP initialize 响应缺少 result")
        negotiated_version = str(result.get("protocolVersion") or MCP_PROTOCOL_VERSION).strip()
        return response.headers.get("Mcp-Session-Id", "").strip(), negotiated_version

    async def _notify_initialized(self, client: httpx.AsyncClient, headers: Dict[str, str]) -> None:
        response = await client.post(
            self._endpoint,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=headers,
        )
        self._raise_for_http_error(response)

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        params: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        request_id = uuid.uuid4().hex
        response = await client.post(
            self._endpoint,
            json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            headers=headers,
        )
        self._raise_for_http_error(response)
        message = parse_mcp_response(response.text, request_id=request_id)
        if isinstance(message, dict) and message.get("error"):
            raise McpTransportError(_short_text(message.get("error"), 1000))
        result = message.get("result") if isinstance(message, dict) else message
        return result if isinstance(result, dict) else {"result": result}

    def _base_headers(self) -> Dict[str, str]:
        reserved = {"accept", "content-type", "mcp-protocol-version", "mcp-session-id"}
        headers = {key: value for key, value in self._headers.items() if key.lower() not in reserved}
        headers["Accept"] = "application/json, text/event-stream"
        headers["Content-Type"] = "application/json"
        return headers

    @staticmethod
    def _raise_for_http_error(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _short_text(response.text, 1000)
            raise McpTransportError(f"MCP 服务返回 HTTP {response.status_code}: {detail}") from exc


def parse_mcp_response(text: str, *, request_id: str | None = None) -> Dict[str, Any]:
    stripped = str(text or "").strip()
    if not stripped:
        raise McpTransportError("MCP 服务返回空响应")

    messages = list(_decode_messages(stripped))
    if request_id is not None:
        for message in messages:
            if message.get("id") == request_id:
                return message
    if len(messages) == 1 and ("result" in messages[0] or "error" in messages[0]):
        return messages[0]

    preview = _short_text(stripped, 500)
    raise McpTransportError(f"MCP 响应中缺少当前请求的 JSON-RPC 结果：{preview}")


def _decode_messages(text: str) -> Iterable[Dict[str, Any]]:
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as direct_error:
        events = _decode_sse_data(text)
        if not events:
            preview = _short_text(text, 500)
            raise McpTransportError(f"MCP 服务返回非 JSON 响应：{preview}") from direct_error
        for event in events:
            try:
                decoded_event = json.loads(event)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded_event, dict):
                yield decoded_event
        return

    if isinstance(decoded, dict):
        yield decoded
    elif isinstance(decoded, list):
        for item in decoded:
            if isinstance(item, dict):
                yield item


def _decode_sse_data(text: str) -> List[str]:
    events: List[str] = []
    current: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            if current:
                events.append("\n".join(current))
                current = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            value = line[5:].lstrip()
            if value and value != "[DONE]":
                current.append(value)
    if current:
        events.append("\n".join(current))
    return events


def _short_text(value: Any, limit: int) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


def _coalesce_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Keep the last value for each case-insensitive HTTP header name."""
    normalized: Dict[str, tuple[str, str]] = {}
    for key, value in headers.items():
        text_key = str(key)
        normalized[text_key.lower()] = (text_key, str(value))
    return {key: value for key, value in normalized.values()}
