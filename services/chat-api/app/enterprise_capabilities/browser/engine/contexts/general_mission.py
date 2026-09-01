"""Site-independent progress ledger for browser missions with side effects."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectReceipt
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .operation_cardinality import minimum_business_effects


_SEARCH_FIELD = re.compile(r"搜索|检索|查找|search|query|keyword", re.I)
_BUSINESS_EDITOR = re.compile(
    r"评论|回复|正文|标题|描述|消息|备注|comment|reply|content|title|description|message|note",
    re.I,
)


@dataclass
class SearchCycle:
    query: str
    state: str = "filled"
    result_url: str = ""
    detail_url: str = ""
    confirmed_effects: int = 0


@dataclass
class GeneralMissionLedger:
    enabled: bool
    search_enabled: bool = False
    minimum_effects: int = 1
    cycles: List[SearchCycle] = field(default_factory=list)
    pending_query: str = ""
    confirmed_effects: int = 0
    confirmed_contract_keys: set[str] = field(default_factory=set)

    @classmethod
    def compile(cls, goal: str, *, requires_search: bool, requires_commit: bool) -> "GeneralMissionLedger":
        enabled = requires_commit
        return cls(
            enabled=enabled,
            search_enabled=requires_search,
            minimum_effects=minimum_business_effects(goal, enabled=enabled),
        )

    def validate(self, decision: Decision, observation: Observation) -> Tuple[str, str]:
        if not self.enabled or not self.search_enabled or decision.tool not in {"browser_fill", "browser_type_at"}:
            return "allow", ""
        if not self.is_search_target(decision, observation):
            return "allow", ""
        value = str((decision.args or {}).get("value") or "").strip()
        current = self.current_cycle
        if current and current.state in {"submitted", "results_ready"} and value and value != current.query:
            return (
                "reject",
                f"关键词“{current.query}”的结果尚未打开并完成目标操作，不能切换到“{value}”。请先消费当前搜索结果。",
            )
        return "allow", ""

    def after_step(
        self,
        decision: Decision,
        observation: Observation,
        *,
        previous_url: str,
        search_target: bool = False,
        search_confirmed: bool = False,
        search_query: str = "",
        detail_confirmed: bool = False,
    ) -> None:
        if not self.enabled or not self.search_enabled:
            return
        tool = str(decision.tool or "")
        args = dict(decision.args or {})
        if tool in {"browser_fill", "browser_type_at"} and search_target:
            value = str(args.get("value") or "").strip()
            if value:
                self.pending_query = value
            return
        if search_confirmed:
            confirmed_query = self.pending_query or str(search_query or "").strip()
            if confirmed_query:
                self._submit(confirmed_query, str(observation.url or ""))
                self.pending_query = ""
            return
        current = self.current_cycle
        if not current or current.state not in {"submitted", "results_ready"}:
            return
        current_url = str(observation.url or "")
        if tool in {"browser_observe", "browser_wait_for"} and current.state == "submitted":
            current.state = "results_ready"
            current.result_url = current_url
        if detail_confirmed:
            current.state = "detail_opened"
            current.detail_url = current_url

    def record_effect(self, receipt: EffectReceipt, *, eligible: bool = True) -> bool:
        if not self.enabled or receipt.status != "confirmed_success" or not eligible:
            return False
        contract_key = str(
            receipt.business_action_id or receipt.contract_key or ""
        ).strip()
        if contract_key and contract_key in self.confirmed_contract_keys:
            return False
        if contract_key:
            self.confirmed_contract_keys.add(contract_key)
        self.confirmed_effects += 1
        current = self.current_cycle
        if current:
            current.confirmed_effects += 1
            current.state = "effect_confirmed"
        return True

    def reject_current_detail(self) -> None:
        """Return the current search cycle to its reusable result-list state."""
        current = self.current_cycle
        if current is None or current.confirmed_effects:
            return
        if current.state == "detail_opened":
            current.state = "results_ready"
            current.detail_url = ""

    def prepare_next_target(self) -> None:
        """Keep the search cycle but reopen its list for another business object."""
        current = self.current_cycle
        if current is None or self.complete:
            return
        current.state = "results_ready"
        current.detail_url = ""

    @property
    def current_cycle(self) -> Optional[SearchCycle]:
        return self.cycles[-1] if self.cycles else None

    @property
    def complete(self) -> bool:
        return not self.enabled or self.confirmed_effects >= self.minimum_effects

    def as_dict(self) -> Dict[str, Any]:
        return {
            "minimum_confirmed_operations": self.minimum_effects,
            "confirmed_operations": self.confirmed_effects,
            "remaining_confirmed_operations": max(
                0, self.minimum_effects - self.confirmed_effects,
            ),
            "confirmed_operation_keys": sorted(self.confirmed_contract_keys),
            "search_tracking_enabled": self.search_enabled,
            "current_query": self.current_cycle.query if self.current_cycle else self.pending_query,
            "search_cycles": [
                {
                    "query": cycle.query,
                    "state": cycle.state,
                    "result_url": cycle.result_url,
                    "detail_url": cycle.detail_url,
                    "confirmed_operations": cycle.confirmed_effects,
                }
                for cycle in self.cycles[-8:]
            ],
        }

    def _submit(self, query: str, url: str) -> None:
        current = self.current_cycle
        if current and current.query == query and current.state in {"submitted", "results_ready"}:
            current.result_url = url or current.result_url
            return
        self.cycles.append(SearchCycle(query=query, state="submitted", result_url=url))

    def is_search_target(self, decision: Decision, observation: Observation) -> bool:
        ref = str((decision.args or {}).get("ref") or "").strip()
        target = next(
            (item for item in observation.elements if isinstance(item, dict) and str(item.get("ref") or "") == ref),
            {},
        )
        if target.get("semanticPurpose") == "search" or target.get("searchContext"):
            return True
        label = " ".join(str(target.get(key) or "") for key in ("name", "placeholder", "scopeName"))
        if _SEARCH_FIELD.search(label):
            return True
        if not self.search_enabled or not target.get("editable"):
            return False
        if _BUSINESS_EDITOR.search(label):
            return False
        # Accessibility metadata is incomplete on many JS search surfaces.
        # During an explicit search mission, one unambiguous visible editable
        # is safe to treat as the query field. Multiple editors remain
        # ambiguous so a business form is never guessed to be search.
        candidates = [
            item for item in observation.elements
            if isinstance(item, dict)
            and item.get("editable") is True
            and item.get("visible") is not False
            and item.get("disabled") is not True
        ]
        return len(candidates) == 1 and candidates[0] is target
