"""Log tool availability and model decisions without message or argument content."""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)


def log_tool_offer(*, session_id: str, profile_version: str, model_id: str, model_name: str,
                   incoming: list[dict[str, Any]] | None, visible: list[dict[str, Any]] | None,
                   knowledge_only: bool) -> None:
    incoming_names = [str(tool.get("name") or "") for tool in incoming or []]
    visible_names = [str(tool.get("name") or "") for tool in visible or []]
    LOGGER.info(
        "model_gateway_tool_offer session_id=%s profile_version=%s model_id=%s model_name=%s "
        "incoming_count=%d incoming_names=%s visible_count=%d visible_names=%s "
        "tool_choice=%s knowledge_only=%s",
        session_id, profile_version, model_id, model_name, len(incoming_names), incoming_names,
        len(visible_names), visible_names, "auto" if visible_names else "none", knowledge_only,
    )


def log_tool_result(*, session_id: str, model_id: str, saw_text: bool,
                    raw_count: int, calls: list[dict[str, str]],
                    incomplete_calls: list[dict[str, str]]) -> None:
    LOGGER.info(
        "model_gateway_tool_result session_id=%s model_id=%s saw_text=%s raw_call_fragment_count=%d "
        "valid_call_count=%d call_names=%s incomplete_call_count=%d incomplete_names=%s "
        "missing_id_count=%d missing_name_count=%d",
        session_id, model_id, saw_text, raw_count, len(calls), [call["name"] for call in calls],
        len(incomplete_calls), [call["name"] for call in incomplete_calls],
        sum(not call["id"] for call in incomplete_calls),
        sum(not call["name"] for call in incomplete_calls),
    )


def log_tool_error(*, session_id: str, model_id: str, code: str) -> None:
    LOGGER.warning("model_gateway_tool_error session_id=%s model_id=%s code=%s", session_id, model_id, code)
