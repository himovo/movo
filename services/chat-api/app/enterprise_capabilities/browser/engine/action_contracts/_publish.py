"""browser.publish — send content to an external channel (email, social, IM, etc.)."""
from __future__ import annotations

from typing import Any, Dict

from .schema import BrowserActionSpec, ContractResult


def _validate(data: Dict[str, Any]) -> ContractResult:
    if not isinstance(data, dict):
        return ContractResult(ok=False, reason="browser_done.data must be an object", missing=["delivery"])
    d = data.get("delivery")
    if not isinstance(d, dict) or not d:
        return ContractResult(
            ok=False,
            reason="delivery missing — a publish task must describe where the content went",
            missing=["delivery"],
        )
    channel = str(d.get("channel") or "").strip()
    destination = str(d.get("destination") or "").strip()
    if not channel:
        return ContractResult(
            ok=False,
            reason="delivery.channel missing — e.g. 'email' / 'wechat_official' / 'xiaohongshu' / 'slack'",
            missing=["delivery.channel"],
        )
    if not destination:
        return ContractResult(
            ok=False,
            reason="delivery.destination missing — e.g. recipient email / channel id / published URL",
            missing=["delivery.destination"],
        )
    return ContractResult(ok=True)


SPEC = BrowserActionSpec(
    capability_id="browser.publish",
    name_zh="对外发送/发布",
    name_en="Publish / Send",
    description_zh="把内容发送到外部通道（发邮件、发朋友圈、发微博、发公众号文章）",
    description_en="Send content to an external channel (email, social post, IM broadcast)",
    produces=("delivery",),
    data_schema_hint_zh=(
        '{"delivery": {"channel": "<通道>: email/xiaohongshu/wechat_official/slack/...", '
        '"destination": "<目的地: 收件人 / 已发布 URL / channel id>", '
        '"identifier": "<本次发送的引用号, 可选>"}}'
    ),
    data_schema_hint_en=(
        '{"delivery": {"channel": "<channel: email/slack/xiaohongshu/...>", '
        '"destination": "<recipient / published URL / channel id>", '
        '"identifier": "<reference id for this send, optional>"}}'
    ),
    validate=_validate,
)
