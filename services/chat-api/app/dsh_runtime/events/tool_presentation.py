"""Secret-free Tool Profile metadata used by ASKAI's execution Timeline."""

from __future__ import annotations

from typing import Any

from app.dsh_runtime.profile.models import RuntimeProfileSnapshot


def tool_presentations(profile: RuntimeProfileSnapshot) -> dict[str, dict[str, Any]]:
    return {
        tool.name: {
            "display_name": tool.display_name or tool.mcp_tool_name or tool.name,
            "description": tool.description,
            "risk_level": tool.risk_level,
            "delivery_mode": tool.delivery_mode,
        }
        for tool in profile.tools
    }
