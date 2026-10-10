from __future__ import annotations

import pytest

from app.services.workflow_validation import validate_workflow_config


def test_rejects_duplicate_workflow_output_aliases() -> None:
    with pytest.raises(ValueError, match="输出名称不能重复"):
        validate_workflow_config({
            "workflowNodes": [
                {"id": "step-1", "outputAlias": "抽取结果"},
                {"id": "step-2", "outputAlias": "抽取结果"},
            ]
        })


def test_allows_empty_and_unique_workflow_output_aliases() -> None:
    validate_workflow_config({
        "workflowNodes": [
            {"id": "step-1", "outputAlias": ""},
            {"id": "step-2", "outputAlias": "指标结果"},
            {"id": "step-3", "outputAlias": "诊断报告"},
        ]
    })


@pytest.mark.parametrize("node, message", [
    ({"type": "read_material", "businessConfig": {"sourceType": "knowledge_document"}}, "知识文档"),
    ({"type": "call_tool", "businessConfig": {"preferredToolId": ""}}, "工具"),
])
def test_requires_selected_knowledge_document_or_tool(node: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_workflow_config({"workflowNodes": [node]})


def test_upload_material_and_bound_tool_are_valid() -> None:
    validate_workflow_config({"workflowNodes": [
        {"type": "read_material", "businessConfig": {"sourceType": "upload"}},
        {"type": "read_material", "businessConfig": {
            "sourceType": "knowledge_document", "knowledgeSourceId": "doc-1",
        }},
        {"type": "call_tool", "businessConfig": {"preferredToolId": "tool-1"}},
    ]})
