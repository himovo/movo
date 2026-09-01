import json
from typing import AsyncGenerator, List, Type, Any, Dict
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.llm.types import Message, Role, LLMResponse
from app.llm.base import BaseLLMClient
from app.llm.structured_fallback import (
    build_structured_fallback_messages,
    sanitize_structured_fallback_kwargs,
    validate_structured_text,
)


class DefaultOpenAIClient(BaseLLMClient):
    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str = "gpt-4o",
        streaming: bool = True,
        structured_output_mode: str = "native",
        **kwargs,
    ):
        self.model = model
        self.streaming = streaming
        self.structured_output_mode = str(structured_output_mode or "native").strip().lower()
        self._last_invocation_meta: Dict[str, Any] | None = None
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            **kwargs,
        )

    def _set_last_invocation_meta(
        self,
        *,
        usage: Dict[str, int] | None = None,
        response_payload: Dict[str, Any] | None = None,
    ) -> None:
        self._last_invocation_meta = {
            "model_name": self.model,
            "model_id": self.model,
            "usage": usage or {},
            "response_payload": response_payload or {},
        }

    def consume_invocation_record(self) -> Dict[str, Any] | None:
        meta = self._last_invocation_meta
        self._last_invocation_meta = None
        return meta

    @staticmethod
    def _parse_tool_arguments(raw: Any) -> Any:
        if isinstance(raw, (dict, list)):
            return raw
        text = str(raw or "").strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            return {"_raw": text}

    def _convert_tool_calls(self, tool_calls: Any) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for call in list(tool_calls or []):
            if not isinstance(call, dict):
                continue
            function = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = str(call.get("name") or function.get("name") or "").strip()
            if not name:
                continue
            arguments = call.get("arguments")
            if arguments is None:
                arguments = function.get("arguments")
            if arguments is None and "args" in call:
                arguments = json.dumps(call.get("args") or {}, ensure_ascii=False)
            if isinstance(arguments, (dict, list)):
                arguments = json.dumps(arguments, ensure_ascii=False)
            result.append(
                {
                    "id": str(call.get("id") or ""),
                    "type": str(call.get("type") or "function"),
                    "function": {
                        "name": name,
                        "arguments": str(arguments or "{}"),
                    },
                }
            )
        return result

    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        result = []
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role")
                content = msg.get("content")
                name = msg.get("name")
                tool_calls = msg.get("tool_calls")
                tool_call_id = msg.get("tool_call_id")
            else:
                role = msg.role
                content = msg.content
                name = msg.name
                tool_calls = msg.tool_calls
                tool_call_id = msg.tool_call_id
            role_value = role.value if isinstance(role, Role) else str(role or "")
            msg_dict = {"role": role_value, "content": content}
            if name:
                msg_dict["name"] = name
            if tool_calls:
                normalized_calls = self._convert_tool_calls(tool_calls)
                if normalized_calls:
                    msg_dict["tool_calls"] = normalized_calls
            if tool_call_id:
                msg_dict["tool_call_id"] = tool_call_id
            result.append(msg_dict)
        return result

    async def ainvoke(self, messages: List[Message], **kwargs) -> LLMResponse:
        self._last_invocation_meta = None
        oai_messages = self._convert_messages(messages)
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=oai_messages,
            stream=False,
            **kwargs
        )
        choice = response.choices[0]
        
        tool_calls = None
        if choice.message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "name": tc.function.name,
                    "args": self._parse_tool_arguments(tc.function.arguments),
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                } for tc in choice.message.tool_calls
            ]
            
        msg = Message(
            role=Role(choice.message.role) if choice.message.role else Role.ASSISTANT,
            content=choice.message.content or "",
            tool_calls=tool_calls
        )
        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        self._set_last_invocation_meta(
            usage=usage,
            response_payload=response.model_dump(),
        )
        return LLMResponse(message=msg, raw_response=response.model_dump(), usage=usage)

    async def astream(self, messages: List[Message], **kwargs) -> AsyncGenerator[LLMResponse, None]:
        self._last_invocation_meta = None
        oai_messages = self._convert_messages(messages)
        stream_kwargs = dict(kwargs)
        stream_options = dict(stream_kwargs.get("stream_options") or {})
        stream_options.setdefault("include_usage", True)
        stream_kwargs["stream_options"] = stream_options
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=oai_messages,
            stream=True,
            **stream_kwargs
        )
        
        role = Role.ASSISTANT
        usage: Dict[str, int] | None = None
        final_payload: Dict[str, Any] | None = None
        
        async for chunk in stream:
            final_payload = chunk.model_dump()
            if getattr(chunk, "usage", None):
                usage = {
                    "prompt_tokens": int(getattr(chunk.usage, "prompt_tokens", 0) or 0),
                    "completion_tokens": int(getattr(chunk.usage, "completion_tokens", 0) or 0),
                    "total_tokens": int(getattr(chunk.usage, "total_tokens", 0) or 0),
                }
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta.role:
                    role = Role(delta.role)
                if delta.content:
                    msg = Message(role=role, content=delta.content)
                    yield LLMResponse(message=msg, raw_response=chunk.model_dump())
                if getattr(delta, "tool_calls", None):
                    calls = []
                    for call in delta.tool_calls:
                        function = getattr(call, "function", None)
                        calls.append({
                            "index": int(getattr(call, "index", 0) or 0),
                            "id": str(getattr(call, "id", "") or ""),
                            "name": str(getattr(function, "name", "") or ""),
                            "arguments_delta": str(getattr(function, "arguments", "") or ""),
                        })
                    yield LLMResponse(
                        message=Message(role=role, content="", tool_calls=calls),
                        raw_response=chunk.model_dump(),
                    )
        self._set_last_invocation_meta(usage=usage, response_payload=final_payload)

    async def ainvoke_structured(
        self, 
        messages: List[Message], 
        schema: Type[BaseModel], 
        **kwargs
    ) -> BaseModel:
        self._last_invocation_meta = None
        if self.structured_output_mode not in {"native", "openai_native"}:
            fallback_messages = build_structured_fallback_messages(messages, schema)
            response = await self.ainvoke(
                fallback_messages,
                **sanitize_structured_fallback_kwargs(dict(kwargs or {})),
            )
            raw_content = str(response.message.content or "")
            try:
                return validate_structured_text(raw_content, schema)
            except Exception:
                repair_messages = build_structured_fallback_messages(
                    [
                        Message(
                            role=Role.USER,
                            content=(
                                "Fix this model output so it is valid JSON matching the schema. "
                                "Return only the corrected JSON.\n\n"
                                f"Model output:\n{raw_content}"
                            ),
                        )
                    ],
                    schema,
                )
                repaired = await self.ainvoke(
                    repair_messages,
                    **sanitize_structured_fallback_kwargs(dict(kwargs or {})),
                )
                return validate_structured_text(str(repaired.message.content or ""), schema)

        oai_messages = self._convert_messages(messages)
        
        response = await self.client.beta.chat.completions.parse(
            model=self.model,
            messages=oai_messages,
            response_format=schema,
            **kwargs
        )
        usage = None
        if getattr(response, "usage", None):
            usage = {
                "prompt_tokens": int(getattr(response.usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(response.usage, "completion_tokens", 0) or 0),
                "total_tokens": int(getattr(response.usage, "total_tokens", 0) or 0),
            }
        self._set_last_invocation_meta(
            usage=usage,
            response_payload=response.model_dump(),
        )
        return response.choices[0].message.parsed
