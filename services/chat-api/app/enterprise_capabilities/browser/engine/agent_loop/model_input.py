from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.llm.capabilities import model_supports_capability
from app.llm.configured_models import get_configured_model_context


@dataclass(frozen=True)
class BrowserModelInput:
    content: Any
    text_content: str
    includes_screenshot: bool


def build_browser_model_input(
    user_turn: str,
    screenshot: str | None,
    *,
    model_config: dict[str, Any] | None = None,
) -> BrowserModelInput:
    config = model_config if model_config is not None else get_configured_model_context()
    encoded = str(screenshot or "").strip()
    if not encoded or not model_supports_capability(config, "vision"):
        return BrowserModelInput(
            content=user_turn,
            text_content=user_turn,
            includes_screenshot=False,
        )
    return BrowserModelInput(
        content=[
            {"type": "text", "text": user_turn},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
            },
        ],
        text_content=user_turn,
        includes_screenshot=True,
    )
