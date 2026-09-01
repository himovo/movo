from __future__ import annotations

from typing import Any, Dict, Iterable


RUN_ORIGINAL_USER_REQUEST = "run_original_user_request"


def bind_run_original_request(output_spec: Dict[str, Any], request: Any) -> str:
    """Bind the immutable user request for one graph run to runtime context."""
    existing = str(output_spec.get(RUN_ORIGINAL_USER_REQUEST) or "").strip()
    if existing:
        return existing
    value = str(request or "").strip()
    if value:
        output_spec[RUN_ORIGINAL_USER_REQUEST] = value
    return value


def restore_run_original_request(
    *,
    output_spec: Dict[str, Any],
    state: Any,
    fallback: Any = "",
) -> str:
    """Restore a run-bound request from persisted graph state."""
    policy_context = getattr(state, "policy_context", None)
    graph = getattr(state, "graph", None)
    graph_globals = getattr(graph, "globals", None)
    goal_contract = getattr(state, "goal_contract", None)
    candidates = (
        (policy_context or {}).get(RUN_ORIGINAL_USER_REQUEST) if isinstance(policy_context, dict) else "",
        (graph_globals or {}).get(RUN_ORIGINAL_USER_REQUEST) if isinstance(graph_globals, dict) else "",
        (goal_contract or {}).get("objective") if isinstance(goal_contract, dict) else "",
        fallback,
    )
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            output_spec[RUN_ORIGINAL_USER_REQUEST] = value
            return value
    return ""


def resolve_run_original_request(
    *,
    output_spec: Dict[str, Any] | None,
    messages: Iterable[Any],
) -> str:
    """Resolve the active run request, with a last-user fallback for old runs."""
    spec = output_spec if isinstance(output_spec, dict) else {}
    for key in (RUN_ORIGINAL_USER_REQUEST, "original_user_request", "inherited_user_request"):
        value = str(spec.get(key) or "").strip()
        if value:
            return value

    for message in reversed(list(messages or [])):
        if isinstance(message, dict):
            raw_role = message.get("role", "")
            content = message.get("content", "")
        else:
            raw_role = getattr(message, "role", "")
            content = getattr(message, "content", "")
        role_value = getattr(raw_role, "value", None)
        role = str(role_value if role_value is not None else raw_role or "").lower()
        if role not in {"user", "human"}:
            continue
        value = str(content or "").strip()
        if value:
            return value
    return ""
