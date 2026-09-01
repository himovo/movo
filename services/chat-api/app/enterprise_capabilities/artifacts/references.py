from __future__ import annotations

from typing import Any


def safe_owner_prefix(user_id: str) -> str:
    owner = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in str(user_id).strip())
    return (owner or "anonymous") + "/"


def require_owned_artifact(artifact: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    value = dict(artifact or {})
    object_path = str(value.get("object_path") or "").strip().lstrip("/")
    if not object_path or ".." in object_path.split("/") or not object_path.startswith(safe_owner_prefix(user_id)):
        raise PermissionError("artifact reference is outside the authenticated user's storage scope")
    value["object_path"] = object_path
    # Bearer URLs are never trusted from model arguments. Storage resolves a
    # fresh URL from the authorized immutable object path when necessary.
    value.pop("url", None)
    value.pop("signed_url", None)
    return value


def require_owned_artifacts(items: list[Any], *, user_id: str) -> list[dict[str, Any]]:
    return [require_owned_artifact(dict(item), user_id=user_id) for item in items if isinstance(item, dict)]


def authorize_nested_artifact_refs(value: Any, *, user_id: str, depth: int = 0) -> Any:
    if depth > 12:
        raise ValueError("artifact input nesting is too deep")
    if isinstance(value, dict):
        current = dict(value)
        if "object_path" in current:
            current = require_owned_artifact(current, user_id=user_id)
        return {key: authorize_nested_artifact_refs(item, user_id=user_id, depth=depth + 1) for key, item in current.items()}
    if isinstance(value, list):
        return [authorize_nested_artifact_refs(item, user_id=user_id, depth=depth + 1) for item in value[:500]]
    return value
