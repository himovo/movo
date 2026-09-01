from abc import ABC, abstractmethod
import json
from typing import AsyncGenerator, Iterable, List, Type, Any
from pydantic import BaseModel

from app.llm.types import Message, LLMResponse


class _StructuredInvoker:
    def __init__(self, client: "BaseLLMClient", schema: Type[BaseModel]) -> None:
        self._client = client
        self._schema = schema

    async def ainvoke(self, messages: List[Message], **kwargs) -> BaseModel:
        return await self._client.ainvoke_structured(messages, self._schema, **kwargs)


class _ToolBoundClient:
    def __init__(self, client: "BaseLLMClient", tools: Iterable[Any]) -> None:
        self._client = client
        self._tools = [_tool_to_openai_schema(tool) for tool in (tools or [])]

    async def ainvoke(self, messages: List[Message], **kwargs) -> LLMResponse:
        merged = dict(kwargs)
        if self._tools and "tools" not in merged:
            merged["tools"] = self._tools
            merged.setdefault("tool_choice", "auto")
        return await self._client.ainvoke(messages, **merged)

    async def astream(self, messages: List[Message], **kwargs) -> AsyncGenerator[LLMResponse, None]:
        merged = dict(kwargs)
        if self._tools and "tools" not in merged:
            merged["tools"] = self._tools
            merged.setdefault("tool_choice", "auto")
        async for chunk in self._client.astream(messages, **merged):
            yield chunk

    async def ainvoke_structured(
        self,
        messages: List[Message],
        schema: Type[BaseModel],
        **kwargs,
    ) -> BaseModel:
        merged = dict(kwargs)
        if self._tools and "tools" not in merged:
            merged["tools"] = self._tools
            merged.setdefault("tool_choice", "auto")
        return await self._client.ainvoke_structured(messages, schema, **merged)

    def with_structured_output(self, schema: Type[BaseModel], method: str | None = None) -> _StructuredInvoker:
        return _StructuredInvoker(self, schema)

    def bind_tools(self, tools: Iterable[Any]) -> "_ToolBoundClient":
        return _ToolBoundClient(self, tools)


def _tool_to_openai_schema(tool: Any) -> dict[str, Any]:
    name = str(getattr(tool, "name", "") or "")
    description = str(getattr(tool, "description", "") or "")
    args_schema = getattr(tool, "args_schema", None)
    parameters: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": True}
    if args_schema is not None:
        try:
            if hasattr(args_schema, "model_json_schema"):
                parameters = args_schema.model_json_schema()
            elif hasattr(args_schema, "schema"):
                parameters = args_schema.schema()
        except Exception:
            parameters = {"type": "object", "properties": {}, "additionalProperties": True}
    elif isinstance(getattr(tool, "args", None), dict):
        properties = {}
        required = []
        for key, spec in dict(getattr(tool, "args") or {}).items():
            properties[str(key)] = {"type": "string", "description": str((spec or {}).get("description") or "")}
            if (spec or {}).get("required"):
                required.append(str(key))
        parameters = {"type": "object", "properties": properties, "required": required}
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": json.loads(json.dumps(parameters, ensure_ascii=False, default=str)),
        },
    }


class BaseLLMClient(ABC):
    @abstractmethod
    async def ainvoke(self, messages: List[Message], **kwargs) -> LLMResponse:
        """Invoke the language model asynchronously."""
        pass

    @abstractmethod
    async def astream(self, messages: List[Message], **kwargs) -> AsyncGenerator[LLMResponse, None]:
        """Stream the language model response asynchronously."""
        pass

    @abstractmethod
    async def ainvoke_structured(
        self, 
        messages: List[Message], 
        schema: Type[BaseModel], 
        **kwargs
    ) -> BaseModel:
        """Invoke the language model and force output to match the given JSON schema (Pydantic model)."""
        pass

    def with_structured_output(self, schema: Type[BaseModel], method: str | None = None) -> _StructuredInvoker:
        return _StructuredInvoker(self, schema)

    def bind_tools(self, tools: Iterable[Any]) -> _ToolBoundClient:
        return _ToolBoundClient(self, tools)

    def consume_invocation_record(self) -> dict[str, Any] | None:
        return None
