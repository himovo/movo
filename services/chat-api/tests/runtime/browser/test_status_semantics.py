from app.enterprise_capabilities.browser.engine.effect_verification.status_semantics import classify_status_text


def test_completed_state_phrases_are_positive_operation_feedback():
    for text in ("已保存", "内容已提交", "草稿已创建。", "图片已上传！", "Comment submitted"):
        assert classify_status_text(text) == "positive"


def test_controls_and_unsaved_state_are_not_success_feedback():
    for text in ("保存为草稿", "提交", "发布", "尚未保存", "未保存"):
        assert classify_status_text(text) != "positive"
