"""Recover from a durable duplicate by returning to a proven candidate list."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision,
    Observation,
    StepRecord,
)
from app.enterprise_capabilities.browser.engine.business_action import (
    browser_target_identity,
)
from app.enterprise_capabilities.browser.engine.target_identity import (
    element_target_aliases,
    normalize_target_alias,
)


@dataclass
class AlternativeTargetRecovery:
    """Track targets skipped by cross-run replay protection.

    A return navigation is offered only when completed history proves that the
    blocked resource was opened by clicking it on another observed page.  This
    keeps exact-URL tasks exact while allowing list-selection tasks to continue
    with another candidate.
    """

    excluded_target_ids: set[str] = field(default_factory=set)
    source_url_by_target: Dict[str, str] = field(default_factory=dict)

    def exclude(self, target_id: str) -> None:
        target = _canonical_target(target_id)
        if target:
            self.excluded_target_ids.add(target)

    def exclude_many(self, target_ids: Iterable[str]) -> None:
        for target_id in target_ids:
            self.exclude(target_id)

    def remember_source(self, target_ids: Iterable[str], source_url: str) -> None:
        source = str(source_url or "").strip()
        if not _is_http_url(source):
            return
        for target_id in target_ids:
            target = _canonical_target(target_id)
            if target and _canonical_target(source) != target:
                self.source_url_by_target[target] = source

    def source_url_for(self, target_id: str) -> str:
        return self.source_url_by_target.get(_canonical_target(target_id), "")

    def source_url_from_history(
        self,
        *,
        history: Iterable[StepRecord],
        target_id: str,
    ) -> str:
        return _candidate_source_url(history, target_id)

    def element_is_excluded(self, element: Any, *, page_url: str = "") -> bool:
        aliases = element_target_aliases(element, page_url=page_url)
        return bool(set(aliases).intersection(self.excluded_target_ids))

    def recovery_decision(
        self,
        *,
        history: Iterable[StepRecord],
        target_id: str,
    ) -> Optional[Decision]:
        source_url = _candidate_source_url(history, target_id)
        if not source_url:
            return None
        self.exclude(target_id)
        return Decision(
            tool="browser_navigate",
            args={"url": source_url},
            rationale=(
                "cross-run duplicate came from an observed candidate list; "
                "return to that list and exclude the completed target"
            ),
        )

    def planning_observation(self, observation: Observation) -> Observation:
        """Hide only links whose durable URL identity is already excluded."""
        if not self.excluded_target_ids:
            return observation
        elements = [
            item for item in list(observation.elements or [])
            if not self.element_is_excluded(item, page_url=observation.url)
        ]
        if len(elements) == len(observation.elements or []):
            return observation
        return replace(observation, elements=elements)

    def augment_state_ledger(self, ledger: Dict[str, Any] | None) -> Dict[str, Any] | None:
        if not self.excluded_target_ids:
            return ledger
        updated = dict(ledger or {})
        constraints = list(updated.get("action_constraints") or [])
        constraints.append(
            "Do not reopen targets excluded by confirmed cross-run action history; "
            "choose another visible candidate."
        )
        notes = list(updated.get("notes") or [])
        notes.append({
            "excluded_completed_targets": sorted(self.excluded_target_ids)[:12],
        })
        updated["action_constraints"] = constraints
        updated["notes"] = notes
        return updated

    def export_state(self) -> Dict[str, Any]:
        return {
            "excluded_target_ids": sorted(self.excluded_target_ids),
            "source_url_by_target": dict(self.source_url_by_target),
        }

    def restore_state(self, payload: Dict[str, Any]) -> None:
        self.excluded_target_ids = {
            target
            for target in (
                _canonical_target(item)
                for item in list((payload or {}).get("excluded_target_ids") or [])
            )
            if target
        }
        self.source_url_by_target = {}
        for target, source in dict((payload or {}).get("source_url_by_target") or {}).items():
            self.remember_source([target], str(source or ""))

def _candidate_source_url(
    history: Iterable[StepRecord],
    target_id: str,
) -> str:
    target = _canonical_target(target_id)
    if not target:
        return ""
    records: List[StepRecord] = list(history)
    for record in reversed(records):
        if not record.ok or record.decision.tool != "browser_click":
            continue
        source_observation = record.decision_observation or record.observation
        ref = str((record.decision.args or {}).get("ref") or "")
        if not ref:
            continue
        clicked = next(
            (
                item for item in list(source_observation.elements or [])
                if isinstance(item, dict) and str(item.get("ref") or "") == ref
            ),
            None,
        )
        clicked_aliases = set(element_target_aliases(
            clicked,
            page_url=str(source_observation.url or ""),
        ))
        if not clicked or target not in clicked_aliases:
            continue
        source_url = str(source_observation.url or "").strip()
        if _is_http_url(source_url) and _canonical_target(source_url) != target:
            return source_url
    return ""


def _canonical_target(value: Any) -> str:
    _system, target = browser_target_identity(str(value or ""))
    return str(target or normalize_target_alias(value)).strip()


def _is_http_url(value: str) -> bool:
    try:
        return urlsplit(value).scheme.lower() in {"http", "https"}
    except ValueError:
        return False


__all__ = ["AlternativeTargetRecovery"]
