from app.enterprise_capabilities.browser.engine.contexts.general import GeneralBrowserContext
from app.enterprise_capabilities.browser.engine.contexts.operation_contract import BrowserOperationContract
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def _node(operation: str) -> CapabilityTask:
    return CapabilityTask(
        node_id=f"op-{operation}",
        goal="test",
        assigned_agent="agent.browser",
        meta={"capability_id": f"browser.{operation}"},
    )


def _context(operation: str, goal: str) -> GeneralBrowserContext:
    return GeneralBrowserContext(
        lang="zh",
        node=_node(operation),
        goal=goal,
        original_user_request=goal,
    )


def test_read_operation_cannot_be_promoted_by_write_words_in_objective() -> None:
    context = _context("read", "读取帖子正文，查看评论区、评论框和是否可以发表评论")
    assert "commit" not in context.requirements
    assert {"navigate", "read"}.issubset(context.requirements)


def test_write_operation_requires_commit_without_keyword_guessing() -> None:
    context = _context("submit", "处理当前表单")
    assert "commit" in context.requirements


def test_navigate_operation_has_bounded_completion_contract() -> None:
    context = _context("navigate", "打开页面并查看评论区是否可用")
    assert context.requirements == {"navigate"}


def test_read_operation_blocks_form_edit_but_allows_confirmed_search_fill() -> None:
    context = _context("read", "搜索 AI 知识库并读取结果")
    page = Observation(
        url="https://example.test/search",
        title="Search",
        elements=[
            {"ref": "search", "role": "searchbox", "name": "搜索"},
            {"ref": "comment", "role": "textbox", "name": "写评论"},
        ],
    )
    allowed = context.validate_action(
        Decision(tool="browser_fill", args={"ref": "search", "value": "AI 知识库"}),
        page,
    )
    blocked = context.validate_action(
        Decision(tool="browser_fill", args={"ref": "comment", "value": "hello"}),
        page,
    )
    assert allowed[0] == "allow"
    assert blocked[0] == "reject"


def test_operation_contract_preserves_untyped_legacy_requirement_inference() -> None:
    contract = BrowserOperationContract.from_node(CapabilityTask(
        node_id="legacy", goal="legacy", assigned_agent="agent.browser", meta={}
    ))
    assert contract.constrain_requirements({"read", "commit"}) == {
        "navigate", "read", "commit",
    }


def test_operation_contract_is_rederived_instead_of_serialized_in_checkpoint() -> None:
    context = _context("read", "读取评论区状态")
    payload = context.export_checkpoint_state()
    assert "operation_contract" not in payload["state"]
    restored = _context("read", "读取评论区状态")
    restored.restore_checkpoint_state(payload)
    assert restored.operation_contract.operation == "read"
    assert "commit" not in restored.requirements
