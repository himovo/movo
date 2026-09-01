from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


DEFAULT_ELEMENT_BUDGET_CHARS = 24_000
_FORM_ROLES = {"textbox", "searchbox", "combobox", "listbox", "checkbox", "radio", "switch", "slider", "spinbutton"}
_ACTION_ROLES = {"button", "menuitem", "tab", "option", "treeitem"}
_TEXT_LIMITS = {
    "name": 220,
    "text": 280,
    "description": 220,
    "placeholder": 160,
    "value": 320,
    "href": 600,
    "accept": 160,
}


def compact_observation(
    obs: Any,
    *,
    goal: str = "",
    target: Optional[str] = None,
    pinned_refs: Optional[Iterable[str]] = None,
    element_budget_chars: int = DEFAULT_ELEMENT_BUDGET_CHARS,
) -> Dict[str, Any]:
    elements = [item for item in list(getattr(obs, "elements", None) or []) if isinstance(item, dict)]
    pinned = {str(ref) for ref in (pinned_refs or []) if str(ref)}
    target_matches = find_target_matches(elements, target or "") if target else []
    pinned.update(str(item.get("ref") or "") for item in target_matches)

    ranked = sorted(
        enumerate(elements),
        key=lambda pair: (-_element_score(pair[1], goal=goal, target=target or "", pinned_refs=pinned), pair[0]),
    )
    selected: List[Dict[str, Any]] = []
    selected_refs: Set[str] = set()
    seen_link_destinations: Set[tuple[str, str, str]] = set()
    used_chars = 2
    budget = max(2_000, int(element_budget_chars))

    for _index, element in ranked:
        compact = _compact_element(element)
        ref = str(compact.get("ref") or "")
        if not ref or ref in selected_refs:
            continue
        if _is_duplicate_link(compact, seen_link_destinations):
            continue
        encoded_size = len(json.dumps(compact, ensure_ascii=False, separators=(",", ":"))) + 1
        required = (
            ref in pinned
            and element.get("inViewport") is not False
            and element.get("hitTestable") is not False
        )
        if not required and used_chars + encoded_size > budget:
            continue
        selected.append(compact)
        selected_refs.add(ref)
        used_chars += encoded_size

    out: Dict[str, Any] = {
        "url": str(getattr(obs, "url", "") or ""),
        "title": str(getattr(obs, "title", "") or ""),
        "elements": selected,
        "element_compaction": {
            "total": len(elements),
            "included": len(selected),
            "omitted": max(0, len(elements) - len(selected)),
            "budget_chars": budget,
        },
    }
    if target_matches:
        out["target_matches"] = target_matches
    viewport = getattr(obs, "viewport", None)
    if isinstance(viewport, dict) and viewport:
        out["viewport"] = viewport
    screenshot_metadata = getattr(obs, "screenshot_metadata", None)
    if isinstance(screenshot_metadata, dict) and screenshot_metadata:
        out["screenshot_metadata"] = screenshot_metadata
    effects = list(getattr(obs, "effects", None) or [])
    if effects:
        out["recent_effects"] = effects[-30:]
    text = str(getattr(obs, "page_text", "") or "").strip()
    if text:
        out["page_text"] = (
            '<observed_page_text source="rendered_dom" trust="low">\n'
            + text[:5000]
            + "\n</observed_page_text>"
        )
    _copy_clean_dom(out, getattr(obs, "clean_dom", None))
    dom_diff = getattr(obs, "dom_diff", None)
    if isinstance(dom_diff, dict) and dom_diff:
        out["dom_diff"] = dom_diff
    return out


def find_target_matches(elements: Sequence[Dict[str, Any]], target: str) -> List[Dict[str, Any]]:
    for term in _target_search_terms(target):
        needle = term.lower()
        hits: List[Dict[str, Any]] = []
        for element in elements:
            if not isinstance(element, dict):
                continue
            searchable = " ".join(
                str(element.get(key) or "").lower()
                for key in ("name", "text", "description", "placeholder")
            )
            if needle not in searchable:
                continue
            hits.append({
                "ref": element.get("ref"),
                "role": element.get("role"),
                "name": element.get("name"),
                "href": element.get("href") or "",
                "disabled": bool(element.get("disabled")),
                "frameDepth": element.get("frameDepth", 0),
                "matched_by": term,
            })
            if len(hits) >= 8:
                break
        if hits:
            return hits
    return []


