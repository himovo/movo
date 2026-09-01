"""browser.delete — remove existing data."""
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
            reason="confirmation missing — a delete task must report server confirmation of removal",
            missing=["confirmation"],
        )
    text = str(conf.get("text") or "").strip()
    if not text:
        return ContractResult(
            ok=False,
            reason="confirmation.text missing — quote the deletion-success message shown on page",
            missing=["confirmation.text"],
        )
    return ContractResult(ok=True)


SPEC = BrowserActionSpec(
    capability_id="browser.delete",
    name_zh="删除",
    name_en="Delete / Remove",
    description_zh="删除一条已有数据（取消订单、移除成员、删除文件）",
    description_en="Remove existing data (cancel order, remove member, delete file)",
    produces=("confirmation",),
    data_schema_hint_zh=(
        '{"confirmation": {"text": "<删除成功文案>", '
        '"removed_ref": "<被删掉的记录引用, 可选>"}}'
    ),
    data_schema_hint_en=(
        '{"confirmation": {"text": "<success text>", '
        '"removed_ref": "<reference to removed item, optional>"}}'
    ),
    validate=_validate,
)
