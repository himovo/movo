from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

class Message(BaseModel):
    role: Role
    content: Any
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None

    @property
    def type(self) -> str:
        return {
            Role.SYSTEM: "system",
            Role.USER: "human",
            Role.ASSISTANT: "ai",
            Role.TOOL: "tool",
        }.get(self.role, str(self.role))

class LLMResponse(BaseModel):
    message: Message
    raw_response: Any = None
    usage: Optional[Dict[str, int]] = None

    @property
    def content(self) -> Any:
        return self.message.content

    @property
    def role(self) -> Role:
        return self.message.role

    @property
    def tool_calls(self) -> Optional[List[Dict[str, Any]]]:
        return self.message.tool_calls
