import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Type

from openai import AsyncAzureOpenAI
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel

from app.llm.base import BaseLLMClient
from app.llm.types import LLMResponse, Message, Role

logger = logging.getLogger(__name__)


class AzureOpenAIClient(BaseLLMClient):
    def __init__(
        self,
        api_key: str,
        azure_endpoint: str,
        api_version: str,
        azure_deployment: str,
        streaming: bool = True,
        **kwargs,
    ):
        self.deployment = azure_deployment
        self.streaming = streaming
        self._last_invocation_meta: Dict[str, Any] | None = None
        kwargs.setdefault("timeout", 90.0)
        self.client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
            **kwargs,
        )

    def _set_last_invocation_meta(
        self,
        *,
        usage: Dict[str, int] | None = None,
        response_payload: Dict[str, Any] | None = None,
    ) -> None:
        self._last_invocation_meta = {
            "model_name": self.deployment,
            "model_id": self.deployment,
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

    @staticmethod
    def _convert_content(content: Any) -> Any:
        if not isinstance(content, list):
            return content
        result: List[Dict[str, Any]] = []
        for part in content:
            if not isinstance(part, dict):
                result.append({"type": "input_text", "text": str(part or "")})
                continue
            part_type = str(part.get("type") or "").strip()
            if part_type in {"text", "input_text"}:
                result.append({"type": "input_text", "text": str(part.get("text") or "")})
                continue
            if part_type in {"image_url", "input_image"}:
                image_url = part.get("image_url")
                if isinstance(image_url, dict):
                    image_url = image_url.get("url")
                result.append({"type": "input_image", "image_url": str(image_url or "")})
                continue
            result.append(part)
        return result

    def _convert_tool_calls(self, tool_calls: Any) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for call in list(tool_calls or []):
            if not isinstance(call, dict):
                continue
            function = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = str(call.get("name") or function.get("name") or "").strip()
            call_id = str(call.get("id") or call.get("call_id") or "").strip()
            if not name or not call_id:
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
                    "type": "function_call",
                    "call_id": call_id,
                    "name": name,
                    "arguments": str(arguments or "{}"),
                    "status": "completed",
                }
            )
        return result

    def _convert_messages(self, messages: List[Message]) -> tuple[str, List[Dict[str, Any]]]:
        instructions_parts: List[str] = []
        result: List[Dict[str, Any]] = []
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role")
                content = msg.get("content")
                tool_calls = msg.get("tool_calls")
                tool_call_id = msg.get("tool_call_id")
            else:
                role = msg.role
                content = msg.content
                tool_calls = msg.tool_calls
                tool_call_id = msg.tool_call_id
            role_value = role.value if isinstance(role, Role) else str(role or "")
            if role_value == Role.SYSTEM.value:
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict) and str(part.get("type") or "") in {"text", "input_text"}:
                            text_parts.append(str(part.get("text") or ""))
                        elif not isinstance(part, dict):
                            text_parts.append(str(part or ""))
                    if text_parts:
                        instructions_parts.append("\n".join([p for p in text_parts if p]))
                else:
                    instructions_parts.append(str(content or ""))
                continue
            if role_value == Role.TOOL.value and tool_call_id:
                result.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(tool_call_id),
                        "output": str(content or ""),
                    }
                )
                continue
            result.append(
                {
                    "type": "message",
                    "role": role_value,
                    "content": self._convert_content(content),
                }
            )
            if tool_calls:
                result.extend(self._convert_tool_calls(tool_calls))
        instructions = "\n\n".join([part.strip() for part in instructions_parts if str(part or "").strip()]).strip()
        return instructions, result

    @staticmethod
    def _ensure_json_object_input_marker(input_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Responses json_object mode requires the word "json" in input, not only instructions."""
        serialized = json.dumps(input_items or [], ensure_ascii=False).lower()
        if "json" in serialized:
            return input_items
        return [
            {
                "type": "message",
                "role": "user",
                "content": "Return the final answer as JSON.",
            },
            *list(input_items or []),
        ]

    def _convert_messages_chat(self, messages: List[Message]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
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
            msg_dict: Dict[str, Any] = {"role": role_value, "content": content}
            if name:
                msg_dict["name"] = name
            if tool_calls:
                normalized_calls: List[Dict[str, Any]] = []
                for call in list(tool_calls or []):
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function") if isinstance(call.get("function"), dict) else {}
                    call_name = str(call.get("name") or function.get("name") or "").strip()
                    if not call_name:
                        continue
                    arguments = call.get("arguments")
                    if arguments is None:
                        arguments = function.get("arguments")
                    if arguments is None and "args" in call:
                        arguments = json.dumps(call.get("args") or {}, ensure_ascii=False)
                    if isinstance(arguments, (dict, list)):
                        arguments = json.dumps(arguments, ensure_ascii=False)
                    normalized_calls.append(
                        {
                            "id": str(call.get("id") or call.get("call_id") or ""),
                            "type": "function",
                            "function": {
                                "name": call_name,
                                "arguments": str(arguments or "{}"),
                            },
                        }
                    )
                if normalized_calls:
                    msg_dict["tool_calls"] = normalized_calls
            if tool_call_id:
                msg_dict["tool_call_id"] = tool_call_id
            result.append(msg_dict)
        return result

    @staticmethod
    def _convert_tools(tools: Any) -> List[Dict[str, Any]]:
        converted: List[Dict[str, Any]] = []
        for tool in list(tools or []):
            if not isinstance(tool, dict):
                continue
            if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
                fn = dict(tool.get("function") or {})
                converted.append(
                    {
                        "type": "function",
                        "name": str(fn.get("name") or ""),
                        "description": str(fn.get("description") or ""),
                        "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
                    }
                )
                continue
            converted.append(tool)
        return converted

    def _prepare_kwargs(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        prepared = dict(kwargs)
        prepared.pop("stream", None)
        prepared.pop("response_format", None)
        tools = prepared.get("tools")
        if tools is not None:
            prepared["tools"] = self._convert_tools(tools)
        return prepared

    @staticmethod
    def _prepare_chat_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Keep the Chat Completions fallback on its own wire contract."""
        prepared = dict(kwargs)
        prepared.pop("stream", None)
        prepared.pop("response_format", None)
        return prepared

    @staticmethod
    def _should_fallback_to_chat(exc: Exception) -> bool:
        text = str(exc or "").lower()
        return (
            "there was an issue with your request" in text
            or "invalid_request_error" in text
            or "request timed out" in text
            or "timed out" in text
        )

    @staticmethod
    def _is_strict_schema_supported(schema_dict: Dict[str, Any]) -> bool:
        def _walk(node: Any) -> bool:
            if isinstance(node, dict):
                node_type = node.get("type")
                if node_type == "object":
                    additional = node.get("additionalProperties")
                    props = node.get("properties")
                    if additional is True:
                        return False
                    if not props and additional not in (False, None):
                        return False
                for value in node.values():
                    if not _walk(value):
                        return False
            elif isinstance(node, list):
                for item in node:
                    if not _walk(item):
                        return False
            return True

        return _walk(schema_dict)

    @staticmethod
    def _extract_json_text(raw: str) -> str:
        text = str(raw or "").strip()
        if not text:
            return "{}"
        cleaned = text.replace("```json", "```").strip()
        if cleaned.startswith("```") and cleaned.endswith("```"):
            cleaned = cleaned[3:-3].strip()
        first_object = cleaned.find("{")
        first_array = cleaned.find("[")
        starts = [idx for idx in (first_object, first_array) if idx != -1]
        start = min(starts) if starts else -1
        if start != -1:
            stack: list[str] = []
            in_string = False
            escape = False
            for index in range(start, len(cleaned)):
                char = cleaned[index]
                if in_string:
                    if escape:
                        escape = False
                    elif char == "\\":
                        escape = True
                    elif char == '"':
                        in_string = False
                    continue
                if char == '"':
                    in_string = True
                    continue
                if char == "{":
                    stack.append("}")
                elif char == "[":
                    stack.append("]")
                elif char in {"}", "]"}:
                    if stack and stack[-1] == char:
                        stack.pop()
                    elif not stack:
                        return cleaned[start : index + 1]
                    if not stack:
                        return cleaned[start : index + 1]
            if stack:
                return cleaned[start:] + "".join(reversed(stack))
        return cleaned

    @staticmethod
    def _extract_usage(response: Any) -> Dict[str, int] | None:
        usage = getattr(response, "usage", None)
        if not usage:
            return None
        prompt_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or 0)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    @staticmethod
    def _content_stats(content: Any) -> Dict[str, int]:
        stats = {
            "text_chars": 0,
            "parts": 0,
            "images": 0,
        }
        if isinstance(content, list):
            for part in content:
                stats["parts"] += 1
                if isinstance(part, dict):
                    part_type = str(part.get("type") or "")
                    if part_type in {"text", "input_text"}:
                        stats["text_chars"] += len(str(part.get("text") or ""))
                    elif part_type in {"image_url", "input_image"}:
                        stats["images"] += 1
                else:
                    stats["text_chars"] += len(str(part or ""))
            return stats
        stats["text_chars"] = len(str(content or ""))
        return stats

    @classmethod
    def _input_summary(cls, input_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        summary = {
            "input_items": len(input_items or []),
            "message_count": 0,
            "function_call_count": 0,
            "function_call_output_count": 0,
            "input_text_chars": 0,
            "input_image_count": 0,
        }
        for item in list(input_items or []):
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "")
            if item_type == "message":
                summary["message_count"] += 1
                content_stats = cls._content_stats(item.get("content"))
                summary["input_text_chars"] += content_stats["text_chars"]
                summary["input_image_count"] += content_stats["images"]
            elif item_type == "function_call":
                summary["function_call_count"] += 1
            elif item_type == "function_call_output":
                summary["function_call_output_count"] += 1
                summary["input_text_chars"] += len(str(item.get("output") or ""))
        return summary

    @staticmethod
    def _tools_summary(tools: Any) -> Dict[str, Any]:
        tool_list = [tool for tool in list(tools or []) if isinstance(tool, dict)]
        names: List[str] = []
        for tool in tool_list[:8]:
            if tool.get("type") == "function":
                names.append(str(tool.get("name") or ""))
            else:
                names.append(str(tool.get("type") or ""))
        return {
            "tool_count": len(tool_list),
            "tool_names_sample": names,
        }

    @classmethod
    def _response_format_summary(cls, response_format: Any) -> Dict[str, Any]:
        if response_format is None:
            return {"response_format_kind": "none"}
        if isinstance(response_format, type) and issubclass(response_format, BaseModel):
            schema_dict = to_strict_json_schema(response_format)
            return {
                "response_format_kind": "pydantic_model",
                "response_format_model": response_format.__name__,
                "response_format_schema_supported": cls._is_strict_schema_supported(schema_dict),
                "response_format_schema_keys": sorted(schema_dict.keys()),
            }
        if isinstance(response_format, dict):
            summary = {
                "response_format_kind": "dict",
                "response_format_type": str(response_format.get("type") or ""),
                "response_format_keys": sorted(response_format.keys()),
            }
            json_schema = response_format.get("json_schema")
            if isinstance(json_schema, dict):
                summary["response_format_json_schema_keys"] = sorted(json_schema.keys())
            return summary
        return {
            "response_format_kind": type(response_format).__name__,
            "response_format_repr": str(response_format)[:200],
        }

    @classmethod
    def _request_summary(
        cls,
        *,
        instructions: str,
        input_items: List[Dict[str, Any]],
        prepared: Dict[str, Any],
        response_format: Any,
    ) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "instructions_chars": len(str(instructions or "")),
            "prepared_keys": sorted(prepared.keys()),
        }
        summary.update(cls._input_summary(input_items))
        summary.update(cls._tools_summary(prepared.get("tools")))
        summary.update(cls._response_format_summary(response_format))
        for key in ("temperature", "max_output_tokens", "max_completion_tokens", "tool_choice", "parallel_tool_calls"):
            if key in prepared:
                summary[key] = prepared.get(key)
        return summary

    @staticmethod
    def _extract_response_tool_calls(response: Any) -> List[Dict[str, Any]] | None:
        output = list(getattr(response, "output", None) or [])
        tool_calls: List[Dict[str, Any]] = []
        for item in output:
            if str(getattr(item, "type", "") or "") != "function_call":
                continue
            tool_calls.append(
                {
                    "id": str(getattr(item, "call_id", "") or getattr(item, "id", "") or ""),
                    "call_id": str(getattr(item, "call_id", "") or ""),
                    "type": "function",
                    "name": str(getattr(item, "name", "") or ""),
                    "args": AzureOpenAIClient._parse_tool_arguments(getattr(item, "arguments", "")),
                    "function": {
                        "name": str(getattr(item, "name", "") or ""),
                        "arguments": str(getattr(item, "arguments", "") or "{}"),
                    },
                }
            )
        return tool_calls or None

    @staticmethod
    def _exception_details(exc: Exception) -> Dict[str, Any]:
        details: Dict[str, Any] = {
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
        }
        status_code = getattr(exc, "status_code", None)
        if status_code is not None:
            details["status_code"] = status_code
        response = getattr(exc, "response", None)
        if response is not None:
            details["response_status_code"] = getattr(response, "status_code", None)
            headers = getattr(response, "headers", None)
            if headers is not None:
                for header_name in ("x-request-id", "apim-request-id", "x-ms-request-id"):
                    header_value = headers.get(header_name)
                    if header_value:
                        details[header_name.replace("-", "_")] = str(header_value)
            try:
                details["response_text"] = str(response.text or "")[:2000]
            except Exception:
                pass
            try:
                response_json = response.json()
            except Exception:
                response_json = None
            if isinstance(response_json, dict):
                details["response_json"] = json.dumps(response_json, ensure_ascii=False, default=str)[:2000]
                error_obj = response_json.get("error")
                if isinstance(error_obj, dict):
                    if error_obj.get("code") is not None:
                        details["provider_error_code"] = str(error_obj.get("code"))
                    if error_obj.get("message") is not None:
                        details["provider_error_message"] = str(error_obj.get("message"))[:1000]
                    if error_obj.get("param") is not None:
                        details["provider_error_param"] = str(error_obj.get("param"))
        body = getattr(exc, "body", None)
        if body is not None:
            try:
                details["body"] = json.dumps(body, ensure_ascii=False, default=str)[:2000]
            except Exception:
                details["body"] = str(body)[:2000]
            if isinstance(body, dict):
                error_obj = body.get("error")
                if isinstance(error_obj, dict):
                    if error_obj.get("code") is not None:
                        details.setdefault("provider_error_code", str(error_obj.get("code")))
                    if error_obj.get("message") is not None:
                        details.setdefault("provider_error_message", str(error_obj.get("message"))[:1000])
                    if error_obj.get("param") is not None:
                        details.setdefault("provider_error_param", str(error_obj.get("param")))
        return details

    def _log_responses_failure(
        self,
        exc: Exception,
        *,
        operation: str,
        request_summary: Dict[str, Any] | None = None,
    ) -> None:
        logger.warning(
            "azure responses request failed",
            extra={
                "event": "azure_openai.responses_failed",
                "operation": operation,
                "deployment": self.deployment,
                "request_summary": request_summary or {},
                **self._exception_details(exc),
            },
        )

    async def ainvoke(self, messages: List[Message], **kwargs) -> LLMResponse:
        self._last_invocation_meta = None
        instructions, input_items = self._convert_messages(messages)
        response_format = kwargs.get("response_format")
        prepared = self._prepare_kwargs(kwargs)
        request_summary = self._request_summary(
            instructions=instructions,
            input_items=input_items,
            prepared=prepared,
            response_format=response_format,
        )
        try:
            response = await self.client.responses.create(
                model=self.deployment,
                instructions=instructions or None,
                input=input_items,
                **prepared,
            )
            msg = Message(
                role=Role.ASSISTANT,
                content=str(getattr(response, "output_text", "") or ""),
                tool_calls=self._extract_response_tool_calls(response),
            )
            usage = self._extract_usage(response)
            self._set_last_invocation_meta(
                usage=usage,
                response_payload=response.model_dump(),
            )
            return LLMResponse(
                message=msg,
                raw_response=response.model_dump(),
                usage=usage,
            )
        except Exception as exc:
            self._log_responses_failure(exc, operation="ainvoke", request_summary=request_summary)
            if not self._should_fallback_to_chat(exc):
                raise
            chat_messages = self._convert_messages_chat(messages)
            chat_prepared = self._prepare_chat_kwargs(kwargs)
            chat_response = await self.client.chat.completions.create(
                model=self.deployment,
                messages=chat_messages,
                stream=False,
                **chat_prepared,
            )
            choice = chat_response.choices[0]
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
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.message.tool_calls
                ]
            msg = Message(
                role=Role(choice.message.role) if choice.message.role else Role.ASSISTANT,
                content=choice.message.content or "",
                tool_calls=tool_calls,
            )
            usage = None
            if chat_response.usage:
                usage = {
                    "prompt_tokens": chat_response.usage.prompt_tokens,
                    "completion_tokens": chat_response.usage.completion_tokens,
                    "total_tokens": chat_response.usage.total_tokens,
                }
            self._set_last_invocation_meta(
                usage=usage,
                response_payload=chat_response.model_dump(),
            )
            return LLMResponse(message=msg, raw_response=chat_response.model_dump(), usage=usage)

    async def astream(self, messages: List[Message], **kwargs) -> AsyncGenerator[LLMResponse, None]:
        self._last_invocation_meta = None
        instructions, input_items = self._convert_messages(messages)
        response_format = kwargs.get("response_format")
        prepared = self._prepare_kwargs(kwargs)
        request_summary = self._request_summary(
            instructions=instructions,
            input_items=input_items,
            prepared=prepared,
            response_format=response_format,
        )
        try:
            usage: Dict[str, int] | None = None
            final_payload: Dict[str, Any] | None = None
            stream = await self.client.responses.create(
                model=self.deployment,
                instructions=instructions or None,
                input=input_items,
                stream=True,
                **prepared,
            )
            async for event in stream:
                final_payload = event.model_dump()
                event_type = str(getattr(event, "type", "") or "")
                if event_type == "response.completed":
                    usage = self._extract_usage(getattr(event, "response", None) or event)
                if event_type == "response.output_item.done":
                    item = getattr(event, "item", None)
                    if str(getattr(item, "type", "") or "") == "function_call":
                        yield LLMResponse(
                            message=Message(role=Role.ASSISTANT, content="", tool_calls=[{
                                "index": int(getattr(event, "output_index", 0) or 0),
                                "id": str(getattr(item, "call_id", "") or getattr(item, "id", "") or ""),
                                "name": str(getattr(item, "name", "") or ""),
                                "arguments": str(getattr(item, "arguments", "") or "{}"),
                            }]),
                            raw_response=event.model_dump(),
                        )
                    continue
                if event_type != "response.output_text.delta":
                    continue
                delta = str(getattr(event, "delta", "") or "")
                if not delta:
                    continue
                yield LLMResponse(
                    message=Message(role=Role.ASSISTANT, content=delta),
                    raw_response=event.model_dump(),
                )
            self._set_last_invocation_meta(usage=usage, response_payload=final_payload)
            return
        except Exception as exc:
            self._log_responses_failure(exc, operation="astream", request_summary=request_summary)
            if not self._should_fallback_to_chat(exc):
                raise
        chat_messages = self._convert_messages_chat(messages)
        chat_stream_kwargs = self._prepare_chat_kwargs(kwargs)
        stream_options = dict(chat_stream_kwargs.get("stream_options") or {})
        stream_options.setdefault("include_usage", True)
        chat_stream_kwargs["stream_options"] = stream_options
        stream = await self.client.chat.completions.create(
            model=self.deployment,
            messages=chat_messages,
            stream=True,
            **chat_stream_kwargs,
        )
        usage = None
        final_payload = None
        async for chunk in stream:
            final_payload = chunk.model_dump()
            if getattr(chunk, "usage", None):
                usage = {
                    "prompt_tokens": int(getattr(chunk.usage, "prompt_tokens", 0) or 0),
                    "completion_tokens": int(getattr(chunk.usage, "completion_tokens", 0) or 0),
                    "total_tokens": int(getattr(chunk.usage, "total_tokens", 0) or 0),
                }
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and getattr(delta, "content", None):
                yield LLMResponse(
                    message=Message(role=Role.ASSISTANT, content=str(delta.content or "")),
                    raw_response=chunk.model_dump(),
                )
            if delta and getattr(delta, "tool_calls", None):
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
                    message=Message(role=Role.ASSISTANT, content="", tool_calls=calls),
                    raw_response=chunk.model_dump(),
                )
        self._set_last_invocation_meta(usage=usage, response_payload=final_payload)

    async def ainvoke_structured(
        self,
        messages: List[Message],
        schema: Type[BaseModel],
        **kwargs,
    ) -> BaseModel:
        self._last_invocation_meta = None
        prepared = self._prepare_kwargs(kwargs)
        prepared.pop("text", None)
        strict_schema = to_strict_json_schema(schema)
        instructions, input_items = self._convert_messages(messages)
        strict_supported = self._is_strict_schema_supported(strict_schema)
        if strict_supported:
            response = await self.client.responses.parse(
                model=self.deployment,
                instructions=instructions or None,
                input=input_items,
                text={
                    "format": {
                        "type": "json_schema",
                        "strict": True,
                        "name": str(schema.__name__ or "StructuredResponse"),
                        "schema": strict_schema,
                    }
                },
                **prepared,
            )
            parsed = getattr(response, "output_parsed", None)
            self._set_last_invocation_meta(
                usage=self._extract_usage(response),
                response_payload=response.model_dump(),
            )
            if isinstance(parsed, schema):
                return parsed
            if parsed is not None:
                return schema.model_validate(parsed)
            return schema.model_validate_json(str(getattr(response, "output_text", "") or "{}"))
        logger.info(
            "structured schema is not strict-compatible; falling back to json_object",
            extra={
                "event": "azure_openai.structured_schema_fallback",
                "schema": str(getattr(schema, "__name__", "") or ""),
                "deployment": self.deployment,
            },
        )

        fallback_messages = [
            Message(
                role=Role.SYSTEM,
                content=(
                    "Return only valid JSON matching the requested schema exactly. "
                    "Do not include markdown fences, explanations, or extra keys."
                ),
            )
        ] + list(messages or [])
        fallback_instructions, fallback_input = self._convert_messages(fallback_messages)
        fallback_input = self._ensure_json_object_input_marker(fallback_input)
        try:
            response = await self.client.responses.create(
                model=self.deployment,
                instructions=fallback_instructions or None,
                input=fallback_input,
                text={"format": {"type": "json_object"}},
                **prepared,
            )
            self._set_last_invocation_meta(
                usage=self._extract_usage(response),
                response_payload=response.model_dump(),
            )
            return schema.model_validate_json(self._extract_json_text(str(getattr(response, "output_text", "") or "")))
        except Exception as exc:
            self._log_responses_failure(exc, operation="ainvoke_structured_json")
            if not self._should_fallback_to_chat(exc):
                raise
            chat_messages = self._convert_messages_chat(fallback_messages)
            chat_prepared = self._prepare_chat_kwargs(kwargs)
            chat_response = await self.client.chat.completions.create(
                model=self.deployment,
                messages=chat_messages,
                stream=False,
                response_format={"type": "json_object"},
                **chat_prepared,
            )
            usage = None
            if chat_response.usage:
                usage = {
                    "prompt_tokens": chat_response.usage.prompt_tokens,
                    "completion_tokens": chat_response.usage.completion_tokens,
                    "total_tokens": chat_response.usage.total_tokens,
                }
            self._set_last_invocation_meta(
                usage=usage,
                response_payload=chat_response.model_dump(),
            )
            content = chat_response.choices[0].message.content if chat_response.choices else ""
            return schema.model_validate_json(self._extract_json_text(str(content or "")))