def _element_score(element: Dict[str, Any], *, goal: str, target: str, pinned_refs: Set[str]) -> int:
    ref = str(element.get("ref") or "")
    role = str(element.get("role") or "").lower()
    text = _searchable_text(element)
    score = 1
    if ref in pinned_refs and element.get("inViewport") is not False and element.get("hitTestable") is not False:
        score += 10_000
    if element.get("inViewport") is False:
        score -= 1_500
    if element.get("hitTestable") is False:
        score -= 4_000
    elif element.get("hitTestable") is True:
        score += 120
    if target and _text_related(text, target):
        score += 3_000
    if goal:
        score += min(900, _bigram_overlap(text, goal) * 45)
        if text and len(text) <= 120 and text.lower() in goal.lower():
            score += 700
    if role in _FORM_ROLES or bool(element.get("editable")):
        score += 520
    elif role in _ACTION_ROLES:
        score += 340
    elif role == "link":
        score += 260
    if element.get("required"):
        score += 220
    if str(element.get("href") or ""):
        score += 210
    if element.get("visible", True):
        score += 80
    if element.get("disabled"):
        score -= 60
    if element.get("name") or element.get("text") or element.get("placeholder"):
        score += 40
    return score


def _compact_element(element: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "ref", "role", "name", "text", "description", "tag", "type", "placeholder", "value", "href",
        "disabled", "editable", "visible", "required", "multiple", "accept", "options",
        "contentEditable", "multiline", "x", "y", "width", "height", "inViewport", "hitTestable",
        "frameDepth", "labelSource", "searchContext", "semanticPurpose",
        "scopeId", "scopeRole", "scopeName", "scopeKind", "scopeLockable",
        "hasPopup", "expanded", "controlsId", "controlledSurfaceId",
    )
    out: Dict[str, Any] = {}
    for key in keys:
        value = element.get(key)
        if value in (None, "", [], {}) or (
            value is False and key not in {"inViewport", "hitTestable", "expanded"}
        ):
            continue
        if key in _TEXT_LIMITS:
            value = str(value)[:_TEXT_LIMITS[key]]
        elif key == "options" and isinstance(value, list):
            value = [str(item)[:120] for item in value[:30]]
        out[key] = value
    return out


def _is_duplicate_link(element: Dict[str, Any], seen: Set[tuple[str, str, str]]) -> bool:
    if str(element.get("role") or "").lower() != "link" or not element.get("href"):
        return False
    key = (
        str(element.get("name") or element.get("text") or "").strip().lower(),
        str(element.get("href") or "").strip(),
        str(element.get("frameDepth") or 0),
    )
    if key in seen:
        return True
    seen.add(key)
    return False


def _searchable_text(element: Dict[str, Any]) -> str:
    return " ".join(
        str(element.get(key) or "")
        for key in ("name", "text", "description", "placeholder", "href", "semanticPurpose")
    ).strip()


def _text_related(left: str, right: str) -> bool:
    lhs = left.lower().strip()
    rhs = right.lower().strip()
    return bool(lhs and rhs and (lhs in rhs or rhs in lhs or _bigram_overlap(lhs, rhs) >= 2))


def _bigram_overlap(left: str, right: str) -> int:
    def grams(value: str) -> Set[str]:
        normalized = re.sub(r"\s+", "", value.lower())
        return {normalized[index:index + 2] for index in range(max(0, len(normalized) - 1))}
    return len(grams(left) & grams(right))


def _target_search_terms(target: str) -> List[str]:
    full = str(target or "").strip()
    if not full:
        return []
    terms = [full]
    for separator in ("-", "_", "·", "—", " "):
        if separator not in full:
            continue
        tail = full.rsplit(separator, 1)[-1].strip()
        if 2 <= len(tail) <= 40 and tail not in terms:
            terms.append(tail)
            break
    alnum = re.findall(r"[A-Za-z0-9]{3,}", full)
    if alnum:
        longest = max(alnum, key=len)
        if longest not in terms:
            terms.append(longest)
    return terms


def _copy_clean_dom(out: Dict[str, Any], clean_dom: Any) -> None:
    if not isinstance(clean_dom, dict) or not clean_dom:
        return
    compact: Dict[str, Any] = {}
    if isinstance(clean_dom.get("summary"), dict) and clean_dom["summary"]:
        compact["summary"] = clean_dom["summary"]
    if isinstance(clean_dom.get("containers"), list) and clean_dom["containers"]:
        compact["containers"] = clean_dom["containers"][:4]
    if isinstance(clean_dom.get("cues"), list) and clean_dom["cues"]:
        compact["cues"] = clean_dom["cues"][:12]
    if compact:
        out["clean_dom"] = compact
