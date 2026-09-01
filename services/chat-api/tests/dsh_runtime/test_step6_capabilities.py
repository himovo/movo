from __future__ import annotations

import asyncio
import json

from app.dsh_runtime.profile.tools import ToolProfileCompiler
from app.enterprise_capabilities.data import MetricsEngine
from app.enterprise_capabilities.data.script import run_script
from app.enterprise_capabilities.tools.result_compaction import compact_tool_result
from app.enterprise_capabilities.browser.result_contract import build_browser_tool_result
from app.enterprise_capabilities.runtime import CapabilityExecutionContext, InternalCapabilityCatalog
from app.enterprise_capabilities.runtime import WORKFLOW_CAPABILITY_BINDINGS
from app.enterprise_capabilities.runtime.adapters import build_default_registry, knowledge_search
from app.enterprise_capabilities.artifacts.references import require_owned_artifact
from app.enterprise_capabilities.browser.service import browser_task


class _EmptyExternalCatalog:
    async def list_enabled(self, tenant_id: str, user_id: str):
        return []


def _context(**turn_context) -> CapabilityExecutionContext:
    return CapabilityExecutionContext(
        tenant_id="tenant-a", user_id="user-a", conversation_id="conversation-a",
        kernel_session_id="session-a", profile_version="profile-a", action_id="action-a",
        turn_context=turn_context,
    )


def test_every_internal_definition_has_exactly_one_handler() -> None:
    definitions = InternalCapabilityCatalog().definitions()
    assert {item.capability_ref for item in definitions} == set(build_default_registry().refs())
    assert len({item.tool_name for item in definitions}) == len(definitions)


def test_internal_catalog_compiles_to_dsh_tools_and_excludes_retired_legacy_tools() -> None:
    async def run():
        return await ToolProfileCompiler(_EmptyExternalCatalog(), InternalCapabilityCatalog()).compile(
            tenant_id="tenant-a", user_id="user-a"
        )

    tools = asyncio.run(run())
    by_name = {item.name: item for item in tools}
    assert by_name["knowledge_search"].source_type == "internal"
    assert by_name["knowledge_search"].capability_ref == "knowledge.search@v1"
    assert "enterprise-specific" in by_name["knowledge_search"].description
    assert "web_search" in by_name["knowledge_search"].description
    assert "progressive_research" in by_name
    assert "evidence is sufficient" in by_name["progressive_research"].description
    assert by_name["pdf_retain_pages"].capability_ref == "document.pdf_retain_pages@v1"
    assert "performs no semantic selection" in by_name["pdf_retain_pages"].description
    assert by_name["browser_task"].approval_required is False
    assert by_name["browser_task"].approval_argument == "operation"
    assert "publish" in by_name["browser_task"].approval_values
    assert by_name["run_script"].idempotent is False
    metric_schema = by_name["compute_metrics"].input_schema
    assert set(metric_schema["properties"]["per_item_calculations"]["items"]["properties"]["type"]["enum"]) == {
        "subtract", "ratio", "rank",
    }
    assert not ({
        "get_current_time", "current_time", "send_email", "send_wechat", "wechat_publish",
        "stock_query", "finance_query", "company_search", "company_registry_search",
    } & set(by_name))


def test_every_existing_workflow_node_type_has_a_real_dsh_binding() -> None:
    expected = {
        "read_material", "extract_resources", "understand_image", "extract_info",
        "compute_metric", "data_collect", "browser_automation", "internal_search",
        "external_search", "call_tool", "script_plugin", "generate_content",
        "translate_rewrite", "fill_table", "review_check", "export_delivery",
    }
    assert {item.node_type for item in WORKFLOW_CAPABILITY_BINDINGS} == expected
    tool_refs = {item.capability_ref for item in InternalCapabilityCatalog().definitions()}
    for binding in WORKFLOW_CAPABILITY_BINDINGS:
        if binding.runtime_shape == "tool":
            assert binding.capability_ref in tool_refs
        elif binding.runtime_shape == "external_tool":
            assert binding.capability_ref == "external.http_mcp@v1"
        else:
            assert binding.capability_ref.startswith("dsh.")
    external_search = next(item for item in WORKFLOW_CAPABILITY_BINDINGS if item.node_type == "external_search")
    assert external_search.capability_ref == "research.progressive@v1"


