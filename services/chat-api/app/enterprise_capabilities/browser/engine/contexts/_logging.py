"""Shared debug logger for browser task contexts.

All decision-point events are emitted at WARNING level so they show
up in the default log stream without extra config. Each line is
single-line and structured so it's grep-friendly:

    [browser_ctx] event=<name> ctx=<General|Form|Scrape> <k=v ...>

Events we surface:
    ctx_init              — which context class was picked by the factory
    phase_advance         — state machine transition
    rule_autoexec         — rules produced a unique candidate and clicked it
    force_nav             — context-owned navigation fired
    validate_reject       — pre-flight audit rejected an LLM decision
    validate_rewrite      — pre-flight audit rewrote an LLM decision
    verify                — CRUD op marked verified by structural signal
    done_gate             — browser_done was blocked by the context
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.enterprise_capabilities.browser.engine.contexts")


def _fmt(ctx_name: str, event: str, **fields: Any) -> str:
    parts = [f"ctx={ctx_name}", f"event={event}"]
    for k, v in fields.items():
        if v is None or v == "":
            continue
        s = str(v).replace("\n", " ")
        if len(s) > 160:
            s = s[:157] + "..."
        parts.append(f"{k}={s!r}" if " " in s else f"{k}={s}")
    return "[browser_ctx] " + " ".join(parts)


def emit(ctx_name: str, event: str, **fields: Any) -> None:
    """Warning-level structured log. Never raises — a broken field
    rendering must not break the calling control flow."""
    try:
        logger.warning(_fmt(ctx_name, event, **fields))
    except Exception:
        pass
