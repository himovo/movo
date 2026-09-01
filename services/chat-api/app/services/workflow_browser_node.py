"""Compile a natural-language browser workflow node to a runtime capability."""
from __future__ import annotations

from typing import Any, Dict


def browser_node_target_name(business_config: Dict[str, Any] | None = None) -> str:
    config = business_config if isinstance(business_config, dict) else {}
    return str(config.get("targetName") or config.get("target_name") or "").strip()


def browser_node_target_url(business_config: Dict[str, Any] | None = None) -> str:
    config = business_config if isinstance(business_config, dict) else {}
    return str(config.get("targetUrl") or config.get("target_url") or "").strip()


def browser_node_target_reference(business_config: Dict[str, Any] | None = None) -> str:
    target_name = browser_node_target_name(business_config)
    target_url = browser_node_target_url(business_config)
    if target_name and target_url:
        return f"[目标系统: {target_name} ({target_url})]"
    if target_name:
        return f"[目标系统: {target_name}]"
    if target_url:
        return f"[目标网址: {target_url}]"
    return ""


def browser_node_objective(description: str, business_config: Dict[str, Any] | None = None) -> str:
    instruction = str(description or "").strip()
    target_reference = browser_node_target_reference(business_config)
    return "\n\n".join(part for part in (target_reference, instruction) if part)


def browser_node_capability(description: str, business_config: Dict[str, Any] | None = None) -> str:
    text = str(description or "").strip().lower()
    config = business_config if isinstance(business_config, dict) else {}
    explicit = str(config.get("capabilityId") or config.get("capability_id") or "").strip()
    if explicit.startswith("browser."):
        return explicit

    if any(word in text for word in ("删除", "移除", "作废", "delete", "remove")):
        return "browser.delete"
    if any(word in text for word in ("发布", "上线", "群发", "publish")) and not any(
        word in text for word in ("不要发布", "不发布", "禁止发布", "保存草稿")
    ):
        return "browser.publish"
    if any(word in text for word in ("上传", "下载", "导入", "upload", "download", "import")):
        return "browser.file_transfer"
    if any(word in text for word in ("新增", "新建", "创建", "添加", "提交", "保存", "草稿", "create", "submit", "save")):
        return "browser.submit"
    if any(word in text for word in ("修改", "编辑", "更新", "填写", "变更", "modify", "edit", "update", "fill")):
        return "browser.modify"
    if any(word in text for word in ("查询", "搜索", "读取", "获取", "采集", "查看", "query", "search", "read", "extract")):
        return "browser.read"
    return "browser.navigate_and_extract"
