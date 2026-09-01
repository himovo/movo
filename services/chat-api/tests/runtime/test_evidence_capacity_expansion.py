from app.enterprise_capabilities.evidence.foundation.normalizer import EvidenceNormalizer
from app.enterprise_capabilities.evidence.foundation.user_request_fact_extractor import (
    MAX_FACTS,
    MAX_TEXT_CHARS,
    MAX_USER_REQUEST_CHARS,
    _strip_embedded_source_sections,
)
from app.enterprise_capabilities.content.writer_engine.compose_skill import ToolWriterEngineComposeSkill


def test_expanded_user_and_search_limits_are_active():
    assert MAX_USER_REQUEST_CHARS == 20000
    assert MAX_FACTS == 48
    assert MAX_TEXT_CHARS == 500
    assert len(_strip_embedded_source_sections("中" * 25000)) == 20000

    results = EvidenceNormalizer.normalize_results(
        [{"title": f"r{i}", "content": "中" * 8000} for i in range(32)]
    )
    assert len(results) == 32
    assert all(len(item["content"]) == 6000 for item in results)


def test_uploaded_document_capacity_is_balanced_across_ten_documents():
    documents = []
    for doc_index in range(10):
        markdown = "\n".join(
            f"## doc-{doc_index}-section-{section_index}\nbody-{doc_index}-{section_index}"
            for section_index in range(10)
        )
        documents.append(
            {
                "parse_status": "parsed",
                "filename": f"doc-{doc_index}.md",
                "profile": {
                    "title": f"doc-{doc_index}",
                    "summary": f"profile-{doc_index}",
                    "key_points": [f"fact-{doc_index}-{index}" for index in range(10)],
                },
                "chunk_briefs": [
                    {"summary": f"chunk-{doc_index}-{index}", "section_signals": [f"signal-{doc_index}-{index}"]}
                    for index in range(8)
                ],
                "markdown": markdown,
            }
        )

    bundle = ToolWriterEngineComposeSkill._build_document_evidence_bundle(
        output_spec={"documents": {"parsed_documents": documents}},
        base_bundle={},
    )
    rendered = "\n".join(str(item) for item in bundle["results"])

    assert len(bundle["results"]) == 64
    assert len(bundle["confirmed_facts"]) == 48
    assert all(f"doc-{doc_index}" in rendered for doc_index in range(10))


def test_graph_artifact_evidence_uses_full_graph_without_duplicate_predecessor():
    output_spec = {
        "predecessor_artifacts": {
            "N_GENERATE_RISK_MATRIX": {
                "plugin_result": {
                    "data": {
                        "risk_matrix": [
                            {"region": "江苏", "completion_rate": 0.5158, "risk_level": "high"}
                        ]
                    }
                }
            }
        },
        "graph_artifacts": {
            "N_CALL_SALES_MOCKAPI": {
                "business_data": {
                    "target": {
                        "target_amount": 12000000,
                        "actual_amount": 8150000,
                        "completion_rate": 0.6792,
                    }
                }
            },
            "N_GENERATE_RISK_MATRIX": {
                "plugin_result": {
                    "data": {
                        "risk_matrix": [
                            {"region": "江苏", "completion_rate": 0.5158, "risk_level": "high"}
                        ]
                    }
                }
            },
        },
    }

    bundle = ToolWriterEngineComposeSkill._build_graph_artifact_evidence_bundle(
        output_spec=output_spec,
        base_bundle={},
    )
    rendered = "\n".join(str(item) for item in bundle["results"])

    assert bundle["graph_artifact_evidence_count"] == 2
    assert "target_amount" in rendered
    assert "12000000" in rendered
    assert "plugin_result" in rendered
    assert rendered.count("N_GENERATE_RISK_MATRIX graph artifacts") == 1


def test_graph_artifact_evidence_projects_repeated_tool_payload_once_for_writer():
    repeated_rows = [
        {
            "region": f"区域-{index}",
            "actual_amount": index * 10000,
            "target_amount": 200000,
            "completion_rate": 0.5,
            "detail": "销售经营明细" * 60,
        }
        for index in range(80)
    ]
    output_spec = {
        "graph_artifacts": {
            "call_sales_mockapi": {
                "business_data": {"rows": repeated_rows, "period": "current"},
                "business_payload": {
                    "data": {"rows": repeated_rows, "period": "current"},
                    "status": "ok",
                },
                "decoded_payload": {
                    "data": {"rows": repeated_rows, "period": "current"},
                    "debug": "原始调试字段" * 2000,
                },
                "research_bundle": {
                    "results": [{"title": "销售快照", "content": "工具原始结果" * 2000}],
                    "raw_tool_results": [{"tool": "mockapi", "result": repeated_rows}],
                },
                "tool_results": [{"tool": "mockapi", "result": repeated_rows}],
            }
        }
    }

    bundle = ToolWriterEngineComposeSkill._build_graph_artifact_evidence_bundle(
        output_spec=output_spec,
        base_bundle={},
    )
    result = bundle["results"][0]
    rendered = str(result)

    assert bundle["graph_artifact_evidence_count"] == 1
    assert "business_data" in rendered
    assert "completion_rate" in rendered
    assert "business_payload" not in result["structured_payload"]
    assert "decoded_payload" not in result["structured_payload"]
    assert "research_bundle" not in result["structured_payload"]
    assert "tool_results" not in result["structured_payload"]
    assert len(rendered) < 20000
