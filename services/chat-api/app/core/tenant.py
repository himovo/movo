from __future__ import annotations

from typing import Any, Dict


DEFAULT_MAIN_ID = "default"


def resolve_main_id(value: Any = None) -> str:
    main_id = str(value or "").strip()
    return main_id or DEFAULT_MAIN_ID


def main_scope_filter(main_id: Any = None) -> Dict[str, Any]:
    resolved = resolve_main_id(main_id)
    if resolved == DEFAULT_MAIN_ID:
        return {
            "$or": [
                {"main_id": resolved},
                {"main_id": {"$exists": False}},
                {"main_id": ""},
                {"main_id": None},
            ]
        }
    return {"main_id": resolved}


def add_main_scope(query: Dict[str, Any], main_id: Any = None) -> Dict[str, Any]:
    base = dict(query or {})
    scope = main_scope_filter(main_id)
    if "$or" in scope:
        if not base:
            return scope
        return {"$and": [base, scope]}
    base.update(scope)
    return base
