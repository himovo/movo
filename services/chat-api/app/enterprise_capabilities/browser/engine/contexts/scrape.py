"""Scrape / extraction context — walk through a paginated list.

State machine:
    phase = extracting   → LLM decides what data to pull from current page
    phase = paginating   → rules auto-click Next / Load More if available
    phase = done         → pagination ended, browser_done allowed

The data-extraction step itself is given to the LLM (rules can't know
which columns matter). The context handles only navigation and
end-of-list detection.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine import rules
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision, Observation, StepRecord,
)

from .base import BrowserTaskContext
from .null import NullContext


def _signals_scrape_mode(node: CapabilityTask, output_spec: Dict[str, Any]) -> bool:
    cts = output_spec.get("content_task_spec") if isinstance(output_spec, dict) else None
    if not isinstance(cts, dict):
        return False
    schema = cts.get("schema") if isinstance(cts.get("schema"), dict) else {}
    return str(schema.get("category") or "").strip().lower() == "scrape_extract"


class ScrapeContext(BrowserTaskContext):
    active: bool = True

    PHASE_EXTRACTING = "extracting"
    PHASE_PAGINATING = "paginating"
    PHASE_DONE = "done"

    # Hard cap — prevents runaway pagination on sites that never finish.
    MAX_PAGES = 50

    def __init__(self, *, lang: str, node: CapabilityTask, goal: str,
                 original_user_request: str) -> None:
        self.lang = lang
        self.node = node
        self.goal = goal
        self.original_user_request = original_user_request

        self.phase = self.PHASE_EXTRACTING
        self.step_counter = 0
        self.pages_seen = 0
        self.last_row_fingerprint: Optional[int] = None
        self.end_reason: str = ""

    @classmethod
    def maybe_init(
        cls, *, node: CapabilityTask, output_spec: Dict[str, Any],
        original_user_request: str, goal: str, lang: str,
    ) -> BrowserTaskContext:
        if _signals_scrape_mode(node, output_spec):
            return cls(
                lang=lang, node=node, goal=goal,
                original_user_request=original_user_request,
            )
        return NullContext()

    # ─── Phase tracking ────────────────────────────────────────────
    def after_step(
        self, decision: Decision, result: Any, ok: bool, current_obs: Observation,
        error: Optional[str] = None,
    ) -> None:
        self.step_counter += 1
        if not ok:
            return
        elements = list(getattr(current_obs, "elements", None) or [])
        tool = str(getattr(decision, "tool", "") or "")

        # First page or a freshly-loaded page → record fingerprint
        if tool in ("browser_navigate", "browser_click"):
            end = rules.scrape.detect_list_end(
                elements, prev_row_fingerprint=self.last_row_fingerprint,
            )
            # Update fingerprint for next comparison
            self.last_row_fingerprint = rules.scrape._row_fingerprint(elements)
            # Count a page as "seen" when we land on one with rows
            if rules.scrape.extract_row_candidates(elements):
                self.pages_seen += 1
            if end["ended"] or self.pages_seen >= self.MAX_PAGES:
                self.phase = self.PHASE_DONE
                self.end_reason = end["reason"] or "max_pages_reached"

    # ─── Rules layer ───────────────────────────────────────────────
    def suggest_next_action(self, current_obs: Observation) -> Optional[Decision]:
        if self.phase == self.PHASE_DONE:
            return None
        elements = list(getattr(current_obs, "elements", None) or [])
        if not elements:
            return None
        nxt = rules.scrape.find_next_page(elements)
        if nxt.action == rules.AUTO_EXECUTE:
            el = nxt.items[0]
            return Decision(
                tool="browser_click", args={"ref": el["ref"]},
                rationale=f"rule auto-execute: next page ({nxt.reason})",
            )
        return None

    # ─── State ledger ──────────────────────────────────────────────
    def build_state_ledger(
        self, current_obs: Optional[Observation] = None,
    ) -> Optional[Dict[str, Any]]:
        ledger: Dict[str, Any] = {
            "phase": f"scrape_{self.phase}",
            "phase_goal": self._phase_goal(),
            "budget": {
                "step_counter": self.step_counter,
                "pages_seen": self.pages_seen,
                "max_pages": self.MAX_PAGES,
            },
        }
        if self.end_reason:
            ledger["end_reason"] = self.end_reason
        if current_obs is not None:
            elements = list(getattr(current_obs, "elements", None) or [])
            rows = rules.scrape.extract_row_candidates(elements)
            if rows:
                ledger["row_candidates"] = rows[:12]
        return ledger

    def _phase_goal(self) -> str:
        zh = str(self.lang or "").startswith("zh")
        if self.phase == self.PHASE_EXTRACTING:
            return "从当前页的 row_candidates 里抽取需要的数据字段" if zh else \
                   "extract the requested fields from row_candidates on the current page"
        if self.phase == self.PHASE_PAGINATING:
            return "翻到下一页（系统会自动点击）" if zh else "move to next page (system auto-clicks)"
        return "已抽完，可 browser_done" if zh else "scraping done — browser_done allowed"

    # ─── Termination ───────────────────────────────────────────────
    def ready_to_done(self) -> bool:
        return self.phase == self.PHASE_DONE

    def done_blocked_hint(self, current_obs: Observation) -> StepRecord:
        zh = str(self.lang or "").startswith("zh")
        reason = (
            f"抓取任务未完成，pages_seen={self.pages_seen}；继续翻页或抽取。"
            if zh else
            f"Scrape not done (pages_seen={self.pages_seen}); keep paginating/extracting."
        )
        return StepRecord(
            observation=current_obs,
            decision=Decision(tool="__scrape_done_blocked__", args={},
                              rationale="scrape gate: premature browser_done"),
            ok=False, error=reason, result_digest="",
        )
