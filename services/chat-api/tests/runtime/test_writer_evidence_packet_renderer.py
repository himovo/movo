from app.enterprise_capabilities.evidence.foundation.writer_packet import (
    WriterEvidencePacket,
    build_writer_packet_source_references,
    render_section_writer_evidence_packet,
    render_writer_evidence_packet,
)
from app.enterprise_capabilities.content.writer_engine.unified_compose.components import SinglePassWriter


def test_renderer_emits_every_writer_facing_packet_channel():
    packet = WriterEvidencePacket.model_validate(
        {
            "subject": {"canonical_subject": "浦东店", "supporting_facts": ["统计周期为六月"]},
            "confirmed_facts": ["浦东店完成率为68%。"],
            "business_datasets": [
                {
                    "title": "门店快照",
                    "data": {"stores": [{"name": "浦东店", "sales": 1020000}]},
                    "provenance": {"source_type": "mcp", "tool": "store_snapshot"},
                }
            ],
            "computed_metrics": [
                {"title": "风险指标", "metrics": {"risk_level": "high"}, "provenance": {"source_type": "graph"}}
            ],
            "source_excerpts": [
                {
                    "title": "内部制度第3条",
                    "content": "活动ROI低于1.2需要复盘。",
                    "document_id": "doc-1",
                    "chunk_id": "chunk-3",
                }
            ],
            "citations": [{"title": "制度引用", "document_id": "doc-1", "chunk_id": "chunk-3", "page_no": 4}],
            "open_questions": ["缺少七月排班数据。"],
            "execution_failures": [{"source_type": "tool", "tool": "weather", "error": "service unavailable"}],
            "coverage": {"complete": True, "truncated": False},
        }
    )

    markdown = render_writer_evidence_packet(packet)

    for expected in (
        "Writer Evidence Packet",
        "浦东店完成率为68%。",
        "1020000",
        "risk_level",
        "活动ROI低于1.2需要复盘。",
        "doc-1 | chunk-3 | 4",
        "缺少七月排班数据。",
        "service unavailable",
        "coverage_complete: true",
    ):
        assert expected in markdown


def test_renderer_does_not_render_runtime_raw_bundle_wrappers():
    packet = WriterEvidencePacket.model_validate(
        {
            "business_datasets": [{"title": "业务数据", "data": {"customer_count": 42}}],
            "coverage": {"complete": True, "truncated": False},
        }
    )

    markdown = render_writer_evidence_packet(packet)

    assert "customer_count" in markdown
    assert "raw_tool_results" not in markdown
    assert "_last_idempotency_key" not in markdown


def test_single_pass_variants_use_packet_renderer_instead_of_old_evidence_formatter():
    packet = WriterEvidencePacket.model_validate(
        {
            "confirmed_facts": ["浦东店完成率为68%。"],
            "business_datasets": [{"title": "门店快照", "data": {"sales": 1020000}}],
            "computed_metrics": [{"title": "指标", "metrics": {"risk": "high"}}],
            "coverage": {"complete": True, "truncated": False},
        }
    )
    evidence_markdown = render_writer_evidence_packet(packet)

    variants = SinglePassWriter._build_user_variants(
        writer_task={"user_goal": "分析浦东店表现"},
        writer_constraints={},
        publish_narrative_block="",
        must_include_block="",
        fewshot_block="",
        selected_style_md="",
        packet_evidence_markdown=evidence_markdown,
    )

    assert variants
    assert all("Writer Evidence Packet" in variant for variant in variants)
    assert all("1020000" in variant and '"risk": "high"' in variant for variant in variants)
    assert all("SOURCE_EVIDENCE" not in variant for variant in variants)


def test_section_writer_uses_the_packet_and_packet_provenance_only():
    packet = WriterEvidencePacket.model_validate(
        {
            "confirmed_facts": ["事实A"],
            "source_excerpts": [{"title": "研究报告", "source_url": "https://example.com/report", "content": "摘录"}],
            "citations": [{"title": "研究报告", "source_url": "https://example.com/report"}],
            "coverage": {"complete": True, "truncated": False},
        }
    )

    markdown = render_section_writer_evidence_packet(packet)
    refs = build_writer_packet_source_references(packet)

    assert markdown == render_writer_evidence_packet(packet)
    assert "事实A" in markdown
    assert refs == [{"index": 1, "title": "研究报告", "url": "https://example.com/report"}]
