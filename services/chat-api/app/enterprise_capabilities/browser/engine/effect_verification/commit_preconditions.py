"""Preconditions for treating a click as a business commit.

Effect discovery describes what a control appears to do. This policy adds the
workflow state that a label alone cannot express: opening an editor is still an
interaction transition, and a structured publish payload cannot be committed
before any of its fields have been confirmed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .contracts import EffectContract


_ENTRY_OPERATION_PREFIXES = (
    "choose",
    "enter",
    "expand",
    "navigate",
    "navigation",
    "open",
    "select",
    "show",
    "switch",
    "进入",
    "展开",
    "打开",
    "查看",
    "选择",
    "切换",
)


@dataclass(frozen=True)
class CommitPreconditionDecision:
    contract: EffectContract
    downgraded: bool = False
    reason: str = ""


def enforce_commit_preconditions(
    contract: EffectContract,
    *,
    requires_form_input: bool,
    has_confirmed_form_input: bool,
) -> CommitPreconditionDecision:
    """Downgrade entry clicks that do not yet satisfy commit prerequisites.

    This does not block the physical click. It only prevents an entry or
    navigation action from producing a side-effect receipt and completing the
    browser task prematurely.
    """
    if not contract.is_commit:
        return CommitPreconditionDecision(contract=contract)

    intended_operation = _normalize_operation(contract.intended_operation)
    if _is_entry_operation(intended_operation):
        return _downgrade(
            contract,
            reason=(
                "semantic alignment identifies this click as an entry "
                "transition, not the final business commit"
            ),
        )

    if requires_form_input and not has_confirmed_form_input:
        return _downgrade(
            contract,
            reason=(
                "structured form input is required but no authoritative "
                "payload field has been confirmed"
            ),
        )

    return CommitPreconditionDecision(contract=contract)


def _normalize_operation(value: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(value or "").strip().casefold())


def _is_entry_operation(operation: str) -> bool:
    return any(
        operation == prefix or operation.startswith(prefix)
        for prefix in _ENTRY_OPERATION_PREFIXES
    )


def _downgrade(
    contract: EffectContract,
    *,
    reason: str,
) -> CommitPreconditionDecision:
    fingerprint = dict(contract.fingerprint or {})
    fingerprint["commit_precondition"] = "entry_transition"
    return CommitPreconditionDecision(
        contract=contract.model_copy(update={
            "operation_family": "navigate",
            "side_effect": "none",
            "is_commit": False,
            "completes_goal": False,
            "fingerprint": fingerprint,
        }),
        downgraded=True,
        reason=reason,
    )


__all__ = [
    "CommitPreconditionDecision",
    "enforce_commit_preconditions",
]
