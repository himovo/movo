from types import SimpleNamespace

from app.enterprise_capabilities.content.publish_assembly.workflow_content_assembler import assemble_workflow_content


def _node(node_id: str, capability_id: str, *, title: str, output_alias: str = "", effect: str = ""):
    semantic = {}
    if effect:
        semantic["contentEffect"] = effect
    return SimpleNamespace(
        node_id=node_id,
        goal=title,
        meta={
            "capability_id": capability_id,
            "selected_skill": {"skill_type": "composite_task", "role": "execution"},
            "workflow_step": {
                "title": title,
                "output_alias": output_alias,
                "semantic_config": semantic,
            },
            "semantic_config": semantic,
        },
    )


def test_workflow_content_assembler_combines_only_reader_facing_content() -> None:
    nodes = [
        _node("N_TOOL", "external.invoke_tool", title="调用经营数据工具"),
        _node("N_REPORT", "generation.compose_dynamic", title="撰写诊断报告", output_alias="诊断报告", effect="primary"),
        _node("N_SUMMARY", "file.transform_content", title="生成英文摘要", output_alias="English Executive Summary", effect="append"),
        _node("N_TABLE", "file.generate_table", title="生成整改行动表", output_alias="整改行动表", effect="append"),
        _node("N_ATTACH", "file.generate_table", title="生成附件表", output_alias="附件表", effect="attach"),
    ]
    assembly = assemble_workflow_content(
        output_spec={"selected_skill": {"skill_type": "composite_task", "role": "execution"}},
        nodes=nodes,
        graph_artifacts={
            "N_TOOL": {
                "plugin_result": {"huge": [{"raw": "SHOULD_NOT_APPEAR"}]},
                "answer": '{"raw":"SHOULD_NOT_APPEAR"}',
            },
            "N_REPORT": {"final_markdown": "# 华东直营门店诊断报告\n\n主报告正文。"},
            "N_SUMMARY": {"transformed_markdown": "This is the English executive summary."},
            "N_TABLE": {"markdown_table": "|问题|动作|\n|-|-|\n|转化低|复盘商机|"},
            "N_ATTACH": {"markdown_table": "|附件|说明|\n|-|-|\n|明细|另附|"},
        },
    )

    assert assembly is not None
    assert "# 华东直营门店诊断报告" in assembly.final_markdown
    assert "## English Executive Summary" in assembly.final_markdown
    assert "This is the English executive summary." in assembly.final_markdown
    assert "## 整改行动表" in assembly.final_markdown
    assert "|问题|动作|" in assembly.final_markdown
    assert "|附件|说明|" not in assembly.final_markdown
    assert "SHOULD_NOT_APPEAR" not in assembly.final_markdown
    assert [item.node_id for item in assembly.contributions] == ["N_REPORT", "N_SUMMARY", "N_TABLE"]


def test_workflow_content_assembler_is_gated_to_workflow_skills() -> None:
    assembly = assemble_workflow_content(
        output_spec={},
        nodes=[
            SimpleNamespace(
                node_id="N_REPORT",
                goal="撰写报告",
                meta={"capability_id": "generation.compose_dynamic"},
            ),
            SimpleNamespace(
                node_id="N_SUMMARY",
                goal="生成摘要",
                meta={"capability_id": "file.transform_content"},
            ),
        ],
        graph_artifacts={
            "N_REPORT": {"final_markdown": "# 报告\n\n正文。"},
            "N_SUMMARY": {"transformed_markdown": "Summary."},
        },
    )

    assert assembly is None
