from __future__ import annotations

import json
from typing import Any, Type

from pydantic import BaseModel

from app.llm.types import Message, Role


def build_structured_fallback_messages(messages: list[Message], schema: Type[BaseModel]) -> list[Message]:
    schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False, default=str)
    instruction = (
        "Return only valid JSON matching this JSON schema. "
        "Do not include markdown fences, explanations, comments, or extra text. "
        "If a field is unknown, use the schema-compatible empty value.\n\n"
        f"JSON schema:\n{schema_text}"
    )
    return [Message(role=Role.SYSTEM, content=instruction)] + list(messages or [])


def extract_json_text(raw: str) -> str:
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
    if start == -1:
        return cleaned
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
    return cleaned[start:]


def validate_structured_text(raw: str, schema: Type[BaseModel]) -> BaseModel:
    json_text = extract_json_text(raw)
    return schema.model_validate_json(json_text)


def sanitize_structured_fallback_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(kwargs or {})
    prepared.pop("stream", None)
    prepared.pop("response_format", None)
    prepared.pop("tools", None)
    prepared.pop("tool_choice", None)
    return prepared
