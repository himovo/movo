from __future__ import annotations

from pathlib import Path


CHAT_API_ROOT = Path(__file__).parents[2]


def test_formal_application_registers_dsh_chat_not_legacy_chat_router() -> None:
    source = (CHAT_API_ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "app.include_router(dsh_chat.router" in source
    assert "app.include_router(chat.router" not in source


def test_dsh_chat_does_not_import_legacy_runtime_or_orchestrator() -> None:
    source = (CHAT_API_ROOT / "app" / "api" / "endpoints" / "dsh_chat.py").read_text(encoding="utf-8")
    forbidden = (
        "app.runtime.streaming",
        "app.services.chat_pipeline_service",
        "app.orchestrator",
        "app.skillsystem",
    )
    assert not any(value in source for value in forbidden)