def test_metrics_engine_preserves_legacy_operations_without_estimation() -> None:
    result = MetricsEngine.compute({
        "records": [
            {"name": "A", "revenue": "1,200", "cost": 800, "status": "won"},
            {"name": "B", "revenue": 600, "cost": 700, "status": "lost"},
        ],
        "calculations": [
            {"name": "revenue_sum", "op": "sum", "field": "revenue"},
            {"name": "won_count", "op": "count_where", "condition": {"field": "status", "op": "eq", "value": "won"}},
            {"name": "won_share", "op": "ratio", "numerator": "won_count", "denominator": "record_count"},
            {"name": "missing", "op": "avg", "field": "not_present"},
        ],
        "per_item_calculations": [{"name": "profit", "op": "subtract", "left": "revenue", "right": "cost"}],
    })
    assert result["computed_metrics"]["revenue_sum"] == 1800
    assert result["computed_metrics"]["won_share"] == 0.5
    assert [row["profit"] for row in result["per_item_metrics"]["profit"]] == [400, -100]
    assert result["uncomputed_metrics"][0]["name"] == "missing"
    assert result["computed_metrics"]["record_count"] == 2


def test_metrics_engine_preserves_legacy_condition_aliases_and_error_rows() -> None:
    result = MetricsEngine.compute({
        "records": [{"amount": "50%", "cost": 0.2}, {"amount": None, "cost": 1}],
        "payload": {"records": [], "source": "https://example.test/a.png"},
        "calculations": [{"name": "low", "op": "count_where", "field": "amount", "lt": 0.75}],
        "per_item_calculations": [{"name": "gap", "op": "subtract", "left": "amount", "right": "cost"}],
    })
    assert result["computed_metrics"]["low"] == 1
    assert result["computed_metrics"]["url_count"] == 1
    assert result["computed_metrics"]["image_count"] == 1
    assert result["per_item_metrics"]["gap"][1]["_calculation_error"] == "invalid_subtract_operands"


def test_metrics_engine_accepts_the_dsh_type_contract_and_per_item_rank() -> None:
    result = MetricsEngine.compute({
        "records": [{"sales": 120}, {"sales": 80}, {"sales": 100}],
        "calculations": [
            {"name": "total", "type": "sum", "field": "sales"},
            {"name": "low", "type": "count_where", "condition": {"field": "sales", "op": "lt", "value": 100}},
        ],
        "per_item_calculations": [{"name": "sales_rank", "type": "rank", "field": "sales", "order": "desc"}],
    })
    assert result["computed_metrics"]["total"] == 300
    assert result["computed_metrics"]["low"] == 1
    assert [row["sales_rank"] for row in result["per_item_metrics"]["sales_rank"]] == [1, 3, 2]
    assert result["uncomputed_metrics"] == []


def test_metrics_engine_accepts_dsh_field_operands_as_record_scoped_calculations() -> None:
    result = MetricsEngine.compute({
        "records": [
            {"target": 100, "actual": 80, "incremental": 60, "cost": 20},
            {"target": 70, "actual": 75, "incremental": 10, "cost": 0},
        ],
        "calculations": [
            {"name": "gap", "type": "subtract", "left": {"field": "target"}, "right": {"field": "actual"}},
            {"name": "roi", "type": "ratio", "numerator": {"field": "incremental"}, "denominator": {"field": "cost"}},
        ],
    })
    assert [row["gap"] for row in result["per_item_metrics"]["gap"]] == [20, -5]
    assert result["per_item_metrics"]["roi"][0]["roi"] == 3
    assert result["per_item_metrics"]["roi"][1]["roi"] is None
    assert result["per_item_metrics"]["roi"][1]["_calculation_error"] == "zero_denominator"
    assert result["uncomputed_metrics"] == []


def test_large_browser_result_preserves_suspension_and_summary() -> None:
    raw = build_browser_tool_result(
        operation="read",
        status="suspended_waiting_approval",
        artifacts={
            "intervention_suspension": {"suspension_id": "susp-1", "run_id": "run-1", "node_id": "node-1"},
            "browser_result": {"summary": "需要登录", "data": {"page": "x" * 200_000}},
        },
        events=[
            {"type": "tool_completed", "content": {"screenshot_base64": "x" * 200_000}},
            {"type": "intervention_required", "content": {"reason": "请完成登录", "category": "login"}},
            {"type": "subagent_done", "content": {"status": "suspended_waiting_approval"}},
        ],
    )
    compacted = compact_tool_result(raw)
    assert len(json.dumps(compacted, ensure_ascii=False).encode()) <= 64 * 1024
    assert compacted["status"] == "suspended_waiting_approval"
    assert compacted["intervention_suspension"]["suspension_id"] == "susp-1"
    assert compacted["responseSummary"] == "需要登录"
    assert any(event.get("type") == "intervention_required" for event in compacted["domain_events"] if isinstance(event, dict))


def test_large_search_result_keeps_real_result_rows_instead_of_empty_summary() -> None:
    compacted = compact_tool_result({
        "success": True,
        "results": [
            {"title": f"Result {index}", "url": f"https://example.test/{index}", "snippet": "内容" * 10_000}
            for index in range(30)
        ],
        "total": 30,
    })
    assert compacted["results"][0]["title"] == "Result 0"
    assert compacted["results"][0]["url"] == "https://example.test/0"
    assert compacted["total"] == 30


