"""Structural page classification.

Returns one of:
  list              — multiple list-like rows / grid cells
  detail_of_target  — target entity's name is prominent (title region)
  detail_other      — detail-like but doesn't carry our target
  form              — textbox-heavy surface with few buttons
  unknown

All signals come from ARIA roles and element positions in the observed
sequence. No site-specific class names.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def infer(
    elements: List[Dict[str, Any]],
    page_text: str = "",
    target: str = "",
    title: str = "",
) -> str:
    roles = []
    names = []
    descriptions = []
    for e in elements or []:
        if not isinstance(e, dict):
            continue
        roles.append(str(e.get("role") or "").lower())
        names.append(str(e.get("name") or ""))
        descriptions.append(str(e.get("description") or ""))

    n_rows = sum(1 for r in roles if r in ("row", "listitem", "gridcell"))
    n_textbox = sum(1 for r in roles if r in ("textbox", "combobox", "searchbox"))
    n_buttons = sum(1 for r in roles if r == "button")

    target_prominent = False
    if target:
        target_terms = [target.strip()]
        target_terms.extend(
            t for t in re.split(r"[\s_:/|\\-]+", target)
            if len(t.strip()) >= 6
        )
        surface = " | ".join(
            [str(title or "")] + names[:20] + descriptions[:20]
        ) + " || " + (page_text or "")[:1200]
        surface = surface.lower()
        for term in target_terms:
            needle = term.strip().lower()
            if needle and needle in surface:
                target_prominent = True
                break

    if n_rows >= 3:
        return "list"
    if target_prominent:
        return "detail_of_target"
    if n_textbox >= 3 and n_textbox >= n_buttons:
        return "form"
    if 0 < n_buttons <= 5 and n_rows == 0:
        return "detail_other"
    return "unknown"
