from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine.state_store import SubAgentRuntimeRecord, SubAgentStateStore
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord


class BrowserExecutionCheckpoint(BaseModel):
    version: int = 3
    phase: str = "running"
    next_step: int = 1
    visible_tool_step: int = 0
    current_url: str = ""
    current_title: str = ""
    current_revision: str = ""
    history: List[Dict[str, Any]] = Field(default_factory=list)
    authenticated_domains: List[str] = Field(default_factory=list)
    last_safe_url_by_domain: Dict[str, str] = Field(default_factory=dict)
    login_recovery_failures: Dict[str, int] = Field(default_factory=dict)
    wait_for_text_calls: Dict[str, int] = Field(default_factory=dict)
    wait_for_text_refs: Dict[str, str] = Field(default_factory=dict)
    last_navigate_target: str = ""
    consecutive_failures: int = 0
    soft_recovery_used: bool = False
    no_progress_streak: int = 0
    last_progress_signature: Optional[List[Any]] = None
    driver_state: Dict[str, Any] = Field(default_factory=dict)
    context_state: Dict[str, Any] = Field(default_factory=dict)
    browser_runtime_state: Dict[str, Any] = Field(default_factory=dict)
    # Replay-safe semantic actions are persisted separately from the compact
    # planner history.  They retain stable locators across auth/human pauses.
    learning_trace: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def capture(
        cls,
        *,
        phase: str,
        next_step: int,
        visible_tool_step: int,
        observation: Observation,
        history: List[StepRecord],
        authenticated_domains: Set[str],
        last_safe_url_by_domain: Dict[str, str],
        login_recovery_failures: Dict[str, int],
        wait_for_text_calls: Dict[str, int],
        wait_for_text_refs: Optional[Dict[str, str]] = None,
        last_navigate_target: Optional[str] = None,
        consecutive_failures: int = 0,
        soft_recovery_used: bool = False,
        no_progress_streak: int = 0,
        last_progress_signature: Optional[tuple[Any, ...]] = None,
        driver_state: Optional[Dict[str, Any]] = None,
        context_state: Optional[Dict[str, Any]] = None,
        browser_runtime_state: Optional[Dict[str, Any]] = None,
        learning_trace: Optional[Dict[str, Any]] = None,
    ) -> "BrowserExecutionCheckpoint":
        compact_history: List[Dict[str, Any]] = []
        for record in history[-12:]:
            compact_history.append({
                "url": str(record.observation.url or ""),
                "title": str(record.observation.title or ""),
                "tool": str(record.decision.tool or ""),
                "args": _stable_args(record.decision.args),
                "rationale": str(record.decision.rationale or "")[:500],
                "ok": bool(record.ok),
                "error": str(record.error or "")[:1000],
                "result_digest": str(record.result_digest or "")[:6000],
            })
        return cls(
            phase=phase,
            next_step=max(1, int(next_step)),
            visible_tool_step=max(0, int(visible_tool_step)),
            current_url=str(observation.url or ""),
            current_title=str(observation.title or ""),
            current_revision=str(observation.revision or ""),
            history=compact_history,
            authenticated_domains=sorted(str(item) for item in authenticated_domains if str(item)),
            last_safe_url_by_domain=dict(last_safe_url_by_domain or {}),
            login_recovery_failures={str(k): int(v) for k, v in dict(login_recovery_failures or {}).items()},
            wait_for_text_calls={str(k): int(v) for k, v in dict(wait_for_text_calls or {}).items()},
            wait_for_text_refs={str(k): str(v) for k, v in dict(wait_for_text_refs or {}).items() if str(v)},
            last_navigate_target=str(last_navigate_target or ""),
            consecutive_failures=max(0, int(consecutive_failures)),
            soft_recovery_used=bool(soft_recovery_used),
            no_progress_streak=max(0, int(no_progress_streak)),
            last_progress_signature=list(last_progress_signature) if last_progress_signature else None,
            driver_state=dict(driver_state or {}),
            context_state=dict(context_state or {}),
            browser_runtime_state=dict(browser_runtime_state or {}),
            learning_trace=dict(learning_trace or {}),
        )

    def restore_history(self) -> List[StepRecord]:
        records: List[StepRecord] = []
        for item in self.history:
            records.append(StepRecord(
                observation=Observation(
                    url=str(item.get("url") or ""),
                    title=str(item.get("title") or ""),
                    elements=[],
                ),
                decision=Decision(
                    tool=str(item.get("tool") or ""),
                    args=dict(item.get("args") or {}),
                    rationale=str(item.get("rationale") or ""),
                ),
                ok=bool(item.get("ok")),
                error=str(item.get("error") or "") or None,
                result_digest=str(item.get("result_digest") or "") or None,
            ))
        return records


