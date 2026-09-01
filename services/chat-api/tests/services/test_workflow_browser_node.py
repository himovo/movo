from app.services.workflow_browser_node import (
    browser_node_capability,
    browser_node_objective,
    browser_node_target_name,
    browser_node_target_reference,
    browser_node_target_url,
)


def test_browser_node_capability_keeps_draft_save_as_submit() -> None:
    assert browser_node_capability("进入草稿箱，添加文章并保存草稿，不要发布") == "browser.submit"


def test_browser_node_capability_distinguishes_read_and_publish() -> None:
    assert browser_node_capability("查询客户合同和回款信息") == "browser.read"
    assert browser_node_capability("将文章发布到微信公众号") == "browser.publish"


def test_browser_node_capability_honors_internal_override() -> None:
    assert browser_node_capability("执行网页操作", {"capabilityId": "browser.modify"}) == "browser.modify"


def test_browser_node_target_url_accepts_frontend_shape() -> None:
    assert browser_node_target_url({"targetUrl": "https://example.com/path"}) == "https://example.com/path"


def test_browser_node_target_name_and_url_form_execution_context() -> None:
    config = {"targetName": "OA", "targetUrl": "https://oa.example.com/"}

    assert browser_node_target_name(config) == "OA"
    assert browser_node_target_reference(config) == "[目标系统: OA (https://oa.example.com/)]"
    assert browser_node_objective("查询待办流程", config) == (
        "[目标系统: OA (https://oa.example.com/)]\n\n查询待办流程"
    )


def test_browser_node_target_name_works_without_url() -> None:
    assert browser_node_target_reference({"targetName": "OA"}) == "[目标系统: OA]"
