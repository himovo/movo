"""browser.modify — change existing data."""
from __future__ import annotations

from typing import Any, Dict

from .schema import BrowserActionSpec, ContractResult


def _validate(data: Dict[str, Any]) -> ContractResult:
    if not isinstance(data, dict):
        return ContractResult(ok=False, reason="browser_done.data must be an object", missing=["confirmation"])
    conf = data.get("confirmation")
    if not isinstance(conf, dict) or not conf:
        return ContractResult(
            ok=False,
            reason="confirmation missing — a modify task must report server confirmation of the change",
            missing=["confirmation"],
        )
    text = str(conf.get("text") or "").strip()
    if not text:
        return ContractResult(
            ok=False,
            reason="confirmation.text missing — quote the success message shown on the page",
            missing=["confirmation.text"],
        )
    return ContractResult(ok=True)


SPEC = BrowserActionSpec(
    capability_id="browser.modify",
    name_zh="修改",
    name_en="Modify / Update",
    description_zh="修改页面上已有的数据（改设置、改权限、改状态）",
    description_en="Change existing data on a page (update setting / permission / state)",
    produces=("confirmation",),
    data_schema_hint_zh=(
        '{"confirmation": {"text": "<页面确认文案>", '
        '"changed_field": "<被改的字段, 可选>", '
        '"new_value": "<改后的值, 可选>"}}'
    ),
    data_schema_hint_en=(
        '{"confirmation": {"text": "<confirmation text on page>", '
        '"changed_field": "<optional>", "new_value": "<optional>"}}'
    ),
    validate=_validate,
)
