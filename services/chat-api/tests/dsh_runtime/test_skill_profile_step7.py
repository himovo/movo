from __future__ import annotations

import pytest
import asyncio

from app.dsh_runtime.profile.skills import SkillProfileCompiler
from app.dsh_runtime.profile.tools import ToolProfileDefinition


class FakeSkillCatalog:
    def __init__(self, rows):
        self.rows = rows

    async def list_enabled(self, tenant_id: str, user_id: str):
        assert tenant_id == "tenant-a"
        assert user_id == "user-a"
        return list(self.rows)


def tool(name: str, capability_ref: str) -> ToolProfileDefinition:
    return ToolProfileDefinition(
        name=name,
        version="tool-v1",
        source_type="internal",
        capability_ref=capability_ref,
        external_tool_id=capability_ref,
        display_name=name,
        description=name,
        input_schema={"type": "object", "properties": {}},
        risk_level="read",
    )


def style_row():
    return {
        "id": "org_skill:style-1",
        "name": "董事会报告规范",
        "description": "用于董事会报告",
        "visibility": "organization",
        "source": "org_db",
        "skill_type": "style",
        "role": "style",
        "skill_markdown": "仅在写报告时使用正式、简洁的管理者语言。",
    }


def workflow_row(bound_style: str = "org_skill:style-1"):
    return {
        "id": "org_skill:workflow-1",
        "name": "调研并生成报告",
        "description": "先检索证据，再生成报告",
        "visibility": "organization",
        "source": "org_db",
        "skill_type": "composite_task",
        "skill_contract": {
            "structure": {"workflow_nodes": [
                {"id": "search", "type": "external_search", "description": "检索充分证据"},
                {
                    "id": "write", "type": "generate_content", "description": "依据证据生成报告",
                    "boundWritingSkillId": bound_style,
                },
            ]}
        },
    }


def test_workflow_compiles_to_native_skill_and_style_is_not_a_catalog_skill():
    compiled = asyncio.run(SkillProfileCompiler(FakeSkillCatalog([style_row(), workflow_row()])).compile(
        tenant_id="tenant-a",
        user_id="user-a",
        tools=(tool("progressive_research", "research.progressive@v1"), tool("content_production", "content.produce@v1")),
    ))
    assert len(compiled.skills) == 1
    assert len(compiled.writing_styles) == 1
    skill = compiled.skills[0]
    assert skill.kind == "workflow"
    assert skill.capability_refs == ("research.progressive@v1", "content.produce@v1")
    assert "progressive_research" in skill.content
    assert "content_production" in skill.content
    assert f"writing_style_ref={compiled.writing_styles[0].ref}" in skill.content
    assert "董事会报告规范" not in [item.name for item in compiled.skills]


def test_legacy_personal_workflow_falls_back_to_config_nodes():
    row = {
        "id": "personal-legacy-workflow",
        "name": "CRI语部填报原版转定版DOCX",
        "description": "处理并导出文档",
        "visibility": "personal",
        "source": "user_db",
        "skill_type": "composite_task",
        # Older personal Skills may have a contract without normalized nodes.
        "skill_contract": {"structure": {}},
        "config": {
            "workflowNodes": [{
                "id": "process",
                "type": "script_plugin",
                "title": "数据处理",
                "description": "执行已配置的数据处理脚本",
                "businessConfig": {"pluginCode": "existing-tested-plugin"},
            }],
        },
    }
    compiled = asyncio.run(SkillProfileCompiler(FakeSkillCatalog([row])).compile(
        tenant_id="tenant-a",
        user_id="user-a",
        tools=(tool("controlled_script", "data.run_script@v1"),),
    ))
    assert len(compiled.skills) == 1
    assert compiled.skills[0].kind == "workflow"
    assert compiled.skills[0].capability_refs == ("data.run_script@v1",)
    assert "controlled_script" in compiled.skills[0].content
    assert "执行已配置的数据处理脚本" in compiled.skills[0].content


