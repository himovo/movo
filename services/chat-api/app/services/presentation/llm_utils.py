from __future__ import annotations

import json
import re
from typing import Any, Dict, Type, TypeVar

from pydantic import BaseModel

from app.llm.factory import get_llm_client
from app.llm.types import Message, Role

T = TypeVar("T")


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_as_text(item) for item in value)
    if isinstance(value, dict):
        for key in ("text", "content", "output"):
            if key in value:
                return _as_text(value.get(key))
    return str(value or "")


def _extract_json_candidate(text: str) -> str:
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", stripped, flags=re.DOTALL)
    if fence:
        return fence.group(1).strip()
    start_obj = stripped.find("{")
    start_arr = stripped.find("[")
    starts = [idx for idx in (start_obj, start_arr) if idx >= 0]
    if not starts:
        return stripped
    start = min(starts)
    end_obj = stripped.rfind("}")
    end_arr = stripped.rfind("]")
    end = max(end_obj, end_arr)
    if end >= start:
        return stripped[start : end + 1].strip()
    return stripped[start:].strip()


def _repair_common_json_issues(text: str) -> str:
    repaired = text.strip()
    repaired = re.sub(r"```(?:json)?|```", "", repaired, flags=re.IGNORECASE).strip()
    repaired = repaired.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    repaired = re.sub(r'("\s*:\s*"[^"]*")\s+(")', r"\1, \2", repaired)
    repaired = re.sub(r'([}\]0-9"\'\u4e00-\u9fff])\s+("[-A-Za-z0-9_\u4e00-\u9fff]+"\s*:)', r"\1, \2", repaired)
    return repaired


def _validate_json_text(model_cls: Type[T], text: str) -> T:
    if isinstance(model_cls, type) and issubclass(model_cls, BaseModel):
        return model_cls.model_validate_json(text)
    return model_cls(**json.loads(text))


async def _repair_with_llm(*, llm: Any, model_cls: Type[T], malformed_text: str, stage: str) -> T:
    schema_text = ""
    if isinstance(model_cls, type) and issubclass(model_cls, BaseModel):
        schema_text = json.dumps(model_cls.model_json_schema(), ensure_ascii=False, default=str)
    response = await llm.ainvoke(
        [
            Message(
                role=Role.SYSTEM,
                content=(
                    "Repair malformed JSON into valid JSON only.\n"
                    "Do not add commentary.\n"
                    "Keep the original meaning and fields.\n"
                    "Return a JSON object matching the target schema.\n"
                ),
            ),
            Message(
                role=Role.USER,
                content=json.dumps(
                    {
                        "stage": stage,
                        "schema": schema_text,
                        "malformed_json": malformed_text,
                    },
                    ensure_ascii=False,
                ),
            ),
        ]
    )
    candidate = _repair_common_json_issues(_extract_json_candidate(_as_text(response.content)))
    return _validate_json_text(model_cls, candidate)


async def invoke_structured(
    *,
    model_cls: Type[T],
    system_prompt: str,
    payload: Dict[str, Any],
    stage: str,
    intent: str = "generation",
    images: list[dict] | None = None,
) -> T:
    """Invoke an LLM with structured output.

    When `images` is provided (list of OpenAI-style multimodal parts, e.g.
    `{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}`),
    the user message becomes a multimodal content list combining the JSON
    payload and the images. When omitted, behavior is identical to a plain
    text-only structured call.
    """
    llm = get_llm_client(streaming=False, stage=stage, intent=intent)
    structured = llm.with_structured_output(model_cls, method="function_calling")
    payload_text = json.dumps(payload, ensure_ascii=False)
    if images:
        user_content: list[dict] = [{"type": "text", "text": payload_text}]
        user_content.extend(images)
        user_message = Message(role=Role.USER, content=user_content)
    else:
        user_message = Message(role=Role.USER, content=payload_text)
    messages = [
        Message(role=Role.SYSTEM, content=system_prompt),
        user_message,
    ]
    try:
        return await structured.ainvoke(messages)
    except Exception as original_error:
        raw = await llm.ainvoke(messages)
        raw_text = _as_text(raw.content)
        candidate = _extract_json_candidate(raw_text)
        try:
            return _validate_json_text(model_cls, candidate)
        except Exception:
            repaired = _repair_common_json_issues(candidate)
            try:
                return _validate_json_text(model_cls, repaired)
            except Exception:
                try:
                    return await _repair_with_llm(
                        llm=llm,
                        model_cls=model_cls,
                        malformed_text=candidate,
                        stage=stage,
                    )
                except Exception:
                    raise original_error
