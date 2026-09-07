"""Task-level policy for selecting previously processed browser targets.

The planner understands the user's language once and emits a small structured
directive.  This module retains that directive and turns durable action facts
into candidate exclusions.  It deliberately does not parse user wording.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation
from app.enterprise_capabilities.browser.engine.alternative_target_recovery import (
    AlternativeTargetRecovery,
)


TargetHistoryMode = Literal["exclude_completed", "allow_completed", "unspecified"]
logger = logging.getLogger(__name__)


class TargetHistoryDirective(BaseModel):
    policy: TargetHistoryMode = "unspecified"
    operation: str = Field(default="", max_length=120)
    reason: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def require_operation_for_explicit_policy(self) -> "TargetHistoryDirective":
        if self.policy != "unspecified" and not normalize_operation(self.operation):
            raise ValueError("target history operation is required for an explicit policy")
        return self


@dataclass
class TargetHistoryState:
    policy: TargetHistoryMode = "unspecified"
    operation: str = ""
    reason: str = ""
    _loaded_operations: set[str] = field(default_factory=set)

    def adopt(self, decision: Decision) -> bool:
        commentary = decision.commentary if isinstance(decision.commentary, dict) else {}
        raw = commentary.get("target_history")
        if not isinstance(raw, dict):
            return False
        try:
            directive = TargetHistoryDirective.model_validate(raw)
        except Exception:
            return False

        changed = False
        operation = normalize_operation(directive.operation)
        if operation and not self.operation:
            self.operation = operation
            changed = True
        if self.policy == "unspecified" and directive.policy != "unspecified":
            self.policy = directive.policy
            self.reason = str(directive.reason or "").strip()
            changed = True
        return changed

    @property
    def excludes_completed(self) -> bool:
        return self.policy == "exclude_completed" and bool(self.operation)

    async def load_completed_targets(
        self,
        *,
        store: Any,
        actor_id: str,
        recovery: AlternativeTargetRecovery,
    ) -> int:
        if not self.excludes_completed or self.operation in self._loaded_operations:
            return 0
        rows = await store.list_succeeded_for_operation(
            actor_id=str(actor_id or "anonymous"),
            operation_id=self.operation,
        )
        aliases: list[str] = []
        for row in rows:
            row_aliases = [
                str(item) for item in list(getattr(row, "target_aliases", []) or [])
            ]
            row_aliases.append(str(getattr(row, "target_id", "") or ""))
            aliases.extend(row_aliases)
            source_url = str(
                getattr(row, "source_url", "")
                or dict(getattr(row, "evidence", {}) or {}).get("source_url")
                or ""
            )
            recovery.remember_source(row_aliases, source_url)
        recovery.exclude_many(aliases)
        self._loaded_operations.add(self.operation)
        return len({item for item in aliases if item})

    async def synchronize(
        self,
        *,
        store: Any,
        actor_id: str,
        recovery: AlternativeTargetRecovery,
        decision: Decision | None = None,
    ) -> None:
        changed = self.adopt(decision) if decision is not None else False
        if changed:
            logger.info(
                "browser target history directive adopted",
                extra={
                    "event": "browser.target_history_directive",
                    "policy": self.policy,
                    "operation": self.operation,
                    "reason": self.reason[:300],
                },
            )
        try:
            loaded = await self.load_completed_targets(
                store=store,
                actor_id=actor_id,
                recovery=recovery,
            )
        except Exception as exc:
            logger.warning(
                "browser completed target lookup failed open",
                extra={
                    "event": "browser.target_history_load_failed",
                    "operation": self.operation,
                    "error": str(exc)[:500],
                },
            )
            return
        if loaded:
            logger.info(
                "browser completed targets loaded for selection",
                extra={
                    "event": "browser.target_history_loaded",
                    "policy": self.policy,
                    "operation": self.operation,
                    "target_alias_count": loaded,
                },
            )

    def export_state(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "operation": self.operation,
            "reason": self.reason,
            "loaded_operations": sorted(self._loaded_operations),
        }

    def restore_state(self, payload: dict[str, Any]) -> None:
        try:
            directive = TargetHistoryDirective.model_validate(payload or {})
        except Exception:
            return
        self.policy = directive.policy
        self.operation = normalize_operation(directive.operation)
        self.reason = str(directive.reason or "").strip()
        self._loaded_operations = {
            normalize_operation(item)
            for item in list((payload or {}).get("loaded_operations") or [])
            if normalize_operation(item)
        }

    def blocked_selection_ref(
        self,
        decision: Decision,
        observation: Observation,
        recovery: AlternativeTargetRecovery,
    ) -> str:
        if not self.excludes_completed:
            return ""
        for tool, args in _atomic_actions(decision):
            if tool != "browser_click":
                continue
            ref = str(args.get("ref") or "").strip()
            target = next(
                (
                    item for item in observation.elements
                    if isinstance(item, dict) and str(item.get("ref") or "") == ref
                ),
                None,
            )
            if not target or not _is_candidate_navigation(target):
                continue
            if recovery.element_is_excluded(target, page_url=observation.url):
                return ref
        return ""


def normalize_operation(value: Any) -> str:
    text = re.sub(r"[^a-z0-9_.:-]+", "_", str(value or "").strip().casefold())
    return text.strip("_")[:120]


def _atomic_actions(decision: Decision) -> list[tuple[str, dict[str, Any]]]:
    if decision.tool != "browser_execute_plan":
        return [(str(decision.tool or ""), dict(decision.args or {}))]
    return [
        (str(item.get("tool") or ""), dict(item.get("args") or {}))
        for item in list((decision.args or {}).get("actions") or [])
        if isinstance(item, dict)
    ]


def _is_candidate_navigation(target: dict[str, Any]) -> bool:
    purpose = str(target.get("semanticPurpose") or "").strip().casefold()
    if purpose in {"send", "submit", "publish", "save", "create", "delete"}:
        return False
    return bool(
        str(target.get("href") or "").strip()
        or str(target.get("contentContextId") or "").strip()
    )


__all__ = [
    "TargetHistoryDirective",
    "TargetHistoryMode",
    "TargetHistoryState",
    "normalize_operation",
]
