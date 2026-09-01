"""browser.submit — create a new record / submit a form."""
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
            reason="confirmation missing — a submit task must report what the server confirmed (text, record_id, or redirect_url)",
            missing=["confirmation"],
        )
    text = str(conf.get("text") or "").strip()
    record_id = str(conf.get("record_id") or "").strip()
    redirect_url = str(conf.get("redirect_url") or "").strip()
    if not (text or record_id or redirect_url):
        return ContractResult(
            ok=False,
            reason="confirmation must carry at least one of: text / record_id / redirect_url",
            missing=["confirmation.text", "confirmation.record_id", "confirmation.redirect_url"],
        )
    return ContractResult(ok=True)


SPEC = BrowserActionSpec(
    capability_id="browser.submit",
    name_zh="创建/提交",
    name_en="Submit / Create",
    description_zh="提交表单或创建新记录（比如下单、新建用户、提交申请）",
    description_en="Submit a form or create a new record (place order, create user, file request)",
    produces=("confirmation",),
    data_schema_hint_zh=(
        '{"confirmation": {"text": "<页面上出现的成功文案>", '
        '"record_id": "<新建的记录 ID, 可选>", '
        '"redirect_url": "<提交后跳转的 URL, 可选>"}}'
        '— 至少填其中一项'
    ),
    data_schema_hint_en=(
        '{"confirmation": {"text": "<success message shown on page>", '
        '"record_id": "<id of created record, optional>", '
        '"redirect_url": "<post-submit redirect URL, optional>"}} '
        '— at least one field must be present'
    ),
    validate=_validate,
)