def test_workflow_marks_spreadsheet_handoff_internal_before_final_export():
    row = {
        "id": "workflow-delivery", "name": "汇总并导出报告", "skill_type": "composite_task",
        "skill_contract": {"structure": {"workflow_nodes": [
            {"id": "table", "type": "fill_table", "description": "生成汇总表"},
            {"id": "export", "type": "export_delivery", "description": "导出最终报告"},
        ]}},
    }
    compiled = asyncio.run(SkillProfileCompiler(FakeSkillCatalog([row])).compile(
        tenant_id="tenant-a", user_id="user-a",
        tools=(tool("table_generate", "artifact.table_generate@v1"), tool("artifact_export", "artifact.export@v1")),
    ))
    assert "delivery_scope=intermediate" in compiled.skills[0].content


def test_workflow_marks_script_file_handoff_internal_before_final_export():
    row = {
        "id": "workflow-script-delivery", "name": "处理数据并导出报告", "skill_type": "composite_task",
        "skill_contract": {"structure": {"workflow_nodes": [
            {"id": "prepare", "type": "script_plugin", "description": "生成报告结构化数据"},
            {"id": "export", "type": "export_delivery", "description": "导出最终报告"},
        ]}},
    }
    compiled = asyncio.run(SkillProfileCompiler(FakeSkillCatalog([row])).compile(
        tenant_id="tenant-a", user_id="user-a",
        tools=(tool("run_script", "data.run_script@v1"), tool("artifact_export", "artifact.export@v1")),
    ))
    assert "delivery_scope=intermediate" in compiled.skills[0].content


def test_standalone_spreadsheet_workflow_remains_user_visible():
    row = {
        "id": "workflow-table", "name": "生成表格", "skill_type": "composite_task",
        "skill_contract": {"structure": {"workflow_nodes": [
            {"id": "table", "type": "fill_table", "description": "生成最终表格"},
        ]}},
    }
    compiled = asyncio.run(SkillProfileCompiler(FakeSkillCatalog([row])).compile(
        tenant_id="tenant-a", user_id="user-a", tools=(tool("table_generate", "artifact.table_generate@v1"),),
    ))
    assert "delivery_scope=intermediate" not in compiled.skills[0].content


def test_workflow_fails_closed_when_capability_is_not_authorized():
    with pytest.raises(PermissionError, match="research.progressive@v1"):
        asyncio.run(SkillProfileCompiler(FakeSkillCatalog([workflow_row("" )])).compile(
            tenant_id="tenant-a", user_id="user-a",
            tools=(tool("content_production", "content.produce@v1"),),
        ))


def test_workflow_fails_closed_when_bound_style_is_missing():
    with pytest.raises(PermissionError, match="writing standard"):
        asyncio.run(SkillProfileCompiler(FakeSkillCatalog([workflow_row("missing")])).compile(
            tenant_id="tenant-a", user_id="user-a",
            tools=(tool("progressive_research", "research.progressive@v1"), tool("content_production", "content.produce@v1")),
        ))


def test_org_workflow_accepts_raw_control_plane_writing_style_id():
    compiled = asyncio.run(SkillProfileCompiler(FakeSkillCatalog([
        style_row(), workflow_row("style-1"),
    ])).compile(
        tenant_id="tenant-a", user_id="user-a",
        tools=(tool("progressive_research", "research.progressive@v1"), tool("content_production", "content.produce@v1")),
    ))
    assert f"writing_style_ref={compiled.writing_styles[0].ref}" in compiled.skills[0].content


def test_workflow_fails_closed_for_an_unmigrated_node_type():
    row = workflow_row("")
    row["skill_contract"]["structure"]["workflow_nodes"] = [
        {"id": "unknown", "type": "future_unknown_node", "description": "未知能力"},
    ]
    with pytest.raises(LookupError, match="not migrated"):
        asyncio.run(SkillProfileCompiler(FakeSkillCatalog([row])).compile(
            tenant_id="tenant-a", user_id="user-a", tools=(),
        ))


