"""Text-only slide planning using the configured presentation content model."""
from __future__ import annotations

from typing import Any
from app.llm.factory import get_llm_client
from app.llm.configured_multimodal import parse_json_object
from app.llm.types import Message, Role


class PagePlanClient:
    async def call_json(self, *, prompt: str, stage: str, intent: str = "generation",
                        user_id: str = "", session_id: str = "",
                        request_payload_extra: dict[str, Any] | None = None) -> dict[str, Any]:
        client = get_llm_client(
            streaming=False, stage=stage, intent=intent,
            output_spec={"user_id": user_id, "session_id": session_id, **(request_payload_extra or {})},
        )
        result = await client.ainvoke([Message(role=Role.USER, content=prompt)])
        return parse_json_object(str(result.content or ""))