def test_failed_browser_terminal_is_not_reported_as_success_from_artifacts() -> None:
    result = build_browser_tool_result(
        operation="read",
        status="failed_terminal",
        artifacts={"browser_receipt": {"status": "failed", "error": "loop exhausted"}},
        events=[{"type": "subagent_done", "content": {"status": "failed_terminal"}}],
    )
    assert result["success"] is False
    assert result["message"] == "loop exhausted"


def test_knowledge_scope_comes_only_from_trusted_turn_context(monkeypatch) -> None:
    calls = []

    class _Result:
        query = "q"
        retrievalMode = "vector"
        total = 0
        items = []

    async def fake_search(**kwargs):
        calls.append(kwargs)
        return _Result()

    monkeypatch.setattr("app.enterprise_capabilities.runtime.adapters.knowledge_retrieval_client.search", fake_search)
    result = asyncio.run(knowledge_search(
        {"query": "q", "knowledge_base_ids": ["model-forged"]},
        _context(knowledge_qa_enabled=True, knowledge_base_ids=["server-selected"]),
    ))
    assert result["success"] is True
    assert calls[0]["knowledge_base_ids"] == ["server-selected"]
    assert calls[0]["main_id"] == "tenant-a"


def test_knowledge_tool_is_available_in_automatic_retrieval_mode(monkeypatch) -> None:
    calls = []

    class _Result:
        query = "internal policy"
        retrievalMode = "vector"
        total = 0
        items = []

    async def fake_search(**kwargs):
        calls.append(kwargs)
        return _Result()

    monkeypatch.setattr("app.enterprise_capabilities.runtime.adapters.knowledge_retrieval_client.search", fake_search)
    result = asyncio.run(knowledge_search(
        {"query": "internal policy"},
        _context(knowledge_qa_enabled=False),
    ))
    assert result["success"] is True
    assert calls[0]["main_id"] == "tenant-a"
    assert calls[0]["knowledge_base_ids"] is None
    assert result["retrieval_status"] == "empty"


def test_knowledge_service_unavailable_is_not_reported_as_zero_results(monkeypatch) -> None:
    from app.knowledge.retrieval.retrieval_client import KnowledgeRetrievalError

    async def unavailable(**_kwargs):
        raise KnowledgeRetrievalError("503 Service Unavailable")

    monkeypatch.setattr("app.enterprise_capabilities.runtime.adapters.knowledge_retrieval_client.search", unavailable)
    result = asyncio.run(knowledge_search({"query": "internal policy"}, _context()))
    assert result["success"] is True
    assert result["retrieval_status"] == "service_unavailable"
    assert result["total"] is None
    assert result["items"] == []
    assert "不代表" in result["message"]


def test_existing_script_sandbox_runs_data_transform_without_network_or_files() -> None:
    result = asyncio.run(run_script({
        "code": "def run(inputs, context):\n    return {'data': {'value': inputs['selected']['data']['value'] * 2}}",
        "data": {"value": 21},
    }, _context()))
    assert result["success"] is True
    assert result["plugin_result"]["data"]["value"] == 42


def test_script_adapter_accepts_ordinary_python_and_returns_stdout() -> None:
    result = asyncio.run(run_script({
        "code": "values = [120 / 133, 80 / 114]\nfor value in values:\n    print(f'{value:.2%}')",
    }, _context()))
    assert result["success"] is True
    assert result["plugin_result"]["data"]["stdout"] == ["90.23%", "70.18%"]


def test_script_contract_requires_explicit_delivery_scope() -> None:
    definition = next(item for item in InternalCapabilityCatalog().definitions() if item.tool_name == "run_script")
    assert set(definition.input_schema["required"]) == {"code", "delivery_scope"}


def test_ordinary_script_cannot_redirect_artifact_scan_by_reassigning_output_dir(monkeypatch) -> None:
    class Storage:
        def upload_bytes_with_path(self, content, user_id, file_name, content_type=None):
            assert content == b'{"ok": true}'
            return "/askai-api/api/files/user-a/generated/result.json", "user-a/generated/result.json"

        def sign_url(self, object_path):
            return f"/askai-api/api/files/{object_path}"

    monkeypatch.setattr("app.enterprise_capabilities.data.script_engine.artifact_export.AliyunOSSUploader", Storage)
    result = asyncio.run(run_script({
        "code": (
            "import os\n"
            "output_dir = '.'\n"
            "with open(os.path.join(output_dir, 'result.json'), 'w', encoding='utf-8') as stream:\n"
            "    stream.write('{\\\"ok\\\": true}')"
        ),
        "delivery_scope": "intermediate",
    }, _context()))
    assert result["documents"][0]["filename"] == "result.json"
    assert result["documents"][0]["lifecycle"] == "intermediate"
    assert result["documents"][0]["visibility"] == "internal"
    assert result["exported_file"]["documents"] == result["documents"]


