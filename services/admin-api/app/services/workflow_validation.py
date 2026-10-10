"""Validation shared by organization Workflow Skill write paths."""

from __future__ import annotations

from typing import Any


def validate_workflow_config(config: dict[str, Any]) -> None:
    raw_nodes = config.get("workflowNodes") or config.get("workflow_nodes") or []
    if not isinstance(raw_nodes, list):
        raise ValueError("工作流节点格式无效")

    aliases = [
        str(node.get("outputAlias") or node.get("output_alias") or "").strip()
        for node in raw_nodes
        if isinstance(node, dict)
    ]
    populated = [alias for alias in aliases if alias]
    if len(populated) != len(set(populated)):
        raise ValueError("工作流各步骤的输出名称不能重复")

    for index, node in enumerate(raw_nodes, start=1):
        if not isinstance(node, dict):
            continue
        business = node.get("businessConfig") or node.get("business_config") or {}
        if not isinstance(business, dict):
            business = {}
        if node.get("type") == "read_material" and business.get("sourceType") == "knowledge_document":
            if not str(business.get("knowledgeSourceId") or "").strip():
                raise ValueError(f"第 {index} 步：请先选择要读取的知识文档")
        if node.get("type") == "call_tool":
            if not str(business.get("preferredToolId") or business.get("externalToolId") or business.get("toolId") or "").strip():
                raise ValueError(f"第 {index} 步：请先选择要调用的工具")
