"""Refine click effect contracts with the interaction that produced them."""
from __future__ import annotations

from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectContract


_NON_BUSINESS_PURPOSES = {
    "filter",
    "navigate",
    "navigation",
    "query",
    "search",
}

_EXPLICIT_BUSINESS_OPERATIONS = {
    "approve",
    "create",
    "delete",
    "publish",
    "reject",
    "save",
    "send",
    "update",
}


def refine_contract_for_interaction(
    contract: EffectContract,
    *,
    purpose: str,
) -> EffectContract:
    """Let a confirmed interaction purpose override a generic submit label.

    Accessibility trees frequently expose icon-only query controls as a generic
    ``Submit`` button. A confirmed query field in the same form is stronger
    evidence than that generic label. Explicit business controls remain commits.
    """
    normalized_purpose = str(purpose or "").strip().lower()
    if not normalized_purpose:
        return contract

    operation = str(contract.operation_family or "").strip().lower()
    if operation in _EXPLICIT_BUSINESS_OPERATIONS:
        return contract

    fingerprint = dict(contract.fingerprint)
    fingerprint["interaction_purpose"] = normalized_purpose
    updates: dict[str, object] = {"fingerprint": fingerprint}

    if normalized_purpose in _NON_BUSINESS_PURPOSES:
        updates.update({
            "operation_family": normalized_purpose,
            "side_effect": "none",
            "is_commit": False,
            "completes_goal": False,
        })

    return contract.model_copy(update=updates)


__all__ = ["refine_contract_for_interaction"]