def test_artifact_reference_cannot_escape_authenticated_user_scope() -> None:
    assert require_owned_artifact({"object_path": "user-a/2026/report.docx", "signed_url": "secret"}, user_id="user-a") == {
        "object_path": "user-a/2026/report.docx"
    }
    try:
        require_owned_artifact({"object_path": "user-b/private.docx"}, user_id="user-a")
    except PermissionError as exc:
        assert "storage scope" in str(exc)
    else:
        raise AssertionError("cross-user artifact access must be rejected")


def test_browser_tool_reuses_checkpoint_and_trusted_resume_signal(monkeypatch) -> None:
    captured = {}

    class _Checkpoint:
        def __init__(self, *, store, task_id, run_id, node):
            captured.update(task_id=task_id, run_id=run_id, node_id=node.node_id)
            self.checkpoint = None
            self.subagent_id = "subagent-1"

        async def open(self):
            captured["opened"] = True

        async def finish(self, status):
            captured["finish"] = status

    class _Executor:
        def __init__(self, user_id, session_id, *, checkpoint_session):
            captured.update(user_id=user_id, browser_session_id=session_id, checkpoint=checkpoint_session)

        async def execute(self, *, node, inputs):
            captured["resume_signal"] = inputs.output_spec["resume_signal"]
            captured["execution_budget_seconds"] = inputs.output_spec["execution_budget_seconds"]
            captured["capability_id"] = node.meta["capability_id"]
            yield {"type": "intervention_required", "content": {"reason": "login"}}, {}
            yield {"type": "subagent_done", "content": {"status": "suspended_waiting_approval"}}, {
                "intervention_suspension": {"suspension_id": "susp-1", "run_id": "run-1", "node_id": node.node_id}
            }

    monkeypatch.setattr("app.enterprise_capabilities.browser.service.agent_registry.get", lambda _user_id: object())
    monkeypatch.setattr("app.enterprise_capabilities.browser.service.BrowserCheckpointSession", _Checkpoint)
    monkeypatch.setattr("app.enterprise_capabilities.browser.service.DesktopAgentBrowserExecutor", _Executor)
    result = asyncio.run(browser_task(
        {"objective": "continue", "operation": "submit"},
        _context(browser_resume={
            "run_id": "run-1", "node_id": "node-1", "browser_session_id": "browser-1",
            "resume_signal": {"type": "human_intervention_completed"},
        }),
    ))
    assert captured["opened"] is True
    assert captured["run_id"] == "run-1"
    assert captured["node_id"] == "node-1"
    assert captured["browser_session_id"] == "browser-1"
    assert captured["resume_signal"] == {"type": "human_intervention_completed"}
    assert captured["execution_budget_seconds"] == 240
    assert captured["capability_id"] == "browser.submit"
    assert "finish" not in captured
    assert result["status"] == "suspended_waiting_approval"
    assert result["intervention_suspension"]["suspension_id"] == "susp-1"


def test_browser_tool_without_terminal_or_artifacts_fails_closed(monkeypatch) -> None:
    captured = {}

    class _Checkpoint:
        def __init__(self, **_kwargs):
            self.checkpoint = None
            self.subagent_id = "subagent-1"

        async def open(self):
            pass

        async def finish(self, status):
            captured["finish"] = status

    class _Executor:
        def __init__(self, *_args, **_kwargs):
            pass

        async def execute(self, **_kwargs):
            if False:
                yield {}, {}

    monkeypatch.setattr("app.enterprise_capabilities.browser.service.agent_registry.get", lambda _user_id: object())
    monkeypatch.setattr("app.enterprise_capabilities.browser.service.BrowserCheckpointSession", _Checkpoint)
    monkeypatch.setattr("app.enterprise_capabilities.browser.service.DesktopAgentBrowserExecutor", _Executor)
    result = asyncio.run(browser_task(
        {"objective": "read", "operation": "read"},
        _context(browser_resume={"run_id": "run-empty", "node_id": "node-empty"}),
    ))
    assert captured["finish"] == "failed_terminal"
    assert result["status"] == "failed_terminal"
    assert result["success"] is False


def test_partial_browser_budget_result_is_a_successful_continuation() -> None:
    result = build_browser_tool_result(
        operation="read",
        status="partial_success",
        artifacts={
            "browser_receipt": {
                "status": "partial_success",
                "summary": "retained observed evidence",
                "continuation_required": True,
            },
            "browser_result": {
                "status": "partial_success",
                "data": {"observed_content": {"text": "fact"}},
            },
        },
        events=[],
    )
    assert result["success"] is True
    assert result["status"] == "partial_success"
    assert result["responseSummary"] == "retained observed evidence"
