from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord

from .contracts import CachedParameterBinding, CachedWorkflowStep
from .page_state import same_url_shape
from .replay_evidence import cached_target_is_ready


AUTH_BLOCKING_STATES = frozenset({
    "required", "registration_required", "authenticating", "failed",
})


def auth_state(observation: Observation | None) -> str:
    payload = observation.auth if observation is not None else None
    return str((payload or {}).get("state") or "unknown").strip().casefold()


def recorded_precondition_category(record: StepRecord) -> str:
    """Classify environment prerequisites from observed state transitions."""

    before = auth_state(record.decision_observation)
    after = auth_state(record.observation)
    if before in AUTH_BLOCKING_STATES:
        return "authentication"
    return ""


def has_runtime_authentication(requirements: Iterable[Mapping[str, Any]]) -> bool:
    return any(
        str(item.get("category") or "").casefold() == "authentication"
        for item in requirements
    )


def authentication_satisfied(observation: Observation) -> bool:
    return auth_state(observation) == "authenticated"


def authentication_blocked(observation: Observation) -> bool:
    return auth_state(observation) in AUTH_BLOCKING_STATES


def realign_after_precondition(
    steps: tuple[CachedWorkflowStep, ...],
    *,
    current_index: int,
    observation: Observation,
    resolve: Callable[[CachedParameterBinding], object | None],
) -> int:
    """Find the first forward business step compatible with the live page."""

    start = max(0, int(current_index))
    for index in range(start, len(steps)):
        step = steps[index]
        if step.execution_kind == "runtime_precondition":
            continue
        if step.source_url_shape and same_url_shape(observation.url, step.source_url_shape):
            return index
        if cached_target_is_ready(step, observation, resolve):
            return index
    return start


@dataclass(frozen=True)
class PreconditionEvaluation:
    index: int
    decision: Decision | None = None


class RuntimePreconditionGate:
    """Request-scoped prerequisite state kept outside the replay driver."""

    def __init__(self, requirements: Iterable[Mapping[str, Any]], *, lang: str) -> None:
        self.requirements = tuple(dict(item) for item in requirements)
        self.lang = str(lang or "zh")
        self.completed: set[str] = set()
        self.resume_requested = False

    def evaluate(
        self,
        steps: tuple[CachedWorkflowStep, ...],
        *,
        index: int,
        observation: Observation,
        resolve: Callable[[CachedParameterBinding], object | None],
    ) -> PreconditionEvaluation:
        current_index = max(0, int(index))
        if (
            self.resume_requested
            and self.requirements
            and "runtime" not in self.completed
            and not authentication_blocked(observation)
        ):
            aligned = realign_after_precondition(
                steps, current_index=current_index,
                observation=observation, resolve=resolve,
            )
            current_index = max(current_index, aligned)
            self.completed.update({"runtime", "authentication"})
            self.resume_requested = False

        while current_index < len(steps):
            current = steps[current_index]
            if current.execution_kind != "runtime_precondition":
                break
            if current.precondition_category not in self.completed:
                break
            current_index += 1

        step = steps[current_index] if current_index < len(steps) else None
        step_auth = bool(
            step is not None
            and step.execution_kind == "runtime_precondition"
            and step.precondition_category == "authentication"
            and "authentication" not in self.completed
        )
        runtime_auth = (
            "authentication" not in self.completed
            and "runtime" not in self.completed
            and has_runtime_authentication(self.requirements)
        )
        if not step_auth and not runtime_auth:
            return PreconditionEvaluation(current_index)
        if step is not None and current_index == 0 and step.tool in {
            "browser_navigate", "browser_tab_new",
        }:
            return PreconditionEvaluation(current_index)

        search_from = current_index + (1 if step_auth else 0)
        aligned = realign_after_precondition(
            steps, current_index=search_from,
            observation=observation, resolve=resolve,
        )
        progressed = aligned > current_index
        completed_by_human = self.resume_requested and not authentication_blocked(observation)
        if authentication_satisfied(observation) or progressed or completed_by_human:
            self.completed.update({"runtime", "authentication"})
            self.resume_requested = False
            return PreconditionEvaluation(aligned if progressed else search_from)
        return PreconditionEvaluation(current_index, self.pause(authentication=True))

    def pause_for_unresolved(self) -> Decision | None:
        if not self.requirements or "runtime" in self.completed:
            return None
        return self.pause(authentication=False)

    def pause(self, *, authentication: bool) -> Decision:
        if self.lang == "zh":
            question = (
                "当前流程需要先完成登录或身份验证。请在浏览器中完成后点击继续。"
                if authentication else
                "当前流程遇到需要人工完成的运行前置条件。请处理后点击继续。"
            )
        else:
            question = (
                "This workflow requires authentication. Complete it in the browser, then continue."
                if authentication else
                "This workflow has a runtime prerequisite. Complete it, then continue."
            )
        return Decision(
            tool="browser_ask_user",
            args={"category": "login" if authentication else "browser", "question": question},
            rationale=(
                "[learned_workflow] runtime authentication precondition"
                if authentication else "[learned_workflow] runtime precondition"
            ),
        )

    def apply_resume_signal(self, signal: Mapping[str, Any]) -> None:
        outcome = str(signal.get("human_outcome") or "").strip().casefold()
        if outcome in {"completed", "confirmed", "success"}:
            self.resume_requested = True

    def export(self) -> dict[str, Any]:
        return {
            "requirements": [dict(item) for item in self.requirements],
            "completed": sorted(self.completed),
            "resume_requested": self.resume_requested,
        }

    def restore(self, state: Mapping[str, Any]) -> None:
        requirements = state.get("requirements")
        if isinstance(requirements, list):
            self.requirements = tuple(
                dict(item) for item in requirements if isinstance(item, dict)
            )
        self.completed = {
            str(item) for item in list(state.get("completed") or []) if str(item)
        }
        self.resume_requested = bool(state.get("resume_requested", self.resume_requested))


__all__ = [
    "AUTH_BLOCKING_STATES",
    "auth_state",
    "authentication_blocked",
    "authentication_satisfied",
    "has_runtime_authentication",
    "realign_after_precondition",
    "recorded_precondition_category",
    "PreconditionEvaluation",
    "RuntimePreconditionGate",
]
