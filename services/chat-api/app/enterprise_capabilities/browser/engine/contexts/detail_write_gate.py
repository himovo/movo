"""Prevent writes until a selected list resource is the opened detail object."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.enterprise_capabilities.browser.engine.operation_intent import is_final_commit_control
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .detail_progress import DetailTargetFingerprint, same_detail_resource


_INPUT_MUTATION_TOOLS = {
    "browser_fill",
    "browser_type_at",
    "browser_select",
    "browser_upload_file",
    "browser_paste_image",
}


@dataclass
class DetailWriteGate:
    """Latch a stable resource selection across ref churn and failed retries."""

    target: Optional[DetailTargetFingerprint] = None
    verified_url: str = ""
    mismatch_url: str = ""
    recovery_attempts: int = 0
    max_recovery_attempts: int = 2

    def arm(self, target: DetailTargetFingerprint) -> None:
        if not (target.target_url or target.content_context_id):
            return
        if self.target is not None and _same_target(self.target, target):
            return
        self.target = target
        self.verified_url = ""
        self.mismatch_url = ""
        self.recovery_attempts = 0

    def observe(self, *, current_url: str, detail_confirmed: bool) -> None:
        if self.target is None:
            return
        current = str(current_url or "").strip()
        if detail_confirmed:
            self.verified_url = current
            self.mismatch_url = ""
            return
        # Detail proof is transition-based. Ordinary fills/clicks on an
        # already verified page do not reproduce that transition, so retain
        # the proof while the resource URL itself is unchanged.
        if (
            current
            and self.verified_url
            and same_detail_resource(self.verified_url, current)
        ):
            self.mismatch_url = ""
            return
        self.verified_url = ""
        if (
            current
            and self.target.source_url
            and not same_detail_resource(self.target.source_url, current)
        ):
            self.mismatch_url = current
        elif current and self.target.source_url:
            self.mismatch_url = ""

    def blocker(self, decision: Decision, observation: Observation) -> str:
        if self.target is None or self.verified_url:
            return ""
        tool = str(decision.tool or "")
        target = _decision_target(decision, observation)
        unsafe = tool in _INPUT_MUTATION_TOOLS
        unsafe = unsafe or (
            tool == "browser_press"
            and str((decision.args or {}).get("key") or "").casefold()
            in {"enter", "numpadenter"}
            and bool(target.get("editable"))
            and not _is_search_target(target)
        )
        unsafe = unsafe or (
            tool in {"browser_click", "browser_click_at"}
            and bool(target)
            and is_final_commit_control(target)
        )
        if not unsafe:
            return ""
        return (
            "当前详情页尚未确认是刚才选择的业务对象，禁止填写、上传或提交；"
            "请先返回结果列表并按原对象身份重新定位。"
        )

    def suggest_recovery(self, observation: Observation) -> Optional[Decision]:
        if (
            self.target is None
            or self.verified_url
            or not self.mismatch_url
            or not self.target.source_url
            or self.recovery_attempts >= self.max_recovery_attempts
        ):
            return None
        if same_detail_resource(self.target.source_url, str(observation.url or "")):
            self.mismatch_url = ""
            return None
        self.recovery_attempts += 1
        return Decision(
            tool="browser_navigate",
            args={"url": self.target.source_url},
            rationale="return to the source list after the opened resource failed identity verification",
        )

    def clear(self) -> None:
        self.target = None
        self.verified_url = ""
        self.mismatch_url = ""
        self.recovery_attempts = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_url": self.target.target_url if self.target else "",
            "content_context_id": (
                self.target.content_context_id if self.target else ""
            ),
            "verified_url": self.verified_url,
            "mismatch_url": self.mismatch_url,
            "recovery_attempts": self.recovery_attempts,
        }


def _same_target(
    left: DetailTargetFingerprint,
    right: DetailTargetFingerprint,
) -> bool:
    if left.content_context_id and right.content_context_id:
        return left.content_context_id == right.content_context_id
    if left.target_url and right.target_url:
        return same_detail_resource(left.target_url, right.target_url)
    return False


def _decision_target(decision: Decision, observation: Observation) -> dict[str, Any]:
    ref = str((decision.args or {}).get("ref") or "").strip()
    if not ref:
        return {}
    return next(
        (
            item
            for item in list(observation.elements or [])
            if isinstance(item, dict) and str(item.get("ref") or "") == ref
        ),
        {},
    )


def _is_search_target(target: dict[str, Any]) -> bool:
    return bool(
        str(target.get("semanticPurpose") or "").casefold() == "search"
        or target.get("searchContext")
        or str(target.get("role") or "").casefold() == "searchbox"
    )


__all__ = ["DetailWriteGate"]
