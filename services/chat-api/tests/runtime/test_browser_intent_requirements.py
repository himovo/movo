import pytest

from app.enterprise_capabilities.browser.engine.contexts.intent_requirements import compile_general_requirements


@pytest.mark.parametrize("goal", [
    "打开百度搜索 AskBot，然后返回搜索结果页面的文本内容",
    "获取页面并返回标题和摘要",
    "搜索后返回结果列表给用户",
    "Search AskBot and return the result titles and content",
])
def test_output_return_does_not_require_browser_history(goal: str) -> None:
    assert "return" not in compile_general_requirements(goal)


@pytest.mark.parametrize("goal", [
    "打开详情后返回到搜索结果页面",
    "查看详情后回到列表页",
    "查看完成后返回上一页",
    "Open the result and then go back to the search page",
    "Open the detail and return to the list",
])
def test_explicit_navigation_return_requires_browser_history(goal: str) -> None:
    assert "return" in compile_general_requirements(goal)


def test_askbot_read_goal_compiles_only_real_evidence_requirements() -> None:
    requirements = compile_general_requirements(
        "打开百度搜索页面，搜索 AskBot，返回搜索结果页面内容用于总结"
    )
    assert requirements == {"navigate", "search", "read"}


@pytest.mark.parametrize("goal", [
    "在搜索框输入 AskBot 并点击搜索，然后返回搜索结果内容",
    "点击搜索按钮查看结果并总结",
    "Click the search button and read the results",
    "Click search and return the result titles",
])
def test_submitting_search_does_not_require_opening_a_result(goal: str) -> None:
    assert "open_result" not in compile_general_requirements(goal)


@pytest.mark.parametrize("goal", [
    "点击第一个搜索结果并读取详情",
    "打开搜索结果中的第一条链接",
    "Click the first search result and read the detail",
])
def test_explicit_result_selection_requires_opening_a_result(goal: str) -> None:
    assert "open_result" in compile_general_requirements(goal)


@pytest.mark.parametrize("goal", [
    "打开小红书搜索 AI 知识库的结果页面，读取页面上可见的帖子标题及点赞数",
    "进入站内检索结果页，列出前十条内容",
    "Open the search results page and list the visible titles",
    "Browse the query result list and summarize the visible posts",
])
def test_opening_result_surface_does_not_require_opening_detail(goal: str) -> None:
    assert "open_result" not in compile_general_requirements(goal)


@pytest.mark.parametrize("goal", [
    "搜索完成后浏览结果页，不要点击进入任何笔记详情页，只返回列表信息",
    "请勿打开搜索结果中的帖子，只读取当前列表",
    "禁止进入任何详情页，返回搜索结果标题",
    "无需打开任何链接，只查看搜索结果页面",
    "Do not open any result detail; only return the search result list",
    "Never click a post or link, just read the visible results",
])
def test_negated_result_selection_does_not_require_opening_detail(goal: str) -> None:
    assert "open_result" not in compile_general_requirements(goal)


@pytest.mark.parametrize("goal", [
    "不要打开第一条结果，点击第二条搜索结果并读取详情",
    "Do not open the first result; open the second search result and read it",
])
def test_negated_clause_does_not_hide_later_positive_selection(goal: str) -> None:
    assert "open_result" in compile_general_requirements(goal)
