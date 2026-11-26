import json
from typing import Any


def decode_response_json_field(response: Any, path: str) -> Any:
    """Decode an explicitly configured JSON container without changing the envelope."""
    ancestors: list[tuple[dict[str, Any], str]] = []
    value = response
    for key in path.strip().split("."):
        if not key or not isinstance(value, dict) or key not in value:
            return response
        ancestors.append((value, key))
        value = value[key]
    if not isinstance(value, str):
        return response
    try:
        decoded = json.loads(value)
    except (ValueError, RecursionError):
        return response
    if not isinstance(decoded, (dict, list)):
        return response
    for record, key in reversed(ancestors):
        decoded = {**record, key: decoded}
    return decoded
