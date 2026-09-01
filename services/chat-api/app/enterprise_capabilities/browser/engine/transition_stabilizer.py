"""Refresh observations after a click opens a new SPA page or tab."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any, Awaitable, Callable

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


Dispatch = Callable[[Decision], Awaitable[tuple[Any, bool, str | None]]]


async def stabilize_transition_observation(
    *,
    decision: Decision,
    before: Observation,
    result: Any,
    dispatch: Dispatch,
    max_probes: int = 2,
    wait_seconds: float = 0.25,
) -> Any:
    current = _observation_payload(result)
    if not _transitioned(decision, before, current):
        return result

    merged = deepcopy(result) if isinstance(result, dict) else {}
    initial_effects = list(current.get("effects") or [])
    previous_signature = _signature(current)
    stable_count = 0
    for _attempt in range(max(1, max_probes)):
        await asyncio.sleep(wait_seconds)
        probe, ok, _error = await dispatch(Decision(
            tool="browser_observe",
            args={},
            rationale="stabilize the newly opened page before selecting another element",
        ))
        fresh = _observation_payload(probe) if ok else None
        if fresh is None:
            continue
        signature = _signature(fresh)
        stable_count = stable_count + 1 if signature == previous_signature else 0
        previous_signature = signature
        if initial_effects:
            fresh["effects"] = _merge_effects(initial_effects, list(fresh.get("effects") or []))
        merged["observation"] = fresh
        merged["url"] = str(fresh.get("url") or merged.get("url") or "")
        merged["title"] = str(fresh.get("title") or merged.get("title") or "")
        if stable_count >= 1:
            break
    return merged


def _merge_effects(initial: list[Any], fresh: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for item in [*initial, *fresh]:
        marker = repr(item)
        if marker in seen:
            continue
        seen.add(marker)
        merged.append(item)
    return merged


def _transitioned(decision: Decision, before: Observation, after: dict[str, Any] | None) -> bool:
    if decision.tool not in {"browser_click", "browser_click_at", "browser_tab_new", "browser_back", "browser_forward"}:
        return False
    if after is None:
        return False
    return str(after.get("url") or "") != str(before.url or "") or str(after.get("title") or "") != str(before.title or "")


def _observation_payload(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    nested = value.get("observation")
    if isinstance(nested, dict):
        return deepcopy(nested)
    if "url" in value and "elements" in value:
        return deepcopy(value)
    return None


def _signature(observation: dict[str, Any] | None) -> tuple[Any, ...]:
    if observation is None:
        return ()
    elements = observation.get("elements") or []
    interactive = tuple(
        (
            str(item.get("role") or ""),
            str(item.get("name") or item.get("placeholder") or "")[:80],
            bool(item.get("editable")),
            str(item.get("href") or "")[:160],
        )
        for item in elements
        if isinstance(item, dict) and item.get("visible", True)
    )
    return (
        str(observation.get("url") or ""),
        str(observation.get("title") or ""),
        len(elements),
        hash(interactive),
    )


__all__ = ["stabilize_transition_observation"]
