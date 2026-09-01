from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.enterprise_capabilities.browser.engine.form_input.identity import find_field, stable_field_key
from app.enterprise_capabilities.browser.engine.form_input.value_equivalence import field_values_equivalent
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


FILL_RECONCILIATION_TAG = "[fill_reconciliation]"


@dataclass
class _PendingFill:
    decision: Decision
    target: Dict[str, Any]
    stable_key: str


@dataclass
class FillRetryPolicy:
    """Schedules bounded retries for transient, pre-commit fill failures."""

    max_retries: int = 2
    _attempts: Dict[str, int] = field(default_factory=dict)
    _pending: Optional[_PendingFill] = None

    def after_result(
        self,
        decision: Decision,
        *,
        ok: bool,
        error: Optional[str],
        before: Optional[Observation] = None,
    ) -> Optional[Decision]:
        if decision.tool != "browser_fill":
            return None
        target = _target_for(before, str((decision.args or {}).get("ref") or ""))
        key = self._key(decision, target)
        if ok:
            self._attempts.pop(key, None)
            self._pending = None
            return None
        if not _is_retryable(error):
            return None
        attempts = self._attempts.get(key, 0)
        if attempts >= self.max_retries:
            self._pending = None
            return None
        self._attempts[key] = attempts + 1
        self._pending = _PendingFill(
            decision=decision,
            target=target,
            stable_key=key,
        )
        return Decision(
            tool="browser_observe",
            args={},
            rationale=(
                f"{FILL_RECONCILIATION_TAG} inspect the field after an ambiguous fill "
                "before deciding whether another mutation is necessary"
            ),
        )

    def after_observation(self, observation: Observation) -> Optional[Decision]:
        pending = self._pending
        if pending is None:
            return None
        original_args = dict(pending.decision.args or {})
        target = find_field(
            observation.elements,
            pending.target,
            str(original_args.get("ref") or ""),
        )
        if target is not None and field_values_equivalent(
            target.get("value"),
            original_args.get("value"),
            target=pending.target,
        ):
            self._attempts.pop(pending.stable_key, None)
            self._pending = None
            return None
        if target is None:
            self._pending = None
            return None
        # A non-empty mismatch proves that the previous mutation changed the
        # field without replacing its old value. Retrying would append the
        # same text again and make recovery progressively harder.
        if _normalize(target.get("value")):
            self._pending = None
            return None
        original_args["ref"] = str(target.get("ref") or original_args.get("ref") or "")
        self._pending = None
        return Decision(
            tool="browser_fill",
            args=original_args,
            rationale=(
                "system retry: a fresh observation confirmed that the requested "
                "value is absent; retry the same stable field once"
            ),
        )

    def assistance_required(
        self,
        decision: Decision,
        *,
        error: Optional[str],
        before: Optional[Observation] = None,
    ) -> bool:
        """Return true only after this stable fill exhausted local recovery.

        Infrastructure failures and arbitrary non-retryable errors remain on
        the executor's existing failure path.  This deliberately narrows the
        human handoff to failures for which this policy actually spent its
        bounded retry budget.
        """
        if decision.tool != "browser_fill" or not _is_retryable(error):
            return False
        target = _target_for(before, str((decision.args or {}).get("ref") or ""))
        return self._attempts.get(self._key(decision, target), 0) >= self.max_retries

    def export_state(self) -> Dict[str, Any]:
        pending = self._pending
        return {
            "version": 1,
            "max_retries": self.max_retries,
            "attempts": dict(self._attempts),
            "pending": (
                {
                    "decision": {
                        "tool": pending.decision.tool,
                        "args": dict(pending.decision.args or {}),
                        "rationale": pending.decision.rationale,
                    },
                    "target": dict(pending.target),
                    "stable_key": pending.stable_key,
                }
                if pending is not None else None
            ),
        }

    def restore_state(self, payload: Dict[str, Any]) -> None:
        self.max_retries = max(0, int((payload or {}).get("max_retries") or self.max_retries))
        self._attempts = {
            str(key): max(0, int(value))
            for key, value in dict((payload or {}).get("attempts") or {}).items()
        }
        pending = (payload or {}).get("pending")
        decision = pending.get("decision") if isinstance(pending, dict) else None
        self._pending = (
            _PendingFill(
                decision=Decision(
                    tool=str(decision.get("tool") or ""),
                    args=dict(decision.get("args") or {}),
                    rationale=str(decision.get("rationale") or ""),
                ),
                target=dict(pending.get("target") or {}),
                stable_key=str(pending.get("stable_key") or ""),
            )
            if isinstance(pending, dict) and isinstance(decision, dict)
            else None
        )

    @staticmethod
    def _key(decision: Decision, target: Optional[Dict[str, Any]] = None) -> str:
        args = dict(decision.args or {})
        identity = stable_field_key(target) if target else str(args.get("ref") or "")
        return f"{args.get('domain', '')}\0{identity}\0{args.get('value', '')}"


def _target_for(observation: Optional[Observation], ref: str) -> Dict[str, Any]:
    if observation is None:
        return {}
    return next((
        dict(item) for item in observation.elements
        if isinstance(item, dict) and str(item.get("ref") or "") == ref
    ), {})


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _is_retryable(error: Optional[str]) -> bool:
    text = str(error or "").strip().lower()
    return any(marker in text for marker in (
        "dispatch-error",
        "human control",
        "agent_control_wait_timeout",
        "target_not_focused",
        "target_not_found",
        "value_not_applied",
    ))


def is_fill_reconciliation(decision: Decision) -> bool:
    return FILL_RECONCILIATION_TAG in str(decision.rationale or "")


__all__ = ["FillRetryPolicy", "is_fill_reconciliation"]
