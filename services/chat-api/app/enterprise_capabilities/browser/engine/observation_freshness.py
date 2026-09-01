"""Freshness and state identity for native-CDP browser observations."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any, Iterable

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


STATE_CHANGING_TOOLS = frozenset({
    "browser_navigate",
    "browser_tab_new",
    "browser_click",
    "browser_click_at",
    "browser_hover",
    "browser_fill",
    "browser_type_at",
    "browser_select",
    "browser_press",
    "browser_scroll",
    "browser_upload_file",
    "browser_paste_image",
    "browser_back",
    "browser_forward",
})


def observation_fingerprint(
    *,
    url: str,
    title: str,
    page_text: str,
    elements: Iterable[dict[str, Any]],
) -> str:
    """Build a bounded semantic fingerprint without persisting transient refs."""
    controls = []
    for item in elements:
        if not isinstance(item, dict):
            continue
        controls.append({
            key: item.get(key)
            for key in (
                "role", "name", "text", "type", "value", "disabled",
                "editable", "visible", "scopeId", "href",
            )
            if item.get(key) not in (None, "")
        })
        if len(controls) >= 160:
            break
    payload = {
        "url": str(url or ""),
        "title": str(title or ""),
        "page_text": str(page_text or "")[:8000],
        "controls": controls,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def complete_observation(observation: Observation) -> Observation:
    fingerprint = observation.state_fingerprint or observation_fingerprint(
        url=observation.url,
        title=observation.title,
        page_text=observation.page_text,
        elements=observation.elements,
    )
    revision = observation.revision or f"state:{fingerprint}"
    return replace(
        observation,
        revision=revision,
        state_fingerprint=fingerprint,
        fresh=True,
    )


def adopt_probed_observation(
    current: Observation,
    probed: Observation | None,
) -> Observation:
    """Adopt any concrete probe, including a freshly observed blank tab."""
    if probed is None or not str(probed.url or "").strip():
        return current
    if current.screenshot and probed.url == current.url and not probed.screenshot:
        return replace(probed, screenshot=current.screenshot)
    return probed


def invalidate_observation(
    observation: Observation,
    *,
    url: str = "",
    title: str = "",
) -> Observation:
    """Retain page location but remove all observation-local element refs."""
    return Observation(
        url=str(url or observation.url or ""),
        title=str(title or observation.title or ""),
        elements=[],
        revision="",
        state_fingerprint="",
        fresh=False,
        interaction=observation.interaction,
        viewport=observation.viewport,
    )


def requires_fresh_observation(tool: str) -> bool:
    return str(tool or "") in STATE_CHANGING_TOOLS


__all__ = [
    "adopt_probed_observation",
    "complete_observation",
    "invalidate_observation",
    "observation_fingerprint",
    "requires_fresh_observation",
]
