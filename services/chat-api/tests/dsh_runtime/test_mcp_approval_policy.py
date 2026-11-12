"""MCP calls do not use the retired per-call approval policy."""

from app.dsh_runtime.profile.tools import ToolProfileCompiler
from app.enterprise_capabilities.tools.service import EnterpriseToolService


def test_mcp_tools_skip_approval_even_with_legacy_connection_flag() -> None:
    compiler = ToolProfileCompiler(catalog=None)
    row = {
        "id": "connection-a", "type": "mcp", "name": "Example MCP",
        "config": {"approvalRequired": True},
        "discoveredTools": [{
            "name": "write_record", "description": "Write one record",
            "annotations": {"destructiveHint": True},
            "inputSchema": {"type": "object", "properties": {}},
        }],
    }
    tool = compiler._compile_mcp(row)[0]
    assert tool.risk_level == "dangerous"
    assert tool.approval_required is False
    assert EnterpriseToolService._approval_required(tool.model_copy(update={"approval_required": True}), {}) is False
