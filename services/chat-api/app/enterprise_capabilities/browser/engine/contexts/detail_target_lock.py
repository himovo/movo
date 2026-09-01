"""Bounded target lock for opening one object from a dynamic result list."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .detail_progress import DetailTargetFingerprint, same_detail_resource


@dataclass
class DetailTargetLock:
    target: Optional[DetailTargetFingerprint] = None
    attempts: int = 0
    observation_due: bool = False
    action_pending: bool = False
    detail_confirmed: bool = False
    detail_url: str = ""
    max_attempts: int = 2
    exhausted_targets: set[str] = field(default_factory=set)
    excluded_target_details: dict[str, dict[str, object]] = field(default_factory=dict)

    def prepare(self, candidate: DetailTargetFingerprint) -> bool:
        candidate_key = detail_target_key(candidate)
        if candidate_key and candidate_key in self.exhausted_targets:
            return False
        if self.target is not None and self.attempts >= self.max_attempts:
            current_key = detail_target_key(self.target)
            if current_key:
                self.exhausted_targets.add(current_key)
            self.target = None
        if self.target is None:
            self.target = candidate
            self.attempts = 0
            self.observation_due = False
            self.detail_confirmed = False
            self.detail_url = ""
        elif not detail_targets_match(self.target, candidate):
            return False
        self.action_pending = True
        return True

    def finish_action(
        self,
        *,
        detail_confirmed: bool,
        detail_url: str = "",
        retain_confirmed: bool = False,
    ) -> None:
        if not self.action_pending:
            return
        self.action_pending = False
        if detail_confirmed:
            if retain_confirmed:
                self.detail_confirmed = True
                self.detail_url = str(detail_url or "").strip()
                self.observation_due = False
            else:
                self.clear()
            return
        self.attempts += 1
        self.observation_due = True
        if self.attempts >= self.max_attempts and self.target is not None:
            key = detail_target_key(self.target)
            if key:
                self.exhausted_targets.add(key)

    def finish_observation(
        self,
        *,
        detail_confirmed: bool,
        detail_url: str = "",
        retain_confirmed: bool = False,
    ) -> None:
        self.action_pending = False
        if detail_confirmed:
            if retain_confirmed and self.target is not None:
                self.detail_confirmed = True
                self.detail_url = str(detail_url or self.detail_url).strip()
                self.observation_due = False
            else:
                self.clear()
            return
        self.observation_due = False

    def exclude_current(self, *, reason: str) -> Optional[DetailTargetFingerprint]:
        """Exclude the current business object after a verified dead end."""
        target = self.target
        if target is None:
            return None
        key = detail_target_key(target)
        if key:
            self.exhausted_targets.add(key)
            self.excluded_target_details[key] = {
                "target_url": target.target_url,
                "labels": list(target.labels),
                "source_url": target.source_url,
                "reason": str(reason or "").strip(),
            }
        self.clear()
        return target

    def excluded_constraints(self) -> list[str]:
        constraints: list[str] = []
        for item in list(self.excluded_target_details.values())[-8:]:
            labels = [
                str(value).strip()
                for value in list(item.get("labels") or [])
                if str(value).strip()
            ]
            identity = str(item.get("target_url") or "") or (
                labels[0] if labels else ""
            )
            reason = str(item.get("reason") or "").strip()
            if identity:
                constraints.append(
                    f"候选“{identity}”已淘汰，不要再次选择"
                    + (f"：{reason}" if reason else "。")
                )
        return constraints

    def suggest(self, observation: Observation) -> Optional[Decision]:
        if (
            self.target is None
            or self.detail_confirmed
            or self.attempts >= self.max_attempts
        ):
            return None
        if self.observation_due:
            return Decision(
                tool="browser_observe",
                args={},
                rationale="verify the selected detail target before another click",
            )
        if self.attempts <= 0:
            return None
        ref = locate_locked_target(self.target, observation)
        if not ref:
            # The virtualized result disappeared after a fresh observation.
            # Release the lock so the planner may choose another visible item.
            self.attempts = self.max_attempts
            key = detail_target_key(self.target)
            if key:
                self.exhausted_targets.add(key)
            return None
        return Decision(
            tool="browser_click",
            args={"ref": ref},
            rationale="retry the same selected business object after fresh observation",
        )

    def replacement(self, observation: Observation) -> Optional[Decision]:
        if (
            self.target is None
            or self.detail_confirmed
            or self.attempts >= self.max_attempts
        ):
            return None
        ref = locate_locked_target(self.target, observation)
        if not ref:
            return None
        return Decision(
            tool="browser_click",
            args={"ref": ref},
            rationale="keep the current detail target locked until verified or exhausted",
        )

    def clear(self) -> None:
        self.target = None
        self.attempts = 0
        self.observation_due = False
        self.action_pending = False
        self.detail_confirmed = False
        self.detail_url = ""

    def as_dict(self) -> dict:
        return {
            "target_url": self.target.target_url if self.target else "",
            "target_labels": list(self.target.labels) if self.target else [],
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "observation_due": self.observation_due,
            "detail_confirmed": self.detail_confirmed,
            "detail_url": self.detail_url,
            "exhausted_target_count": len(self.exhausted_targets),
            "excluded_targets": list(self.excluded_target_details.values())[-8:],
        }


def detail_targets_match(
    left: DetailTargetFingerprint,
    right: DetailTargetFingerprint,
) -> bool:
    if left.content_context_id and right.content_context_id:
        return left.content_context_id == right.content_context_id
    if left.target_url and right.target_url:
        return same_detail_resource(left.target_url, right.target_url)
    if left.scope_id and right.scope_id:
        return left.scope_id == right.scope_id
    return bool(set(left.labels).intersection(right.labels))


def locate_locked_target(
    target: DetailTargetFingerprint,
    observation: Observation,
) -> str:
    candidates = [item for item in observation.elements if isinstance(item, dict)]
    if target.content_context_id:
        for item in candidates:
            ref = str(item.get("ref") or "").strip()
            context_id = str(item.get("contentContextId") or "").strip()
            if ref and context_id == target.content_context_id:
                return ref
    if target.target_url:
        for item in candidates:
            ref = str(item.get("ref") or "").strip()
            href = str(item.get("href") or "").strip()
            if ref and href and same_detail_resource(target.target_url, href):
                return ref
    if target.scope_id:
        for item in candidates:
            ref = str(item.get("ref") or "").strip()
            scope_id = _element_scope_identity(item)
            if ref and scope_id == target.scope_id:
                return ref
        return ""
    labels = set(target.labels)
    for item in candidates:
        ref = str(item.get("ref") or "").strip()
        if not ref:
            continue
        values = {
            _normalise_text(item.get(key))
            for key in ("name", "text", "scopeName", "scopeText")
            if item.get(key)
        }
        if labels.intersection(values):
            return ref
    return ""


def _normalise_text(value: object) -> str:
    return " ".join(str(value or "").split()).strip()[:240]


def detail_target_key(target: DetailTargetFingerprint) -> str:
    if target.content_context_id:
        return f"content:{target.content_context_id}"
    if target.target_url:
        return f"url:{target.target_url}"
    if target.scope_id:
        return f"scope:{target.scope_id}"
    labels = "|".join(target.labels)
    return f"labels:{labels}" if labels else ""


def _element_scope_identity(item: dict[str, object]) -> str:
    return str(
        item.get("scopeId")
        or item.get("scopeSelector")
        or item.get("componentOwnerSelector")
        or item.get("selector")
        or ""
    ).strip()


__all__ = [
    "DetailTargetLock",
    "detail_target_key",
    "detail_targets_match",
    "locate_locked_target",
]
