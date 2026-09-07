"""Recover a new browser run that starts on an already completed target."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision,
    Observation,
    StepRecord,
)
from app.enterprise_capabilities.browser.engine.alternative_target_recovery import (
    AlternativeTargetRecovery,
)
from app.enterprise_capabilities.browser.engine.business_action import (
    browser_target_identity,
)
from app.enterprise_capabilities.browser.engine.target_identity import (
    observation_target_aliases,
)


@dataclass
class CompletedTargetRecovery:
    """Choose a grounded route away from an already completed detail page.

    Routes are tried in evidence order: a source observed in this run, a
    source persisted with the successful action, then a trusted task entry.
    Every route is attempted at most once so recovery cannot become another
    observe/navigate loop.
    """

    attempted_routes: set[str] = field(default_factory=set)

    def blocked_target(
        self,
        observation: Observation,
        recovery: AlternativeTargetRecovery,
    ) -> str:
        aliases = observation_target_aliases(observation)
        return next(
            (alias for alias in aliases if alias in recovery.excluded_target_ids),
            "",
        )

    def recovery_decision(
        self,
        *,
        observation: Observation,
        history: Iterable[StepRecord],
        candidate_entries: Sequence[Mapping[str, Any]],
        recovery: AlternativeTargetRecovery,
    ) -> Decision | None:
        target = self.blocked_target(observation, recovery)
        if not target:
            return None

        routes: list[tuple[str, str]] = []
        observed = recovery.recovery_decision(history=history, target_id=target)
        if observed is not None:
            routes.append((str(observed.args.get("url") or ""), "observed_candidate_list"))
        remembered = recovery.source_url_for(target)
        if remembered:
            routes.append((remembered, "persisted_candidate_source"))
        routes.extend(
            (str(entry.get("url") or ""), "task_entry")
            for entry in candidate_entries
            if isinstance(entry, Mapping)
        )
        site_root = _observed_site_root(observation.url)
        if site_root:
            routes.append((site_root, "observed_site_root"))

        for route, source in routes:
            route_id = _route_identity(route)
            if not self._usable_route(
                route=route,
                route_id=route_id,
                current_url=observation.url,
                recovery=recovery,
            ):
                continue
            self.attempted_routes.add(route_id)
            return Decision(
                tool="browser_navigate",
                args={"url": route},
                rationale=(
                    "current page is a completed target excluded by task policy; "
                    f"recover through grounded {source}"
                ),
            )
        return None

    def export_state(self) -> dict[str, Any]:
        return {"attempted_routes": sorted(self.attempted_routes)}

    def restore_state(self, payload: Mapping[str, Any] | None) -> None:
        self.attempted_routes = {
            route
            for route in (
                _route_identity(item)
                for item in list((payload or {}).get("attempted_routes") or [])
            )
            if route
        }

    def _usable_route(
        self,
        *,
        route: str,
        route_id: str,
        current_url: str,
        recovery: AlternativeTargetRecovery,
    ) -> bool:
        if not route_id or route_id in self.attempted_routes:
            return False
        if route_id == _route_identity(current_url):
            return False
        if route_id in recovery.excluded_target_ids:
            return False
        try:
            return urlsplit(route).scheme.casefold() in {"http", "https"}
        except ValueError:
            return False


def _route_identity(value: Any) -> str:
    raw = str(value or "").strip()
    _system, target = browser_target_identity(raw)
    if target:
        return target
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme.casefold() not in {"http", "https"} or not parts.netloc:
        return ""
    return f"{parts.scheme.casefold()}://{parts.netloc.casefold()}/"


def _observed_site_root(value: Any) -> str:
    try:
        parts = urlsplit(str(value or "").strip())
    except ValueError:
        return ""
    if parts.scheme.casefold() not in {"http", "https"} or not parts.netloc:
        return ""
    return f"{parts.scheme.casefold()}://{parts.netloc}/"


__all__ = ["CompletedTargetRecovery"]
