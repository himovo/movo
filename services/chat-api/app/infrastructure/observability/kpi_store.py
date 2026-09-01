from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime
from typing import Dict


class RuntimeKPIStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._counters: Dict[str, float] = {
            "checkpoint_resume_success_rate": 0.0,
            "mean_steps_to_success": 0.0,
            "mean_retries_per_step": 0.0,
            "tool_denied_rate": 0.0,
            "suspend_to_resume_conversion": 0.0,
            "browser_action_failure_top_locators": 0.0,
            "exactly_once_reuse_rate": 0.0,
            "_tool_total": 0.0,
            "_tool_denied": 0.0,
            "_reuse_hit": 0.0,
            "_suspend_total": 0.0,
            "_resume_total": 0.0,
            "_success_steps": 0.0,
            "_success_runs": 0.0,
            "_checkpoint_resume_total": 0.0,
            "_checkpoint_resume_ok": 0.0,
            "_retry_total": 0.0,
            "_retry_steps": 0.0,
        }
        self._updated_at = datetime.utcnow()

    async def incr(self, key: str, value: float = 1.0) -> None:
        async with self._lock:
            self._counters[key] = float(self._counters.get(key, 0.0) + value)
            self._recompute()

    async def set_value(self, key: str, value: float) -> None:
        async with self._lock:
            self._counters[key] = float(value)
            self._recompute()

    async def snapshot(self) -> Dict[str, float]:
        async with self._lock:
            data = deepcopy(self._counters)
            data["updated_at"] = self._updated_at.timestamp()
            return data

    def _recompute(self) -> None:
        tool_total = max(1.0, float(self._counters.get("_tool_total", 0.0)))
        self._counters["tool_denied_rate"] = float(self._counters.get("_tool_denied", 0.0)) / tool_total
        self._counters["exactly_once_reuse_rate"] = float(self._counters.get("_reuse_hit", 0.0)) / tool_total
        suspend_total = max(1.0, float(self._counters.get("_suspend_total", 0.0)))
        self._counters["suspend_to_resume_conversion"] = float(self._counters.get("_resume_total", 0.0)) / suspend_total
        success_runs = max(1.0, float(self._counters.get("_success_runs", 0.0)))
        self._counters["mean_steps_to_success"] = float(self._counters.get("_success_steps", 0.0)) / success_runs
        resume_total = max(1.0, float(self._counters.get("_checkpoint_resume_total", 0.0)))
        self._counters["checkpoint_resume_success_rate"] = float(self._counters.get("_checkpoint_resume_ok", 0.0)) / resume_total
        retry_steps = max(1.0, float(self._counters.get("_retry_steps", 0.0)))
        self._counters["mean_retries_per_step"] = float(self._counters.get("_retry_total", 0.0)) / retry_steps
        self._updated_at = datetime.utcnow()
