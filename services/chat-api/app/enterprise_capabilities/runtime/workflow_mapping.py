"""Versioned bridge from ASKAI workflow node vocabulary to DSH capabilities.

The mapping is declarative only. Step 7 consumes it when compiling Skills; it
does not execute a graph or retain any legacy capability identifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class WorkflowCapabilityBinding:
    node_type: str
    runtime_shape: Literal["tool", "agent_preset", "external_tool"]
    capability_ref: str


WORKFLOW_CAPABILITY_BINDINGS = (
    WorkflowCapabilityBinding("read_material", "tool", "document.parse@v1"),
    WorkflowCapabilityBinding("extract_resources", "tool", "document.extract_resources@v1"),
    WorkflowCapabilityBinding("understand_image", "tool", "vision.extract_facts@v1"),
    WorkflowCapabilityBinding("extract_info", "agent_preset", "dsh.extract_structured@v1"),
    WorkflowCapabilityBinding("compute_metric", "tool", "data.compute_metrics@v1"),
    WorkflowCapabilityBinding("data_collect", "tool", "research.collect_url@v1"),
    WorkflowCapabilityBinding("browser_automation", "tool", "browser.task@v1"),
    WorkflowCapabilityBinding("internal_search", "tool", "knowledge.search@v1"),
    WorkflowCapabilityBinding("external_search", "tool", "research.progressive@v1"),
    WorkflowCapabilityBinding("call_tool", "external_tool", "external.http_mcp@v1"),
    WorkflowCapabilityBinding("script_plugin", "tool", "data.run_script@v1"),
    WorkflowCapabilityBinding("generate_content", "tool", "content.produce@v1"),
    WorkflowCapabilityBinding("translate_rewrite", "tool", "document.transform@v1"),
    WorkflowCapabilityBinding("fill_table", "tool", "artifact.table_generate@v1"),
    WorkflowCapabilityBinding("review_check", "agent_preset", "dsh.review_check@v1"),
    WorkflowCapabilityBinding("export_delivery", "tool", "artifact.export@v1"),
)


def workflow_capability(node_type: str) -> WorkflowCapabilityBinding:
    match = next((item for item in WORKFLOW_CAPABILITY_BINDINGS if item.node_type == node_type), None)
    if match is None:
        raise LookupError(f"workflow node type is not migrated: {node_type}")
    return match
