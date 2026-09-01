from app.enterprise_capabilities.evidence.foundation.writer_packet import WriterEvidencePacketBuilder
from app.enterprise_capabilities.evidence.foundation.writer_packet import shadow as shadow_module


def _build(*, bundle=None, observations=None, output_spec=None, user_query=""):
    return WriterEvidencePacketBuilder().build(
        evidence_bundle=bundle or {},
        tool_observations=observations or [],
        output_spec=output_spec or {},
        user_query=user_query,
    )


def test_writer_packet_keeps_compact_web_sources_without_raw_web_body():
    raw_body = "外部网页全文" * 2000
    packet = _build(
        bundle={
            "results": [
                {
                    "tool": "progressive_research",
                    "title": "门店经营趋势",
                    "summary": "线下门店转化率承压。",
                    "content": raw_body,
                    "source_url": "https://example.com/store-report",
                }
            ],
            "confirmed_facts": ["线下门店转化率承压。"],
            "raw_tool_results": [{"tool": "progressive_research", "result": raw_body}],
        }
    )

    rendered = packet.model_dump_json()
    assert "https://example.com/store-report" in rendered
    assert "线下门店转化率承压" in rendered
    assert raw_body not in rendered
    assert packet.coverage.complete is True


def test_writer_packet_does_not_misclassify_business_tool_with_url_as_web_raw():
    packet = _build(
        observations=[
            {
                "tool": "external_crm_query",
                "source_url": "https://crm.example.com/customers/42",
                "result": {"customer_id": 42, "status": "active"},
            }
        ]
    )

    assert packet.business_datasets[0]["data"]["customer_id"] == 42
    assert "business_tool" in packet.coverage.source_types
    assert packet.coverage.source_types["web"].input_records == 0
    assert not any(item.get("source_url") == "https://crm.example.com/customers/42" for item in packet.citations)


def test_writer_packet_preserves_kb_excerpt_and_citation_coordinates():
    packet = _build(
        bundle={
            "results": [
                {
                    "tool": "kb_search",
                    "title": "内部制度",
                    "summary": "退款需要二级审批。",
                    "content": "退款需要二级审批。",
                    "source": "内部知识库",
                    "meta": {
                        "provider": "internal_knowledge_qa",
                        "usedChunks": [
                            {
                                "citationId": "cite-1",
                                "documentId": "doc-1",
                                "chunkId": "chunk-3",
                                "title": "退款制度",
                                "text": "单笔退款超过一万元时，需要区域经理二级审批。",
                                "pageNo": 4,
                            }
                        ],
                    },
                }
            ]
        }
    )

    assert packet.source_excerpts[0]["content"] == "单笔退款超过一万元时，需要区域经理二级审批。"
    assert packet.citations[0]["document_id"] == "doc-1"
    assert packet.citations[0]["chunk_id"] == "chunk-3"
    assert packet.citations[0]["page_no"] == 4


def test_writer_packet_uses_complete_mcp_raw_instead_of_truncated_summary():
    rows = [{"customer_id": index, "amount": index * 100} for index in range(120)]
    packet = _build(
        bundle={
            "raw_tool_results": [
                {
                    "tool": "external_mcp_crm_list_customers_abcd1234",
                    "result": {
                        "ok": True,
                        "results": [
                            {
                                "title": "CRM/list_customers",
                                "content": "摘要内容"[:4000],
                                "meta": {
                                    "providerType": "mcp",
                                    "mcpToolName": "list_customers",
                                },
                            }
                        ],
                        "raw": {"rows": rows, "total": len(rows)},
                    },
                }
            ]
        }
    )

    assert packet.business_datasets[0]["data"]["mcp_raw"]["total"] == 120
    assert packet.business_datasets[0]["data"]["mcp_raw"]["rows"][-1]["customer_id"] == 119
    assert packet.business_datasets[0]["provenance"]["mcp_tool_name"] == "list_customers"


def test_writer_packet_separates_metrics_and_deduplicates_graph_artifacts():
    graph_result = {
        "title": "calculate graph artifacts",
        "summary": "浦东店完成率最低。",
        "source": "graph_artifact:graph_artifacts",
        "structured_payload": {
            "computed_metrics": {"pudong_completion_rate": 0.62},
            "metric_table": [{"store": "浦东店", "completion_rate": 0.62}],
        },
    }
    packet = _build(bundle={"results": [graph_result, dict(graph_result)]})

    assert len(packet.computed_metrics) == 1
    assert packet.computed_metrics[0]["metrics"]["computed_metrics"]["pudong_completion_rate"] == 0.62
    assert packet.coverage.source_types["graph"].deduplicated_materials >= 1


def test_writer_packet_exposes_tool_failures_and_unsupported_records():
    packet = _build(
        bundle={
            "raw_tool_results": [
                {"tool": "external_crm_query", "result": {"ok": False, "message": "CRM unavailable"}},
                {"tool": "unknown_tool", "opaque_handle": object()},
            ]
        }
    )

    assert packet.execution_failures[0]["tool"] == "external_crm_query"
    assert packet.execution_failures[0]["error"] == "CRM unavailable"
    assert packet.coverage.complete is False
    assert packet.coverage.unsupported_records[0]["tool"] == "unknown_tool"


def test_writer_packet_preserves_generic_tool_list_and_string_results():
    packet = _build(
        bundle={
            "raw_tool_results": [
                {"tool": "customer_list", "result": [{"customer_id": 1}, {"customer_id": 2}]},
                {"tool": "legacy_status", "result": "系统当前处于只读维护状态"},
            ]
        }
    )

    assert packet.business_datasets[0]["data"]["result"][-1]["customer_id"] == 2
    assert any(item["summary"] == "系统当前处于只读维护状态" for item in packet.evidence_items)


