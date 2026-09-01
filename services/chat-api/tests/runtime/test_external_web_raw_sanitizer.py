from app.enterprise_capabilities.evidence.foundation.external_web_raw import sanitize_external_web_raw_text, strip_external_web_raw


def test_strip_external_web_raw_preserves_nested_kb_and_business_payloads():
    value = {
        "source_material": {
            "raw_tool_results": [
                {"tool": "kb_search", "result": {"text": "内部知识库原文"}},
                {"tool": "progressive_research", "result": "网页原始正文"},
            ],
        },
        "business_payload": {"data": [{"customer_id": 42, "url": "https://crm.example.com/42"}]},
    }

    cleaned, removed = strip_external_web_raw(value)

    assert removed == 1
    assert cleaned["source_material"]["raw_tool_results"][0]["tool"] == "kb_search"
    assert cleaned["business_payload"]["data"][0]["customer_id"] == 42
    assert "progressive_research" not in str(cleaned)


def test_rendered_upstream_text_external_raw_is_removed_but_business_data_stays():
    upstream = (
        "【上游节点产出（含具体值，作为写作依据）】\n"
        '  - research_bundle: {"raw_tool_results":[{"tool":"progressive_research","result":"网页原始正文"}],"confirmed_facts":["事实A"]}\n'
        '  - business_payload: {"data":[{"customer_count":42,"url":"https://crm.example.com"}]}\n'
    )

    cleaned, removed = sanitize_external_web_raw_text(upstream)

    assert removed == 1
    assert "progressive_research" not in cleaned
    assert "网页原始正文" not in cleaned
    assert "事实A" in cleaned
    assert "customer_count" in cleaned
