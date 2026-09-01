"""Browser automation integration.

Responsibilities
----------------
- ``registry``     : in-process map of connected local-agent WebSockets.
- ``ws_endpoint``  : FastAPI WS endpoint for agent connections.
- ``local_bridge`` : proxies v2 tool calls to the connected agent.
- ``tools``        : tool-name constants shared with the agent side.
"""

from .registry import agent_registry
from .local_bridge import LocalBridge

__all__ = ["agent_registry", "LocalBridge"]
