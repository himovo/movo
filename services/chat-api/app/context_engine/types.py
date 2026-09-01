from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class ContextBlockType(str, Enum):
    CURRENT_REQUEST = "current_request"
    RECENT_MESSAGES = "recent_messages"
    CONVERSATION_SUMMARY = "conversation_summary"
    ACTIVE_DOCUMENT = "active_document"
    RETRIEVED_HISTORY = "retrieved_history"
    PROJECT_MEMORY = "project_memory"
    CODING_CONTEXT = "coding_context"


@dataclass
class ContextBlock:
    block_type: ContextBlockType
    title: str
    content: str
    priority: int
    token_budget: int
    role: str = "system"
    required: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RenderedBlock:
    block: ContextBlock
    content: str
    estimated_tokens: int
    included: bool
    reason: str = ""


@dataclass
class ContextBuildResult:
    messages: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)
    blocks: List[RenderedBlock] = field(default_factory=list)
