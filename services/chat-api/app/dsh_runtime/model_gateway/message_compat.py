"""Normalize legacy DSH tool messages before calling a model provider."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _call_id(value: dict[str, Any]) -> str:
    source = value.get("source")
    source_id = source.get("callId") if isinstance(source, dict) else None
    return str(
        value.get("toolCallId")
        or value.get("tool_call_id")
        or source_id
        or ""
    )


def normalize_tool_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a provider-safe copy of DSH history.

    Old DSH sessions may omit the call id on a wrapped ``tool-result``. A
    missing id is restored only when exactly one prior tool call is awaiting a
    result. Ambiguous or incomplete tool exchanges are removed as a unit while
    preserving surrounding user and assistant text.
    """

    output: list[dict[str, Any]] = []
    pending: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}

    def discard_pending() -> None:
        affected: list[dict[str, Any]] = []
        for message, block in pending.values():
            content = message.get("content")
            if isinstance(content, list) and block in content:
                content.remove(block)
            if message not in affected:
                affected.append(message)
        for message in affected:
            if message in output and not message.get("content") and not message.get("tool_calls"):
                output.remove(message)
        pending.clear()

    def resolve_id(value: dict[str, Any]) -> str:
        explicit = _call_id(value)
        if explicit:
            return explicit if explicit in pending else ""
        return next(iter(pending)) if len(pending) == 1 else ""

    for original in messages:
        message = deepcopy(original)
        role = str(message.get("role") or "user")
        content = message.get("content")
        blocks = content if isinstance(content, list) else []
        is_tool_message = role == "tool"
        wrapped_results = [
            block for block in blocks
            if isinstance(block, dict) and block.get("type") == "tool-result"
        ]

        if not is_tool_message and not wrapped_results and pending:
            discard_pending()

        if role == "assistant":
            output.append(message)
            for block in blocks:
                if not isinstance(block, dict) or block.get("type") != "tool-call":
                    continue
                identifier = str(block.get("id") or "")
                if identifier:
                    pending[identifier] = (message, block)
            continue

        if is_tool_message:
            identifier = resolve_id(message)
            if not identifier:
                continue
            message["toolCallId"] = identifier
            pending.pop(identifier, None)
            output.append(message)
            continue

        if wrapped_results:
            compatible_results: list[dict[str, Any]] = []
            for block in wrapped_results:
                identifier = resolve_id(block)
                if not identifier:
                    continue
                block["toolCallId"] = identifier
                pending.pop(identifier, None)
                compatible_results.append(block)
            if compatible_results:
                message["content"] = compatible_results
                output.append(message)
            continue

        output.append(message)

    if pending:
        discard_pending()
    return output
