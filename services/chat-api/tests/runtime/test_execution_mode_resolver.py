from app.enterprise_capabilities.content.execution_mode import ExecutionModeResolver


def _resolve(
    *,
    write_mode="auto",
    content_form="report",
    min_words=1500,
    max_words=3000,
    required_blocks=None,
    semantic_profile=None,
    assembly_profile=None,
):
    compose_policy = {
        "write_mode": write_mode,
        "content_form": content_form,
    }
    if semantic_profile is not None:
        compose_policy["delivery_profile"] = {"semantic_profile": semantic_profile}
    if assembly_profile is not None:
        compose_policy["assembly_profile"] = assembly_profile
    return ExecutionModeResolver().resolve(
        compose_policy=compose_policy,
        structure_contract={"required_blocks": required_blocks or ["概述", "介绍", "对比", "总结"]},
        quality_gates={"min_words": min_words, "max_words": max_words},
        evidence_policy={},
        prompt_contract={},
        user_query="生成一份竞品分析报告",
    )


def test_explicit_document_scale_short_report_demotes_to_single_pass():
    decision = _resolve(
        write_mode="document_scale",
        content_form="report",
        min_words=1500,
        max_words=3000,
        required_blocks=["报告概述", "产品介绍", "对比表格", "总结"],
    )

    assert decision.mode == "direct_compose"
    assert "explicit_document_scale_requires_large_scope" in decision.reasons


def test_explicit_document_scale_large_word_budget_is_preserved():
    decision = _resolve(
        write_mode="document_scale",
        content_form="report",
        min_words=8000,
        max_words=10000,
        required_blocks=["概述", "市场", "产品", "能力", "价格", "风险"],
    )

    assert decision.mode == "document_scale_compose"
    assert decision.reasons == ["explicit_write_mode=document_scale_compose"]


def test_explicit_document_scale_many_sections_medium_budget_is_preserved():
    decision = _resolve(
        write_mode="document_scale",
        content_form="report",
        min_words=5000,
        max_words=6000,
        required_blocks=["一", "二", "三", "四", "五", "六"],
    )

    assert decision.mode == "document_scale_compose"


def test_whitepaper_document_scale_is_preserved_with_meaningful_budget():
    decision = _resolve(
        write_mode="document_scale",
        content_form="whitepaper",
        min_words=4000,
        max_words=5000,
        required_blocks=["背景", "现状", "方案", "路线"],
    )

    assert decision.mode == "document_scale_compose"


def test_semantic_document_scale_short_report_cannot_route_back_to_document_scale():
    decision = _resolve(
        write_mode="auto",
        content_form="report",
        min_words=1500,
        max_words=3000,
        required_blocks=["报告概述", "产品介绍", "对比表格", "总结"],
        semantic_profile={
            "document_scale": True,
            "single_pass_feasible": True,
            "recommended_execution_mode": "document_scale_compose",
            "section_independence": "high",
            "audience_consumption_mode": "reference_read",
        },
    )

    assert decision.mode == "direct_compose"
    assert "semantic_document_scale_requires_large_scope" in decision.reasons
