from app.enterprise_capabilities.browser.engine.action_contracts import describe_for_agent, validate_data
from app.enterprise_capabilities.browser.engine.result_presenter import render_browser_result


def test_read_result_is_included_in_user_facing_answer() -> None:
    answer = render_browser_result(
        summary="读取完成",
        data={
            "result": {
                "title": "示例网站",
                "first_paragraph": "这是正文内容。",
            }
        },
        lang="zh",
    )

    assert "读取完成" in answer
    assert "标题" in answer
    assert "示例网站" in answer
    assert "第一段正文" in answer
    assert "这是正文内容。" in answer


def test_legacy_read_capability_uses_read_contract() -> None:
    hint = describe_for_agent("browser.navigate_and_extract", "zh")

    assert "browser.read" in hint
    assert not validate_data("browser.navigate_and_extract", {}).ok
    assert validate_data(
        "browser.navigate_and_extract",
        {"result": {"name": "真实页面值"}},
    ).ok


def test_operation_confirmation_is_included_in_answer() -> None:
    answer = render_browser_result(
        summary="保存完成",
        data={
            "confirmation": {
                "text": "草稿保存成功",
                "record_id": "draft-42",
            }
        },
        lang="zh",
    )

    assert "保存完成" in answer
    assert "草稿保存成功" in answer
    assert "draft-42" in answer


def test_file_and_delivery_results_are_rendered_without_llm() -> None:
    answer = render_browser_result(
        summary="操作完成",
        data={
            "file": {
                "direction": "download",
                "filename": "report.pdf",
                "path_or_url": "/tmp/report.pdf",
            },
            "delivery": {
                "channel": "wechat_official",
                "destination": "drafts",
            },
        },
        lang="zh",
    )

    assert "report.pdf" in answer
    assert "/tmp/report.pdf" in answer
    assert "wechat_official" in answer
    assert "drafts" in answer


def test_empty_data_preserves_summary_only_behavior() -> None:
    assert render_browser_result(summary="任务完成", data={}, lang="zh") == "任务完成"