def test_call_tool_uses_real_external_tool_id_and_rejects_unauthorized_binding():
    row = workflow_row("")
    row["skill_contract"]["structure"]["workflow_nodes"] = [{
        "id": "crm", "type": "call_tool", "description": "查询 CRM",
        "businessConfig": {"externalToolId": "crm-tool"},
    }]
    crm = ToolProfileDefinition(
        name="crm_search", version="tool-v1", source_type="mcp",
        external_tool_id="crm-tool", display_name="CRM", description="CRM",
        input_schema={
            "type": "object", "additionalProperties": False,
            "properties": {"period": {"type": "string"}},
        }, risk_level="read",
    )
    compiled = asyncio.run(SkillProfileCompiler(FakeSkillCatalog([row])).compile(
        tenant_id="tenant-a", user_id="user-a", tools=(crm,),
    ))
    assert "`crm_search`" in compiled.skills[0].content
    other = crm.model_copy(update={"name": "other_tool", "external_tool_id": "other-tool"})
    with pytest.raises(PermissionError, match="unauthorized external tool"):
        asyncio.run(SkillProfileCompiler(FakeSkillCatalog([row])).compile(
            tenant_id="tenant-a", user_id="user-a", tools=(other,),
        ))


def test_workflow_contract_rejects_duplicate_outputs_and_unknown_tool_arguments():
    row = workflow_row("")
    row["skill_contract"]["structure"]["workflow_nodes"][0]["outputAlias"] = "result"
    row["skill_contract"]["structure"]["workflow_nodes"][1]["outputAlias"] = "result"
    with pytest.raises(ValueError, match="output aliases"):
        asyncio.run(SkillProfileCompiler(FakeSkillCatalog([row])).compile(
            tenant_id="tenant-a", user_id="user-a", tools=(
                tool("progressive_research", "research.progressive@v1"),
                tool("content_production", "content.produce@v1"),
            ),
        ))

    external = workflow_row("")
    external["skill_contract"]["structure"]["workflow_nodes"] = [{
        "id": "crm", "type": "call_tool", "description": "查询 CRM",
        "businessConfig": {
            "externalToolId": "crm-tool",
            "tool_arg_bindings": [{"arg_name": "undeclared", "value": "x"}],
        },
    }]
    crm = ToolProfileDefinition(
        name="crm_search", version="tool-v1", source_type="mcp",
        external_tool_id="crm-tool", display_name="CRM", description="CRM",
        input_schema={
            "type": "object", "additionalProperties": False,
            "properties": {"period": {"type": "string"}},
        }, risk_level="read",
    )
    with pytest.raises(ValueError, match="not declared by tool schema"):
        asyncio.run(SkillProfileCompiler(FakeSkillCatalog([external])).compile(
            tenant_id="tenant-a", user_id="user-a", tools=(crm,),
        ))


def test_ordinary_skill_is_native_and_does_not_require_taskgraph():
    row = {
        "id": "personal-1", "name": "客户访谈分析", "description": "分析访谈",
        "skill_type": "execution", "skill_markdown": "提取诉求、证据与待办，不要虚构。",
    }
    compiled = asyncio.run(SkillProfileCompiler(FakeSkillCatalog([row])).compile(
        tenant_id="tenant-a", user_id="user-a", tools=(),
    ))
    assert compiled.skills[0].kind == "ordinary"
    assert "提取诉求" in compiled.skills[0].content
    assert "TaskGraph" not in compiled.skills[0].content


def test_skill_and_style_versions_cover_all_model_visible_definition_fields():
    ordinary = {
        "id": "skill-1", "name": "访谈分析", "description": "分析访谈",
        "skill_type": "execution", "skill_markdown": "提取事实。",
    }
    first = asyncio.run(SkillProfileCompiler(FakeSkillCatalog([ordinary, style_row()])).compile(
        tenant_id="tenant-a", user_id="user-a", tools=(),
    ))
    ordinary["description"] = "分析访谈和待办"
    changed_style = style_row()
    changed_style["name"] = "新的董事会报告规范"
    second = asyncio.run(SkillProfileCompiler(FakeSkillCatalog([ordinary, changed_style])).compile(
        tenant_id="tenant-a", user_id="user-a", tools=(),
    ))
    assert first.skills[0].version != second.skills[0].version
    assert first.writing_styles[0].version != second.writing_styles[0].version
