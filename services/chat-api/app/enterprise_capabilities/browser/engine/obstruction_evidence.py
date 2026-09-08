"""Interpret structured hit-test evidence, not the generic stale-target text."""
import json
from typing import Any


def obstruction_evidence(error: object) -> dict[str, Any] | None:
    text = str(error or "")
    if "diagnostic=" not in text:
        return None
    try:
        diagnostic, _ = json.JSONDecoder().raw_decode(text.split("diagnostic=", 1)[1])
    except (ValueError, TypeError):
        return None
    if not isinstance(diagnostic, dict) or diagnostic.get("targetResolved") is not True:
        return None
    hit = diagnostic.get("hit")
    if diagnostic.get("hitsTarget") is not False or not isinstance(hit, dict):
        return None
    # Keep only bounded explanatory data, never persist the full page text.
    return {"reason": "occluded", "blocker_tag": str(hit.get("tag") or ""),
            "blocker_role": str(hit.get("role") or ""),
            "blocker_text": str(hit.get("text") or "")[:160]}


OBSTRUCTION_GUIDANCE = (
    "目标节点仍存在，但点击点被其他页面层覆盖，不是编号失效。"
    "先处理覆盖层内已观察到的关闭/返回入口，或使用已观察到的目标链接导航；"
    "不要重复点击底层目标、盲目填入或只重复观察。不要凭空构造链接或关闭按钮；"
    "关闭或离开前检查未提交内容，不能擅自丢弃用户输入。"
)
