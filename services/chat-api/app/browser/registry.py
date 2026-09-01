"""Per-user WebSocket registry for connected local agents.

Each logged-in user may have at most one active agent connection. Sending
a tool call allocates a future and rendezvous on ``call_id`` with the
agent's reply. Pings keep the socket alive; stale connections are culled
by heartbeat timeout.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Optional


logger = logging.getLogger(__name__)


class AgentToolTimeout(asyncio.TimeoutError):
    def __init__(self, tool: str, session_id: str, timeout: float) -> None:
        super().__init__(
            f"local agent tool timed out: tool={tool} session={session_id} timeout={timeout:.1f}s"
        )


@dataclass
class PendingCall:
    call_id: str
    future: "asyncio.Future[Dict[str, Any]]"
    progress_sink: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]] = None
    created_at: float = field(default_factory=time.time)


@dataclass
class AgentConnection:
    user_id: str
    send: Callable[[Dict[str, Any]], Awaitable[None]]
    capabilities: list[str] = field(default_factory=list)
    pending: Dict[str, PendingCall] = field(default_factory=dict)
    connected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


class AgentRegistry:
    """In-process singleton. Replace with Redis pub/sub for multi-worker."""

    def __init__(self) -> None:
        self._by_user: Dict[str, AgentConnection] = {}
        self._lock = asyncio.Lock()
        # Recording event listeners. Separate from screencast so the
        # two subscriptions don't interfere when both are active.
        self._recording_listeners: Dict[str, list["asyncio.Queue[Dict[str, Any] | None]"]] = {}
        self._active_recordings: Dict[tuple[str, str], str] = {}

    async def attach(
        self,
        user_id: str,
        send: Callable[[Dict[str, Any]], Awaitable[None]],
        capabilities: list[str],
    ) -> AgentConnection:
        async with self._lock:
            existing = self._by_user.get(user_id)
            if existing is not None:
                # Cancel any in-flight calls so old awaiters wake up.
                for pc in list(existing.pending.values()):
                    if not pc.future.done():
                        pc.future.set_exception(ConnectionError("agent reconnected"))
            conn = AgentConnection(user_id=user_id, send=send, capabilities=list(capabilities))
            self._by_user[user_id] = conn
            return conn

    async def detach(self, user_id: str, connection: AgentConnection | None = None) -> None:
        async with self._lock:
            current = self._by_user.get(user_id)
            if current is None or (connection is not None and current is not connection):
                return
            conn = self._by_user.pop(user_id)
            for key in [item for item in self._active_recordings if item[0] == user_id]:
                self._active_recordings.pop(key, None)
            if conn is None:
                return
            for pc in list(conn.pending.values()):
                if not pc.future.done():
                    pc.future.set_exception(ConnectionError("agent disconnected"))

    def get(self, user_id: str) -> Optional[AgentConnection]:
        return self._by_user.get(user_id)

    # -- call dispatch -----------------------------------------------------
    async def send_tool_call(
        self,
        user_id: str,
        tool: str,
        args: Dict[str, Any],
        *,
        session_id: str = "default",
        domain: Optional[str] = None,
        timeout: float = 60.0,
        progress_sink: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]] = None,
    ) -> Dict[str, Any]:
        conn = self.get(user_id)
        if conn is None:
            raise ConnectionError("agent not connected")
        call_id = uuid.uuid4().hex
        pc = PendingCall(call_id=call_id, future=asyncio.get_event_loop().create_future(),
                         progress_sink=progress_sink)
        conn.pending[call_id] = pc
        try:
            local_timeout_ms = max(1_000, int(timeout * 1_000) - 5_000)
            await conn.send({
                "type": "tool_call",
                "payload": {
                    "call_id": call_id,
                    "tool": tool,
                    "args": args,
                    "user_id": user_id,
                    "session_id": session_id or "default",
                    "domain": domain,
                    "timeout_ms": local_timeout_ms,
                },
            })
            try:
                return await asyncio.wait_for(pc.future, timeout=timeout)
            except asyncio.TimeoutError as exc:
                logger.warning(
                    "local agent tool timed out",
                    extra={
                        "event": "browser.local_tool_timeout",
                        "tool": tool,
                        "call_id": call_id,
                        "browser_session_id": session_id or "default",
                        "timeout_seconds": timeout,
                    },
                )
                try:
                    await conn.send({
                        "type": "tool_cancel",
                        "payload": {
                            "call_id": call_id,
                            "session_id": session_id or "default",
                            "reason": "backend_timeout",
                        },
                    })
                except Exception:
                    logger.warning(
                        "failed to cancel timed out local agent tool",
                        exc_info=True,
                        extra={
                            "event": "browser.local_tool_cancel_failed",
                            "tool": tool,
                            "call_id": call_id,
                        },
                    )
                raise AgentToolTimeout(tool, session_id or "default", timeout) from exc
        finally:
            conn.pending.pop(call_id, None)

    async def send_login_request(
        self,
        user_id: str,
        domain: str,
        login_url: str,
        *,
        session_id: str = "default",
        timeout: float = 360.0,
    ) -> Dict[str, Any]:
        conn = self.get(user_id)
        if conn is None:
            raise ConnectionError("agent not connected")
        request_id = uuid.uuid4().hex
        pc = PendingCall(call_id=request_id, future=asyncio.get_event_loop().create_future())
        conn.pending[request_id] = pc
        try:
            await conn.send({
                "type": "login_request",
                "payload": {
                    "request_id": request_id,
                    "user_id": user_id,
                    "session_id": session_id or "default",
                    "domain": domain,
                    "login_url": login_url,
                },
            })
            return await asyncio.wait_for(pc.future, timeout=timeout)
        finally:
            conn.pending.pop(request_id, None)

    # -- inbound frame handling ------------------------------------------
    async def on_frame(self, user_id: str, frame: Dict[str, Any]) -> None:
        conn = self.get(user_id)
        if conn is None:
            return
        conn.last_seen = time.time()
        t = str(frame.get("type") or "")
        payload = frame.get("payload") or {}
        if t == "tool_result":
            cid = payload.get("call_id")
            pc = conn.pending.get(cid or "")
            if pc and not pc.future.done():
                pc.future.set_result(payload)
        elif t == "tool_progress":
            cid = payload.get("call_id")
            pc = conn.pending.get(cid or "")
            if pc and pc.progress_sink is not None:
                res = pc.progress_sink(payload)
                if asyncio.iscoroutine(res):
                    await res
        elif t == "login_result":
            rid = payload.get("request_id")
            pc = conn.pending.get(rid or "")
            if pc and not pc.future.done():
                pc.future.set_result(payload)
        elif t == "recording_event":
            from app.enterprise_capabilities.browser.engine.recording import human_recording_store

            if isinstance(payload, dict):
                payload = {**payload, "user_id": user_id}
                await human_recording_store.append(payload)
                event_type = str(payload.get("type") or "")
                recording_id = str(payload.get("recording_id") or "")
                recording_key = (user_id, str(payload.get("session_id") or "default"))
                if event_type == "recording_started" and recording_id:
                    self._active_recordings[recording_key] = recording_id
                elif event_type == "recording_stopped" and self._active_recordings.get(recording_key) == recording_id:
                    self._active_recordings.pop(recording_key, None)
            for q in self._recording_listeners.get(user_id, []):
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    pass
        elif t == "hello":
            caps = payload.get("capabilities") or []
            if isinstance(caps, list):
                conn.capabilities = [str(c) for c in caps]
        elif t == "authentication_completed":
            from app.enterprise_capabilities.browser.engine.auth_suspension import browser_auth_suspensions

            await browser_auth_suspensions.mark_ready(
                user_id=user_id,
                run_id=str(payload.get("run_id") or ""),
                node_id=str(payload.get("node_id") or ""),
                browser_session_id=str(payload.get("browser_session_id") or payload.get("session_id") or "default"),
                tab_id=str(payload.get("tab_id") or ""),
                url=str(payload.get("url") or ""),
                source="local_auth_watch",
            )

    # -- recording event subscription -------------------------------------
    def subscribe_recording(self, user_id: str) -> "asyncio.Queue[Dict[str, Any] | None]":
        q: asyncio.Queue[Dict[str, Any] | None] = asyncio.Queue(maxsize=256)
        self._recording_listeners.setdefault(user_id, []).append(q)
        return q

    def unsubscribe_recording(self, user_id: str, q: "asyncio.Queue[Dict[str, Any] | None]") -> None:
        qs = self._recording_listeners.get(user_id, [])
        try:
            qs.remove(q)
        except ValueError:
            pass

    async def send_command(self, user_id: str, command: str, **kwargs: Any) -> bool:
        conn = self.get(user_id)
        if conn is None:
            return False
        recording_key: tuple[str, str] | None = None
        recording_id = ""
        if command == "recording_start":
            recording_id = str(kwargs.get("recording_id") or "")
            recording_key = (user_id, str(kwargs.get("session_id") or "default"))
            active = self._active_recordings.get(recording_key, "")
            if active and active != recording_id:
                return False
            if recording_id:
                self._active_recordings[recording_key] = recording_id
        try:
            await conn.send({"type": "command", "payload": {"command": command, **kwargs}})
        except Exception:
            if recording_key is not None and self._active_recordings.get(recording_key) == recording_id:
                self._active_recordings.pop(recording_key, None)
            raise
        return True


agent_registry = AgentRegistry()
