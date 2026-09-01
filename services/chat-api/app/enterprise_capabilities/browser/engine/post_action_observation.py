from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


def observation_retry_required(result: Any) -> bool:
    return isinstance(result, dict) and bool(result.get("observation_pending"))


def reconcile_post_action_observation(
    action_result: Dict[str, Any],
    observation_result: Any,
) -> Dict[str, Any]:
    merged = deepcopy(action_result)
    fresh = _observation_payload(observation_result)
    if fresh is None:
        return merged

    previous = _observation_payload(action_result) or {}
    effects = list(previous.get("effects") or [])
    if effects:
        fresh["effects"] = effects
    merged["observation"] = fresh
    merged["url"] = str(fresh.get("url") or merged.get("url") or "")
    merged["title"] = str(fresh.get("title") or merged.get("title") or "")
    merged["observation_pending"] = False
    receipt = dict(merged.get("action_receipt") or {})
    receipt.update({
        "status": "observed_after_retry",
        "observationPending": False,
    })
    merged["action_receipt"] = receipt
    return merged


def _observation_payload(value: Any) -> Dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    nested = value.get("observation")
    if isinstance(nested, dict):
        return deepcopy(nested)
    if "url" in value and "elements" in value:
        return deepcopy(value)
    return None


__all__ = ["observation_retry_required", "reconcile_post_action_observation"]