def test_writer_packet_does_not_repeat_json_graph_summary_beside_structured_metrics():
    packet = _build(
        bundle={
            "results": [
                {
                    "title": "metrics graph artifacts",
                    "source": "graph_artifact:graph_artifacts",
                    "summary": '{"computed_metrics":{"completion_rate":0.62}}',
                    "structured_payload": {"computed_metrics": {"completion_rate": 0.62}},
                }
            ]
        }
    )

    assert packet.computed_metrics[0]["metrics"]["computed_metrics"]["completion_rate"] == 0.62
    assert packet.evidence_items == []
    assert packet.coverage.suppressed_duplicate_representations == 1


def test_writer_packet_keeps_structured_runtime_values_once_and_never_as_facts():
    truncated_json = '{"business_data":{"records":[{"id":1}]}}...<truncated>'
    packet = _build(
        bundle={
            "confirmed_facts": [truncated_json, "门店数据统计周期为六月。", "[注意] 缺失数据须标注待确认。"],
            "results": [
                {
                    "title": "graph artifact",
                    "source": "graph_artifact:graph_artifacts",
                    "summary": truncated_json,
                    "structured_payload": {"business_data": {"records": [{"id": 1}]}},
                }
            ],
        }
    )

    assert packet.confirmed_facts == ["门店数据统计周期为六月。", "[注意] 缺失数据须标注待确认。"]
    assert len(packet.business_datasets) == 1
    assert packet.evidence_items == []
    assert packet.coverage.filtered_structured_facts == 1
    assert packet.coverage.suppressed_duplicate_representations == 1


def test_writer_packet_keeps_subject_user_facts_and_multimodal_facts():
    packet = _build(
        bundle={
            "confirmed_facts": ["浦东店完成率最低。"],
            "user_request_facts": [{"text": "用户确认统计周期为六月。"}],
            "open_questions": ["促销活动是否执行？"],
        },
        output_spec={
            "subject_resolution": {"canonical_subject": "浦东店", "status": "resolved"},
            "multimodal": {
                "image_facts": {
                    "cross_image_facts": ["截图中浦东店状态为预警。"],
                    "uncertain": ["截图日期不可见。"],
                }
            },
        },
    )

    assert packet.subject["canonical_subject"] == "浦东店"
    assert "用户确认统计周期为六月。" in packet.confirmed_facts
    assert packet.open_questions == ["促销活动是否执行？"]
    assert {item["kind"] for item in packet.multimodal_facts} == {"cross_image_facts", "uncertain"}


def test_writer_packet_marks_web_source_loss_as_incomplete_instead_of_hiding_it():
    packet = _build(
        bundle={
            "results": [
                {
                    "tool": "progressive_research",
                    "title": f"source-{index}",
                    "summary": f"fact-{index}",
                    "source_url": f"https://example.com/{index}",
                }
                for index in range(21)
            ]
        }
    )

    assert packet.coverage.complete is False
    assert packet.coverage.truncated is True
    assert any("external-web" in note for note in packet.coverage.notes)


def test_writer_packet_marks_kb_citation_loss_as_incomplete():
    chunks = [
        {
            "documentId": "doc-1",
            "chunkId": f"chunk-{index}",
            "text": f"知识片段-{index}",
        }
        for index in range(13)
    ]
    packet = _build(
        bundle={
            "results": [
                {
                    "tool": "kb_search",
                    "title": "内部知识",
                    "summary": "知识库结论",
                    "meta": {"provider": "internal_knowledge_qa", "usedChunks": chunks},
                }
            ]
        }
    )

    assert packet.coverage.complete is False
    assert packet.coverage.truncated is True
    assert len(packet.citations) == 12
    assert any("KB citation" in note for note in packet.coverage.notes)


def test_writer_packet_preserves_agreement_grounding_materials():
    packet = _build(
        bundle={"agreement_template_markdown": "# 合同\n第八条：违约责任。"},
    )

    assert packet.source_excerpts[0]["kind"] == "agreement_template"
    assert "第八条" in packet.source_excerpts[0]["content"]


def test_writer_packet_preserves_user_source_document_sections_without_raw_prompt_append():
    packet = _build(
        user_query="请按原文改写。\n[SOURCE_DOCUMENT]\n第一条：付款期限为30日。",
    )

    assert packet.source_excerpts[0]["kind"] == "user_source_section"
    assert "付款期限为30日" in packet.source_excerpts[0]["content"]


def test_writer_packet_shadow_persists_full_packet_but_does_not_claim_prompt_usage(monkeypatch):
    captured = {}

    def fake_write(domain, name, payload):
        captured.update({"domain": domain, "name": name, "payload": payload})
        return "static/debug_snapshots/writer_evidence_packet/test/packet.json"

    monkeypatch.setattr(shadow_module, "write_debug_artifact", fake_write)
    summary = shadow_module.build_writer_evidence_packet_shadow(
        evidence_bundle={"confirmed_facts": ["浦东店完成率最低。"]},
        tool_observations=[],
        output_spec={"subject_resolution": {"canonical_subject": "浦东店"}},
    )

    assert summary["mode"] == "shadow_only_not_sent_to_llm"
    assert summary["artifact_path"].endswith("packet.json")
    assert captured["domain"] == "writer_evidence_packet"
    assert captured["payload"]["packet"]["confirmed_facts"] == ["浦东店完成率最低。"]
