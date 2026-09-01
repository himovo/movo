from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from app.llm.types import Message, Role

@dataclass
class SkillContext:
    messages: List[Message]
    intent: str
    output_spec: Dict[str, Any] = field(default_factory=dict)
    sop: Optional[Dict[str, Any]] = None
    payload: Dict[str, Any] = field(default_factory=dict)


class BaseSkill:
    name: str = "base"
    description: str = ""

    async def run_stream(self, context: SkillContext) -> AsyncIterator[Dict[str, Any]]:
        raise NotImplementedError
