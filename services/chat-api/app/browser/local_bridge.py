"""LocalBridge — ExecutionEnvironment implementation backed by a connected
local agent. Calls travel as WS frames; progress events (observations,
screenshots) are forwarded to the provided sink.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Callable, Dict, Optional

from .registry import agent_registry


class AgentNotConnected(RuntimeError):
    pass


class LocalBridge:
    """One instance per user session. Stateless apart from the user_id
    binding; all transport state lives in the global registry.
    """

    def __init__(self, user_id: str, session_id: str = "default") -> None:
        self._user_id = user_id
        self._session_id = session_id or "default"

    @property
    def user_id(self) -> str:
        return self._user_id

    def available(self) -> bool:
        return agent_registry.get(self._user_id) is not None

    async def execute(
        self,
        tool: str,
        args: Dict[str, Any],
        *,
        domain: Optional[str] = None,
        timeout: float = 60.0,
        on_progress: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Dict[str, Any]:
        if not self.available():
            raise AgentNotConnected("local agent is not connected")
        return await agent_registry.send_tool_call(
            self._user_id,
            tool,
            args,
            session_id=self._session_id,
            domain=domain,
            timeout=timeout,
            progress_sink=on_progress,
        )

    async def send_command(self, command: str, **kwargs: Any) -> None:
        ok = await agent_registry.send_command(
            self._user_id,
            command,
            session_id=self._session_id,
            **kwargs,
        )
        if command == "recording_start" and not ok:
            raise RuntimeError("another browser recording is already active")

    async def request_login(
        self,
        domain: str,
        login_url: str,
        *,
        timeout: float = 360.0,
    ) -> Dict[str, Any]:
        if not self.available():
            raise AgentNotConnected("local agent is not connected")
        return await agent_registry.send_login_request(
            self._user_id, domain, login_url, session_id=self._session_id, timeout=timeout,
        )
