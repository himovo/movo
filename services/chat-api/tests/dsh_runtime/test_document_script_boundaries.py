from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from bson import BSON

from app.enterprise_capabilities.artifacts.document_result import public_document_parse_result
from app.enterprise_capabilities.data.script import run_script
from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext
from app.enterprise_capabilities.tools.persistence_codec import restore_json_field, store_json_field
from app.enterprise_capabilities.tools.repository import EnterpriseToolRepository
from app.services.runtime_parse_service import RuntimeParseService


def _context(**turn_context) -> CapabilityExecutionContext:
    return CapabilityExecutionContext(
        tenant_id="tenant-a",
        user_id="user-a",
        conversation_id="conversation-a",
        kernel_session_id="session-a",
        profile_version="profile-a",
        action_id="action-a",
        turn_context=turn_context,
    )


def test_tool_receipt_json_field_round_trips_mongo_unsafe_parser_data() -> None:
    unsafe_result = {
        "structured_content": {
            "body": {"children": [{"$ref": "#/texts/0"}]},
            "origin": {"binary_hash": 10941865328962521312},
        }
    }
    row = store_json_field(
        {
            "schema_version": "askai.enterprise-action-receipt.v1",
            "action_id": "action-a",
            "idempotency_key": "idem-a",
            "tenant_id": "tenant-a",
            "user_id": "user-a",
            "conversation_id": "conversation-a",
            "kernel_session_id": "session-a",
            "profile_version": "profile-a",
            "tool_name": "document_parse",
            "status": "succeeded",
            "result": unsafe_result,
            "error": "",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
        "result",
    )

    BSON.encode(row)
    assert restore_json_field(row, "result")["result"] == unsafe_result
    assert EnterpriseToolRepository._receipt(row).result == unsafe_result


def test_document_result_hides_docling_tree_but_keeps_markdown_contract() -> None:
    raw = {
        "parsed_documents": [{
            "filename": "invoice.pdf",
            "markdown": "# 发票\n金额 216.40 元",
            "structured_content": {"body": {"children": [{"$ref": "#/texts/0"}]}},
            "parse_quality": {"score": 1.0},
        }],
        "documents": {"parsed_documents": [{
            "filename": "invoice.pdf",
            "markdown": "# 发票\n金额 216.40 元",
            "structured_content": {"origin": {"binary_hash": 2**80}},
        }]},
        "active_document_markdown": "# 发票\n金额 216.40 元",
    }

    projected = public_document_parse_result(raw)

    assert projected["parsed_documents"][0]["markdown"].endswith("216.40 元")
    assert "structured_content" not in projected["parsed_documents"][0]
    assert "parsed_documents" not in projected["documents"]
    assert "active_document_markdown" not in projected["documents"]


def test_object_path_alone_is_recognized_and_normalized_as_document() -> None:
    artifact = {"object_path": "user-a/2026/08/invoice.pdf"}
    assert RuntimeParseService._looks_like_document(artifact) is True
    assert RuntimeParseService._normalize_file(artifact)["filename"] == "invoice.pdf"


def test_every_script_invocation_inherits_turn_file_and_prints_utf8(monkeypatch) -> None:
    content = "中文附件内容：金额 216.40 元"
    monkeypatch.setattr(
        "app.enterprise_capabilities.data.script_engine.executor.AliyunOSSUploader.read_bytes",
        lambda _self, object_path: content.encode("utf-8"),
    )
    context = _context(documents=[{
        "object_path": "user-a/2026/08/invoice.txt",
        "filename": "中文发票.txt",
        "content_type": "text/plain",
    }])
    arguments = {
        "code": "with open(input_files[0]['local_path'], encoding='utf-8') as f:\n    print(f.read())",
    }

    first = asyncio.run(run_script(arguments, context))
    second = asyncio.run(run_script(arguments, context))

    assert first["plugin_result"]["data"]["stdout"] == [content]
    assert second["plugin_result"]["data"]["stdout"] == [content]


def test_script_error_summary_preserves_actionable_exception_tail(monkeypatch) -> None:
    from app.enterprise_capabilities.data.script_engine.error_summary import execution_error_summary

    error = RuntimeError("prefix " + "x" * 1200 + "\nFileNotFoundError: inputs/invoice.pdf")
    summary = execution_error_summary(error, max_chars=300)

    assert len(summary) <= 300
    assert summary.endswith("FileNotFoundError: inputs/invoice.pdf")
