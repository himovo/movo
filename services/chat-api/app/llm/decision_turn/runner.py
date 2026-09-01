from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Type, TypeVar

from pydantic import BaseModel

from app.llm.base import BaseLLMClient
from app.llm.decision_turn.contracts import DecisionOutput, DecisionTurnVisibility, normalize_decision_commentary
from app.llm.decision_turn.context import current_decision_turn_channel
from app.llm.types import Message, Role


logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
CommentarySink = Callable[[Dict[str, str]], Awaitable[None] | None]

_INSTRUCTION = (
    "This is a decision turn. The business result remains authoritative. "
    "When this turn makes a material plan, finding, transition, pivot, or blocker useful to the user, you MUST include commentary. "
    "Omit commentary only for a purely mechanical classification with nothing useful to explain. "
    "Use the user's language and return commentary as {text, reason}. "
    "If another instruction enumerates output keys, commentary is an additional allowed key. "
    "Do not expose hidden reasoning, repeat generic status, or let commentary change any business field. "
    "Commentary must describe the concrete approach or finding, not merely say that work is starting or complete."
)

_TOOL_INSTRUCTION = (
    "This is a tool-selection decision turn. Keep tool calls and their arguments unchanged as the authoritative result. "
    "When a concrete explanation would help the user, you may put one concise commentary sentence in ordinary assistant content "
    "using the user's language. Do not output JSON, hidden reasoning, or a generic status. Omit content when there is nothing useful to say."
)


@dataclass(frozen=True)
class DecisionTurnSpec:
    locale: str
    turn_id: str
    sink: CommentarySink | None = None
    accept_compatible_decision_output: bool = False
    visibility: DecisionTurnVisibility = DecisionTurnVisibility.USER_VISIBLE


def _messages_for_decision(messages: List[Message]) -> List[Message]:
    copied = [message.model_copy(deep=True) for message in messages]
    for message in copied:
        if message.role == Role.SYSTEM:
            message.content = f"{str(message.content or '').rstrip()}\n\n{_INSTRUCTION}"
            return copied
    return [Message(role=Role.SYSTEM, content=_INSTRUCTION), *copied]


def _messages_for_spec(messages: List[Message], spec: DecisionTurnSpec) -> List[Message]:
    if spec.visibility == DecisionTurnVisibility.INTERNAL:
        return [message.model_copy(deep=True) for message in messages]
    return _messages_for_decision(messages)


def _messages_for_tool_decision(messages: List[Message]) -> List[Message]:
    copied = [message.model_copy(deep=True) for message in messages]
    for message in copied:
        if message.role == Role.SYSTEM:
            message.content = f"{str(message.content or '').rstrip()}\n\n{_TOOL_INSTRUCTION}"
            return copied
    return [Message(role=Role.SYSTEM, content=_TOOL_INSTRUCTION), *copied]


def _messages_for_tool_spec(messages: List[Message], spec: DecisionTurnSpec) -> List[Message]:
    if spec.visibility == DecisionTurnVisibility.INTERNAL:
        return [message.model_copy(deep=True) for message in messages]
    return _messages_for_tool_decision(messages)


async def _publish(value: Any, spec: DecisionTurnSpec) -> None:
    if spec.visibility == DecisionTurnVisibility.INTERNAL:
        return
    channel = current_decision_turn_channel()
    locale = spec.locale or (channel.locale if channel is not None else "")
    payload = normalize_decision_commentary(value, locale=locale)
    if payload is None:
        return
    payload["turn_id"] = str(spec.turn_id)
    if spec.sink is None:
        if channel is not None:
            channel.publish(payload)
        return
    try:
        result = spec.sink(payload)
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        logger.warning(
            "decision commentary sink failed",
            extra={"event": "llm.decision_commentary_sink_failed", "turn_id": spec.turn_id, "error": str(exc)[:240]},
        )


async def invoke_structured_decision(
    client: BaseLLMClient,
    schema: Type[T],
    messages: List[Message],
    *,
    spec: DecisionTurnSpec,
    **kwargs: Any,
) -> T:
    if not issubclass(schema, DecisionOutput):
        raise TypeError(f"decision schema must inherit DecisionOutput: {schema.__name__}")
    prepared_messages = _messages_for_spec(messages, spec)
    structured_invoke = getattr(client, "ainvoke_structured", None)
    if callable(structured_invoke):
        result = await structured_invoke(prepared_messages, schema, **kwargs)
    else:
        # Preserve compatibility with LangChain-shaped/request-scoped wrappers
        # that only expose with_structured_output().
        invoker = client.with_structured_output(schema, method="function_calling")
        result = await invoker.ainvoke(prepared_messages, **kwargs)
    if isinstance(result, schema):
        parsed = result
    elif spec.accept_compatible_decision_output and isinstance(result, DecisionOutput):
        # A small number of staged schema migrations deliberately accept the
        # previous decision model and project it downstream. This must be
        # opted into by that call site; it is never the global default.
        parsed = result
    else:
        parsed = schema.model_validate(result)
    await _publish(parsed.commentary, spec)
    return parsed


async def invoke_json_decision(
    client: BaseLLMClient,
    messages: List[Message],
    *,
    parser: Callable[[Any], Dict[str, Any]],
    spec: DecisionTurnSpec,
    **kwargs: Any,
) -> Dict[str, Any]:
    response = await client.ainvoke(_messages_for_spec(messages, spec), **kwargs)
    data = parser(getattr(response, "content", response))
    await _publish(data.get("commentary"), spec)
    return data


async def invoke_text_decision(
    client: BaseLLMClient,
    messages: List[Message],
    *,
    spec: DecisionTurnSpec,
    commentary_parser: Callable[[Any], Dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Any:
    """Run a decision turn without taking ownership of raw-output parsing."""

    response = await client.ainvoke(_messages_for_spec(messages, spec), **kwargs)
    if commentary_parser is not None:
        try:
            data = commentary_parser(getattr(response, "content", response))
            await _publish(data.get("commentary"), spec)
        except Exception:
            # Optional narration must not consume malformed raw output that a
            # caller's established recovery parser may still understand.
            pass
    return response


async def invoke_tool_decision(
    client: Any,
    messages: List[Message],
    *,
    spec: DecisionTurnSpec,
    **kwargs: Any,
) -> Any:
    """Run one tool-selection turn without changing the provider tool-call shape."""

    response = await client.ainvoke(_messages_for_tool_spec(messages, spec), **kwargs)
    if getattr(response, "tool_calls", None):
        text = str(getattr(response, "content", "") or "").strip()
        if text:
            await _publish({"text": text, "reason": "progress"}, spec)
    return response
