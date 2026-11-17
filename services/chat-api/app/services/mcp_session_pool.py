"""Bounded, actor-scoped MCP sessions; protocol handling remains in the client."""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from time import monotonic
from weakref import WeakKeyDictionary

import httpx

from .http_proxy_policy import should_trust_environment_proxy
from .mcp_streamable_http import StreamableHttpMcpClient, McpTransportError


@dataclass
class Session:
    client: httpx.AsyncClient
    protocol: StreamableHttpMcpClient
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    headers: dict | None = None
    initialized: bool = False
    active: int = 0
    touched: float = field(default_factory=monotonic)
    invalid: bool = False


class McpSessionPool:
    def __init__(self, limit=64, idle_seconds=300, transport=None):
        self.limit = limit
        self.idle_seconds = idle_seconds
        self.transport = transport
        self._sessions = {}
        self._lock = asyncio.Lock()

    async def call(self, *, endpoint, headers, timeout, actor, method, params):
        if not actor:
            raise ValueError('MCP session reuse requires a trusted actor')
        key = hashlib.sha256(json.dumps([actor, endpoint, headers, timeout], sort_keys=True).encode()).hexdigest()
        async with self._lock:
            stale = [k for k, v in self._sessions.items() if not v.active
                     and (v.invalid or monotonic() - v.touched >= self.idle_seconds)]
            for old in stale:
                await self._sessions.pop(old).client.aclose()
            entry = self._sessions.get(key)
            if entry is None:
                if len(self._sessions) >= self.limit:
                    idle = [(v.touched, k) for k, v in self._sessions.items() if not v.active]
                    if idle:
                        await self._sessions.pop(min(idle)[1]).client.aclose()
                    else:
                        # One-shot fallback preserves availability without growing the pool.
                        entry = None
                if len(self._sessions) < self.limit:
                    entry = Session(
                        httpx.AsyncClient(timeout=timeout, follow_redirects=True, transport=self.transport,
                                          trust_env=should_trust_environment_proxy(endpoint)),
                        StreamableHttpMcpClient(endpoint=endpoint, headers=headers, timeout=timeout),
                    )
                    self._sessions[key] = entry
            if entry is not None:
                entry.active += 1
        if entry is None:
            return await StreamableHttpMcpClient(endpoint=endpoint, headers=headers, timeout=timeout,
                                                 transport=self.transport).call(method, params)
        try:
            async with entry.lock:
                if entry.invalid:
                    raise McpTransportError('MCP session expired; retry with a new session')
                if not entry.initialized:
                    initialized = await entry.protocol._initialize(entry.client)
                    entry.headers = entry.protocol._base_headers()
                    if initialized:
                        session_id, version = initialized
                        entry.headers['MCP-Protocol-Version'] = version
                        if session_id:
                            entry.headers['Mcp-Session-Id'] = session_id
                        await entry.protocol._notify_initialized(entry.client, entry.headers)
                    entry.initialized = True
            return await entry.protocol._request(entry.client, method, params or {}, entry.headers)
        except BaseException:
            # Never replay tools/call: a network error can occur after a write committed.
            entry.invalid = True
            raise
        finally:
            async with self._lock:
                entry.active -= 1
                entry.touched = monotonic()
                if entry.invalid and not entry.active and self._sessions.get(key) is entry:
                    self._sessions.pop(key)
                    await entry.client.aclose()

    async def close(self):
        async with self._lock:
            entries = list(self._sessions.values())
            self._sessions.clear()
        await asyncio.gather(*(entry.client.aclose() for entry in entries))


_POOLS = WeakKeyDictionary()


def current_mcp_pool():
    loop = asyncio.get_running_loop()
    pool = _POOLS.get(loop)
    if pool is None:
        pool = McpSessionPool()
        _POOLS[loop] = pool
    return pool


async def close_mcp_pool():
    pool = _POOLS.pop(asyncio.get_running_loop(), None)
    if pool:
        await pool.close()
