"""Browser rule layer — deterministic entry discovery for every task type.

Three-layer architecture across the whole browser subsystem:
    observer  →  rules (this package)  →  LLM fallback

Each rule function returns a ``CandidateSet`` whose ``.action`` tells
the caller how to proceed:
    auto_execute  — exactly one candidate, synthesize a click
    llm_pick      — 2–8 candidates, surface in ledger
    fallback      — 0 or >8, let the planner figure it out

The package is organised so a context (form / scrape / general) imports
only what it needs; tokens are split per domain to keep blast radius
small when adding a new locale or synonym.
"""
from .candidate_set import (
    AUTO_EXECUTE, LLM_PICK, FALLBACK, SKIP,
    CandidateSet,
)
from . import matchers, page_kind, tokens, crud, form, scrape, nav, locator

__all__ = [
    "AUTO_EXECUTE", "LLM_PICK", "FALLBACK", "SKIP",
    "CandidateSet",
    "matchers", "page_kind", "tokens",
    "crud", "form", "scrape", "nav", "locator",
]
