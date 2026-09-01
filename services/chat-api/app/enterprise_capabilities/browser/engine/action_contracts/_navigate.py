"""browser.navigate — land on a target URL / view."""
from __future__ import annotations

from typing import Any, Dict

from .schema import BrowserActionSpec, ContractResult


def _validate(data: Dict[str, Any]) -> ContractResult:
    if not isinstance(data, dict):
        return ContractResult(ok=False, reason="browser_done.data must be an object", missing=["final_url"])
    final_url = str(data.get("final_url") or "").strip()
    if not final_url:
        return ContractResult(
            ok=False,
            reason="final_url missing — a navigate task must report the URL it actually landed on",
            missing=["final_url"],
        )
    if final_url.lower() == "about:blank":
        return ContractResult(
            ok=False,
            reason="final_url is about:blank — navigation didn't complete",
            missing=["final_url"],
        )
    return ContractResult(ok=True)


SPEC = BrowserActionSpec(
    capability_id="browser.navigate",
    name_zh="切换页面",
    name_en="Navigate",
    description_zh="打开指定页面 / 跳转到指定视图（不改数据、不提交）",
    description_en="Open a target page or switch views (no data change, no submit)",
    produces=("final_url",),
    data_schema_hint_zh=(
        '{"final_url": "<落地后实际 URL>", "page_title": "<页面标题, 可选>", '
        '"landed_ok": true}'
    ),
    data_schema_hint_en=(
        '{"final_url": "<actual URL after landing>", '
        '"page_title": "<optional>", "landed_ok": true}'
    ),
    validate=_validate,
)
