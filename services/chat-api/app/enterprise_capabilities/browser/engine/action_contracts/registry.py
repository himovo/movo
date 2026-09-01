"""Central registry of browser action contracts.

Adding a new capability is one-file-one-line: create
``_<name>.py`` exporting ``SPEC`` and register it here. Nothing else
in the codebase should enumerate the seven ids.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import (
    _delete,
    _file_transfer,
    _modify,
    _navigate,
    _publish,
    _read,
    _submit,
)
from .schema import BrowserActionSpec, ContractResult


_REGISTRY: Dict[str, BrowserActionSpec] = {
    _read.SPEC.capability_id: _read.SPEC,
    _navigate.SPEC.capability_id: _navigate.SPEC,
    _submit.SPEC.capability_id: _submit.SPEC,
    _modify.SPEC.capability_id: _modify.SPEC,
    _delete.SPEC.capability_id: _delete.SPEC,
    _file_transfer.SPEC.capability_id: _file_transfer.SPEC,
    _publish.SPEC.capability_id: _publish.SPEC,
}

# Compatibility names are normalized at the contract boundary so legacy graph
# nodes receive the same prompt, validation, and result semantics as new ones.
_ALIASES = {
    "browser.navigate_and_extract": "browser.read",
}

_REPLAY_SENSITIVE_CAPABILITIES = frozenset({
    "browser.submit",
    "browser.modify",
    "browser.delete",
    "browser.file_transfer",
    "browser.publish",
})
_REPLAY_ALIASES = {
    "browser.publish_or_submit": "browser.publish",
}


def get_spec(capability_id: str) -> Optional[BrowserActionSpec]:
    """Return the spec for a capability id, or ``None`` if the id isn't
    one of the registered browser actions (covers legacy ids like
    ``browser.publish_or_submit`` that predate this taxonomy — callers
    should treat "no spec" as "no contract, pass through")."""
    normalized = str(capability_id or "").strip().lower()
    return _REGISTRY.get(_ALIASES.get(normalized, normalized))


def blocks_whole_node_replay(capability_id: str) -> bool:
    normalized = str(capability_id or "").strip().lower()
    return _REPLAY_ALIASES.get(normalized, normalized) in _REPLAY_SENSITIVE_CAPABILITIES


def list_specs() -> List[BrowserActionSpec]:
    """All registered specs, stable order for prompt rendering."""
    return list(_REGISTRY.values())


def validate_data(capability_id: str, data: Any) -> ContractResult:
    """Run the contract for a capability. Unknown capability is treated
    as "no contract" (passthrough), preserving backward compatibility
    while new ids roll out."""
    spec = get_spec(capability_id)
    if spec is None:
        return ContractResult(ok=True, reason="no contract registered")
    data_dict = data if isinstance(data, dict) else {}
    return spec.validate(data_dict)


def describe_for_planner(lang: str = "zh") -> str:
    """Render a menu of capabilities + required produce shape — inject
    into the planner's prompt so it picks the right capability per step."""
    is_zh = str(lang or "").startswith("zh")
    lines: List[str] = []
    for spec in _REGISTRY.values():
        desc = spec.description_zh if is_zh else spec.description_en
        hint = spec.data_schema_hint_zh if is_zh else spec.data_schema_hint_en
        lines.append(f"- `{spec.capability_id}`: {desc}\n  produces shape: {hint}")
    header = "可选的浏览器动作类型（每个 browser step 选一个）:" if is_zh \
             else "Available browser action types (pick one per browser step):"
    return header + "\n" + "\n".join(lines)


def describe_for_agent(capability_id: str, lang: str = "zh") -> str:
    """Per-step explanation the browser task planner shows to the
    executing LLM so it knows exactly what browser_done.data must
    contain. Empty string when capability has no contract."""
    spec = get_spec(capability_id)
    if spec is None:
        return ""
    is_zh = str(lang or "").startswith("zh")
    name = spec.name_zh if is_zh else spec.name_en
    desc = spec.description_zh if is_zh else spec.description_en
    hint = spec.data_schema_hint_zh if is_zh else spec.data_schema_hint_en
    if is_zh:
        return (
            f"【本步骤动作类型】{name} (`{spec.capability_id}`)\n"
            f"动作说明：{desc}\n"
            f"browser_done 时 data 必须符合这个结构（字段名固定、值真实可观测，"
            f"**不允许空/占位**；拿不到就继续扫页面、实在不行 browser_fail 说明）：\n"
            f"{hint}"
        )
    return (
        f"STEP ACTION TYPE: {name} (`{spec.capability_id}`)\n"
        f"Description: {desc}\n"
        f"Your browser_done.data MUST match this shape "
        f"(fixed field names, real observed values — no empty/placeholder; "
        f"keep scanning or call browser_fail if impossible):\n"
        f"{hint}"
    )
