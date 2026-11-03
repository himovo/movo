"""Text-only slide planning using the configured presentation content model."""
from __future__ import annotations

from typing import Any
from app.llm.factory import get_llm_client
from app.llm.configured_multimodal import parse_json_object
from app.llm.types import Message, Role
from app.services.presentation.execution.failures import run_generation_step


class PagePlanClient:
    async def call_json(self, *, prompt: str, stage: str, intent: str = "generation",
                        user_id: str = "", session_id: str = "",
                        request_payload_extra: dict[str, Any] | None = None) -> dict[str, Any]:
        client = get_llm_client(
            streaming=False, stage=stage, intent=intent,
            output_spec={"user_id": user_id, "session_id": session_id, **(request_payload_extra or {})},
        )
        result = await run_generation_step(
            lambda: client.ainvoke([Message(role=Role.USER, content=prompt)]),
            stage="slide_content_planning",
            page_id=str((request_payload_extra or {}).get("page_id") or ""),
        )
        return parse_json_object(str(result.content or ""))
