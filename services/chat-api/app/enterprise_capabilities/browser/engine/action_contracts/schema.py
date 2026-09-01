"""Shared dataclasses for the browser action-contract taxonomy.

Each concrete capability (browser.read, browser.navigate, ...) lives in
its own ``_<name>.py`` module and exports a single ``BrowserActionSpec``
instance. The module set is intentionally small and uniform so the
planner LLM can pick cleanly and the executor can validate structurally.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple


@dataclass
class ContractResult:
    """Outcome of validating an LLM's browser_done.data against a spec.

    ``reason`` is user-/LLM-facing text explaining why the contract
    wasn't met; the executor feeds it back into the planner's next turn
    so the LLM can self-correct (e.g. "no observed value for result —
    keep reading the page or fail explicitly").
    """

    ok: bool
    reason: str = ""
    missing: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class BrowserActionSpec:
    """Declarative contract for one browser capability.

    ``validate`` is a pure function ``data -> ContractResult``. No
    keyword matching — only structural / shape / emptiness checks on
    the data dict the LLM returns in browser_done.args.data.
    """

    capability_id: str                  # e.g. "browser.read"
    name_zh: str                        # display name
    name_en: str
    description_zh: str                 # shown to planner LLM so it picks
    description_en: str                 # the right capability per step
    produces: Tuple[str, ...]           # artifact keys expected in data
    data_schema_hint_zh: str            # shown to browser LLM so it knows
    data_schema_hint_en: str            # what structure to emit on done
    validate: Callable[[Dict[str, Any]], ContractResult]
