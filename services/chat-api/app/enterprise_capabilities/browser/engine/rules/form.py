"""Form-submission rules.

Used by form_submission tasks and the CRUD Create sub-phase — any flow
that boils down to "fill fields, click submit, detect outcome".

Provides field discovery, required-field filtering, submit button
selection and post-submit outcome detection (validation error vs
success toast).
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import matchers as M
from .candidate_set import CandidateSet
from .tokens import (
    CONFIRM, REQUIRED_MARKERS, VALIDATION_ERROR, SUCCESS_TOAST,
)


def find_form_fields(
    elements: List[Dict[str, Any]], *, required_only: bool = False,
) -> List[Dict[str, Any]]:
    """Return every field element in order. When required_only=True,
    keep only those whose name / description carries a required marker
    (* / "required" / "必填" / pinyin)."""
    out: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict) or not M.is_field(el):
            continue
        if required_only and not M.has_any_token(el, REQUIRED_MARKERS):
            continue
        out.append(M.entry(el))
    return out


def pick_submit(elements: List[Dict[str, Any]]) -> CandidateSet:
    """Pick the confirm/submit button for the currently open form.

    If a dialog is open, we restrict to CONFIRM-in-dialog (crud.find_confirm
    already does this — callers may prefer that entry point). Otherwise
    we pick from the page-level CONFIRM buttons; when exactly one is
    present, auto-execute fires.
    """
    named: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict) or not M.is_interactive(el):
            continue
        if M.has_any_token(el, CONFIRM) and M.name_text(el):
            named.append(M.entry(el))
    if named:
        return CandidateSet(op="submit", tier=1, items=named[:4], reason="submit:named")
    return CandidateSet(op="submit", tier=3, items=[], reason="submit:no_match")


def detect_validation_error(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return alert-ish elements whose text suggests a client-side
    validation failure. Used post-submit to distinguish "form rejected
    my input" from "submit succeeded, page moved on"."""
    hits: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        role = str(el.get("role") or "").lower()
        if role in ("alert", "status"):
            hits.append(M.entry(el))
            continue
        if M.has_any_token(el, VALIDATION_ERROR):
            hits.append(M.entry(el))
    return hits


def detect_success_toast(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return elements announcing a successful submit (toast / status /
    notification with success wording). Used to verify submission
    succeeded without a URL change."""
    hits: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        if M.has_any_token(el, SUCCESS_TOAST):
            hits.append(M.entry(el))
    return hits


def suggest_field_value(field_el: Dict[str, Any], *, seed: str = "test") -> str:
    """Pick a reasonable test value for a form field.

    Strategy is intentionally blunt — the goal is "the form accepts
    this" not "this is business-realistic". Picks by role:
      textbox / searchbox  → "{seed}-{short-hash}"
      combobox             → "" (caller may need to click+pick instead)
      spinbutton           → "1"
    Rule can be overridden by the task context (for example a form phase
    wants a timestamp so the entity is locatable later)."""
    role = str(field_el.get("role") or "").lower()
    if role in ("textbox", "searchbox"):
        return f"{seed}"
    if role == "spinbutton":
        return "1"
    return ""
