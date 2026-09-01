"""browser.read — pull structured data out of a page."""
from __future__ import annotations

from typing import Any, Dict

from .schema import BrowserActionSpec, ContractResult


_PLACEHOLDER_STRINGS = (
    "", "null", "none", "n/a", "undefined", "待确认", "tbd",
    "to be confirmed", "tbc", "--", "—",
)


def _value_is_concrete(v: Any) -> bool:
    """A value counts as "observed" iff it's a real non-empty payload.

    Structural check only — empty string / None / empty container /
    well-known placeholder words are rejected; everything else passes.
    """
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip().lower() not in _PLACEHOLDER_STRINGS
    if isinstance(v, (list, dict)):
        return bool(v)  # non-empty container
    return True  # numbers, bools


def _validate(data: Dict[str, Any]) -> ContractResult:
    if not isinstance(data, dict):
        return ContractResult(ok=False, reason="browser_done.data must be an object", missing=["result"])
    result = data.get("result")
    if result is None:
        return ContractResult(
            ok=False,
            reason="browser_done.data.result is missing — a read task must expose the observed values under `result`",
            missing=["result"],
        )
    # Accept both {field: value} and [row, row, ...] shapes.
    if isinstance(result, dict):
        if not result:
            return ContractResult(ok=False, reason="result is an empty object — no values were captured", missing=["result.*"])
        if not any(_value_is_concrete(v) for v in result.values()):
            return ContractResult(
                ok=False,
                reason="every value under result is empty / placeholder — re-scan page_text or call browser_fail",
                missing=[f"result.{k}" for k, v in result.items() if not _value_is_concrete(v)][:6],
            )
        return ContractResult(ok=True)
    if isinstance(result, list):
        if not result:
            return ContractResult(ok=False, reason="result is an empty list", missing=["result[*]"])
        # A list of scalars or dicts is fine as long as it's not empty
        return ContractResult(ok=True)
    # Scalar result is acceptable (e.g. a single count)
    if _value_is_concrete(result):
        return ContractResult(ok=True)
    return ContractResult(ok=False, reason="result has no concrete value", missing=["result"])


SPEC = BrowserActionSpec(
    capability_id="browser.read",
    name_zh="读数据",
    name_en="Read data",
    description_zh="从当前页面读取可见的数据/指标/列表（只看不改）",
    description_en="Read visible data / metrics / lists from the current page (no state change)",
    produces=("result",),
    data_schema_hint_zh=(
        '{"result": {"<字段名>": "<页面上观测到的真实值>", ...}}'
        '或 {"result": [{...}, {...}]}（列表型数据）'
    ),
    data_schema_hint_en=(
        '{"result": {"<field>": "<value observed on the page>", ...}}'
        ' or {"result": [{...}, {...}]} for list-shaped data'
    ),
    validate=_validate,
)