class BrowserCheckpointSession:
    def __init__(
        self,
        *,
        store: SubAgentStateStore,
        task_id: str,
        run_id: str,
        node: CapabilityTask,
    ) -> None:
        self.store = store
        self.task_id = task_id
        self.run_id = run_id
        self.node = node
        self.record: Optional[SubAgentRuntimeRecord] = None
        self.checkpoint: Optional[BrowserExecutionCheckpoint] = None

    @property
    def subagent_id(self) -> str:
        return self.record.subagent_id if self.record else ""

    async def open(self) -> Optional[BrowserExecutionCheckpoint]:
        existing = await self.store.get_by_node(self.task_id, self.node.node_id, run_id=self.run_id)
        resumable = existing and existing.status in {"pending", "running", "suspended", "suspended_waiting_approval"}
        if resumable:
            self.record = existing
            self.checkpoint = self._decode(existing.checkpoint_ref)
            existing.status = "running"
            existing.last_error = ""
            self.record = await self.store.upsert(existing)
            return self.checkpoint
        self.record = await self.store.upsert(SubAgentRuntimeRecord(
            subagent_id=f"sa_{uuid.uuid4().hex[:12]}",
            parent_task_id=self.task_id,
            run_id=self.run_id,
            node_id=self.node.node_id,
            assigned_agent=self.node.assigned_agent,
            skill_name=str((self.node.meta or {}).get("target_skill") or "browser_task"),
            status="running",
        ))
        return None

    async def save(self, checkpoint: BrowserExecutionCheckpoint, *, status: str = "running") -> None:
        if not self.record:
            raise RuntimeError("browser checkpoint session is not open")
        self.checkpoint = checkpoint
        self.record.checkpoint_ref = checkpoint.model_dump_json()
        self.record.step_seq = max(0, checkpoint.next_step - 1)
        self.record.skill_step = self.record.step_seq
        self.record.status = status
        self.record = await self.store.upsert(self.record)

    async def capture_and_save(
        self,
        *,
        phase: str,
        next_step: int,
        visible_tool_step: int,
        observation: Observation,
        history: List[StepRecord],
        authenticated_domains: Set[str],
        last_safe_url_by_domain: Dict[str, str],
        login_recovery_failures: Dict[str, int],
        wait_for_text_calls: Dict[str, int],
        wait_for_text_refs: Optional[Dict[str, str]] = None,
        last_navigate_target: Optional[str] = None,
        consecutive_failures: int = 0,
        soft_recovery_used: bool = False,
        no_progress_streak: int = 0,
        last_progress_signature: Optional[tuple[Any, ...]] = None,
        driver_state: Optional[Dict[str, Any]] = None,
        context_state: Optional[Dict[str, Any]] = None,
        browser_runtime_state: Optional[Dict[str, Any]] = None,
        learning_trace: Optional[Dict[str, Any]] = None,
        status: str = "running",
    ) -> BrowserExecutionCheckpoint:
        checkpoint = BrowserExecutionCheckpoint.capture(
            phase=phase,
            next_step=next_step,
            visible_tool_step=visible_tool_step,
            observation=observation,
            history=history,
            authenticated_domains=authenticated_domains,
            last_safe_url_by_domain=last_safe_url_by_domain,
            login_recovery_failures=login_recovery_failures,
            wait_for_text_calls=wait_for_text_calls,
            wait_for_text_refs=wait_for_text_refs,
            last_navigate_target=last_navigate_target,
            consecutive_failures=consecutive_failures,
            soft_recovery_used=soft_recovery_used,
            no_progress_streak=no_progress_streak,
            last_progress_signature=last_progress_signature,
            driver_state=driver_state,
            context_state=context_state,
            browser_runtime_state=browser_runtime_state,
            learning_trace=learning_trace,
        )
        await self.save(checkpoint, status=status)
        return checkpoint

    async def finish(self, status: str) -> None:
        if not self.record:
            return
        mapped = {
            "suspended_waiting_approval": "suspended_waiting_approval",
            "succeeded": "succeeded",
            "failed_retryable": "failed_retryable",
            "failed_terminal": "failed_terminal",
        }.get(status, status or self.record.status)
        self.record.status = mapped
        self.record = await self.store.upsert(self.record)

    @staticmethod
    def _decode(payload: str) -> Optional[BrowserExecutionCheckpoint]:
        if not str(payload or "").strip():
            return None
        try:
            return BrowserExecutionCheckpoint.model_validate_json(payload)
        except Exception:
            return None


def _stable_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Drop transient DOM refs; restored steps are evidence, not replay commands."""
    safe = dict(args or {})
    safe.pop("ref", None)
    try:
        return json.loads(json.dumps(safe, ensure_ascii=False, default=str))
    except Exception:
        return {}
