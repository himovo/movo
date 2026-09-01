from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


async def begin_recorded_human_handoff(
    bridge: Any,
    *,
    recording_id: str,
    run_id: str,
    node_id: str,
    category: str,
) -> str:
    """Start sidecar recording best-effort, but always transfer ownership."""

    active_recording_id = recording_id
    try:
        await bridge.send_command(
            "recording_start",
            recording_id=recording_id,
            recording_mode="assistance",
            run_id=run_id,
            node_id=node_id,
            category=category,
        )
    except Exception as exc:
        active_recording_id = ""
        logger.warning(
            "browser human assistance recording unavailable",
            extra={
                "event": "browser.human_recording_start_failed",
                "error": str(exc),
            },
        )
    await bridge.send_command("set_owner", owner="human")
    return active_recording_id


__all__ = ["begin_recorded_human_handoff"]

