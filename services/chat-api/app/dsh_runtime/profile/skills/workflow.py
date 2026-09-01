"""Compile adaptive ASKAI workflows into declarative DSH Skill bodies."""

from __future__ import annotations

import json
from typing import Any

from app.dsh_runtime.profile.tools import ToolProfileDefinition
from app.enterprise_capabilities.runtime.workflow_mapping import workflow_capability
from app.services.org_skill_adapter import _workflow_nodes as normalize_workflow_nodes

from .workflow_contract import validate_external_bindings, validate_node_identity
from .delivery_semantics import intermediate_artifact_nodes


def workflow_nodes(row: dict[str, Any]) -> list[dict[str, Any]]:
    contract = row.get("skill_contract") if isinstance(row.get("skill_contract"), dict) else {}
    structure = contract.get("structure") if isinstance(contract.get("structure"), dict) else {}
    nodes = structure.get("workflow_nodes")
    contracted = [dict(item) for item in nodes if isinstance(item, dict)] if isinstance(nodes, list) else []
    if contracted:
        return contracted

    # Personal workflows created before the DSH migration keep their tested
    # node definitions in config.workflowNodes. Reuse the same normalizer used
    # by organization Skills so both sources compile to one native contract.
    config = row.get("config") if isinstance(row.get("config"), dict) else {}
    return normalize_workflow_nodes(config)


def compile_workflow_body(
    row: dict[str, Any],
    *,
    tools: tuple[ToolProfileDefinition, ...],
    style_refs: dict[str, str],
) -> tuple[str, tuple[str, ...]]:
    nodes = workflow_nodes(row)
    if not nodes:
        raise ValueError(f"workflow Skill has no executable nodes: {row.get('name')}")
    validate_node_identity(nodes)
    by_capability = {tool.capability_ref: tool for tool in tools if tool.capability_ref}
    external_tools = [tool for tool in tools if tool.source_type in {"http", "mcp"}]
    rendered: list[str] = []
    capability_refs: list[str] = []
    intermediate_nodes = intermediate_artifact_nodes(nodes)
    for index, node in enumerate(nodes, start=1):
        node_type = str(node.get("type") or "").strip()
        binding = workflow_capability(node_type)
        tool_name = ""
        if binding.runtime_shape == "tool":
            tool = by_capability.get(binding.capability_ref)
            if tool is None:
                raise PermissionError(
                    f"workflow node {node_type} requires unavailable capability {binding.capability_ref}"
                )
            tool_name = tool.name
        elif binding.runtime_shape == "external_tool":
            if not external_tools:
                raise PermissionError("workflow call_tool node requires an authorized HTTP or MCP tool")
            configured = node.get("businessConfig") if isinstance(node.get("businessConfig"), dict) else {}
            wanted = str(
                configured.get("externalToolId")
                or configured.get("external_tool_id")
                or configured.get("toolId")
                or configured.get("tool_id")
                or ""
            ).strip()
            if wanted:
                matched = next((tool for tool in external_tools if tool.external_tool_id == wanted), None)
                if matched is None:
                    raise PermissionError(f"workflow references unauthorized external tool: {wanted}")
                tool_name = matched.name
                validate_external_bindings(node, matched)
        capability_refs.append(binding.capability_ref)
        instruction = str(node.get("description") or node.get("title") or node_type).strip()
        line = f"{index}. {instruction}\n   - capability_ref: `{binding.capability_ref}`"
        if tool_name:
            line += f"\n   - 调用工具：`{tool_name}`"
        if index - 1 in intermediate_nodes:
            line += "\n   - 此产物仅供后续步骤使用；调用工具时传入 `delivery_scope=intermediate`，不要作为独立附件交付给用户"
        bound_style_id = str(node.get("boundWritingSkillId") or "").strip()
        if bound_style_id:
            if node_type != "generate_content":
                raise ValueError("writing standard may only bind to a generate_content node")
            style_ref = style_refs.get(bound_style_id)
            if not style_ref:
                raise PermissionError(f"workflow writing standard is unavailable: {bound_style_id}")
            line += f"\n   - 调用内容生产时传入 `writing_style_ref={style_ref}`"
        config = node.get("businessConfig") if isinstance(node.get("businessConfig"), dict) else {}
        if config:
            line += f"\n   - 业务约束：{json.dumps(config, ensure_ascii=False, sort_keys=True)}"
        rendered.append(line)
    name = str(row.get("name") or "Workflow").strip()
    description = str(row.get("description") or row.get("summary") or "").strip()
    scenario = str(row.get("notes") or row.get("applicable_scenarios") or "").strip()
    body = f"""# {name}

## 目标
{description or name}

## 适用场景
{scenario or '当用户目标与本工作流描述一致时使用。'}

## 建议执行步骤
{chr(10).join(rendered)}

## 执行原则
- 这是供 DSH Agent Loop 使用的自适应 Skill，不是固定图执行计划。
- 根据当前上下文决定是否跳过、重复或并行无依赖步骤，但不得越过权限边界。
- 上一步产生的搜索证据、附件解析结果和结构化产物应作为后续步骤输入，不得重新伪造。
- 工具返回失败时依据真实错误调整；不得声称未实际完成的动作已经完成。

## 验收
- 用户要求的交付物完整，关键结论有可追溯证据。
- 所有外部写操作遵循 MOVO 审批策略。
- 写作规范只约束内容生成节点，不约束检索、计算、浏览器或普通工具调用。
"""
    return body.strip(), tuple(dict.fromkeys(capability_refs))
