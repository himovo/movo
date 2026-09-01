from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FixtureToolExecutor:
    fixtures: dict[str, Any]
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def execute(self, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        arguments = dict(arguments or {})
        self.calls.append({"name": tool_name, "arguments": arguments})
        if tool_name not in self.fixtures:
            raise KeyError(f"no fixture configured for tool {tool_name!r}")
        fixture = self.fixtures[tool_name]
        if isinstance(fixture, dict) and fixture.get("raise"):
            raise RuntimeError(str(fixture["raise"]))
        return deepcopy(fixture)
