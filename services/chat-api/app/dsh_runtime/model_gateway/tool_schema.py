"""Translate DSH's neutral tool definitions to provider-client contracts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def to_openai_chat_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return the canonical tool shape expected by ASKAI's BaseLLM clients.

    DSH exposes function tools as ``{name, description, parameters}``, while the
    OpenAI-compatible chat contract wraps that payload in ``type/function``.
    Already-normalized definitions are retained so callers can safely retry or
    compose gateway adapters without double wrapping.
    """
    normalized: list[dict[str, Any]] = []
    for raw in tools or []:
        if raw.get("type") == "function" and isinstance(raw.get("function"), dict):
            function = deepcopy(raw["function"])
        else:
            function = {
                "name": raw.get("name"),
                "description": raw.get("description", ""),
                "parameters": raw.get("parameters") or raw.get("inputSchema"),
            }

        name = str(function.get("name") or "").strip()
        if not name:
            raise ValueError("tool definition is missing name")
        parameters = function.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {"type": "object", "properties": {}}

        canonical_function: dict[str, Any] = {
            "name": name,
            "description": str(function.get("description") or ""),
            "parameters": deepcopy(parameters),
        }
        if "strict" in function:
            canonical_function["strict"] = bool(function["strict"])
        normalized.append({"type": "function", "function": canonical_function})
    return normalized
