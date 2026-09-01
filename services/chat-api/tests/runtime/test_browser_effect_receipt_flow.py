from app.enterprise_capabilities.browser.engine.contexts.general import GeneralBrowserContext
from app.enterprise_capabilities.browser.engine.contexts.null import NullContext
from app.enterprise_capabilities.browser.engine.effect_receipt_flow import (
    applied_effect_now_completes_goal,
    apply_effect_receipt,
    build_effect_completion,
    build_effect_failure,
)
from app.enterprise_capabilities.browser.engine.effect_business_failure import (
    build_effect_business_failure,
    build_effect_business_failure_events,
)
from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectReceipt
from app.enterprise_capabilities.browser.engine.effect_task_outcome import EffectTaskOutcome
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _receipt(
    status: str,
    *,
    contract_key: str = "comment-1",
    completes_goal: bool = True,
) -> EffectReceipt:
    return EffectReceipt(
        contract_key=contract_key,
        status=status,
        confidence=0.95,
        action_name="发布评论",
        operation_family="publish",
        completes_goal=completes_goal,
    )


def test_delayed_success_receipt_updates_general_mission_and_completes_goal():
    goal = "搜索一个相关帖子，打开详情并发表评论"
    context = GeneralBrowserContext(
        lang="zh",
        node=CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser"),
        goal=goal,
        original_user_request=goal,
    )
    context.completed.update({"navigate", "search", "open_result"})
    observation = Observation(
        url="https://example.test/post/1",
        title="Post",
        page_text="评论成功",
        elements=[],
    )

    pending = apply_effect_receipt(
        context=context,
        tracks_context_state=True,
        receipt=_receipt("unknown"),
        observation=observation,
    )
    confirmed = apply_effect_receipt(
        context=context,
        tracks_context_state=True,
        receipt=_receipt("confirmed_success"),
        observation=observation,
    )

    assert pending.goal_completed is False
    assert context.mission.confirmed_effects == 1
    assert confirmed.goal_completed is True
    assert context.ready_to_done() is True


def test_applied_effect_completes_after_later_context_milestone():
    goal = "搜索一个相关帖子，打开详情并发表评论"
    context = GeneralBrowserContext(
        lang="zh",
        node=CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser"),
        goal=goal,
        original_user_request=goal,
    )
    context.completed.update({"navigate", "search"})
    receipt = _receipt("confirmed_success", completes_goal=False)
    observation = Observation(
        url="https://example.test/post/1", title="Post", elements=[],
    )

    first_check = apply_effect_receipt(
        context=context,
        tracks_context_state=True,
        receipt=receipt,
        observation=observation,
    )
    assert first_check.goal_completed is False

    context.completed.add("open_result")

    assert applied_effect_now_completes_goal(
        context=context,
        tracks_context_state=True,
        receipt=receipt,
    ) is True


def test_single_operation_general_mission_uses_ledger_when_receipt_is_not_task_terminal():
    goal = "搜索一个相关帖子，打开详情并发表评论"
    context = GeneralBrowserContext(
        lang="zh",
        node=CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser"),
        goal=goal,
        original_user_request=goal,
    )
    context.completed.update({"navigate", "search", "open_result"})

    result = apply_effect_receipt(
        context=context,
        tracks_context_state=True,
        receipt=_receipt("confirmed_success", completes_goal=False),
        observation=Observation(url="https://example.test/post/1", title="Post", elements=[]),
    )

    assert context.mission.confirmed_effects == 1
    assert context.ready_to_done() is True
    assert result.goal_completed is True


def test_multi_operation_general_mission_completes_on_second_distinct_success():
    goal = "搜索多个相关帖子，打开详情并分别发表评论"
    context = GeneralBrowserContext(
        lang="zh",
        node=CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser"),
        goal=goal,
        original_user_request=goal,
    )
    context.completed.update({"navigate", "search", "open_result"})
    observation = Observation(url="https://example.test/post/1", title="Post", elements=[])

    first = apply_effect_receipt(
        context=context,
        tracks_context_state=True,
        receipt=_receipt("confirmed_success", contract_key="comment-1", completes_goal=False),
        observation=observation,
    )
    context.completed.add("open_result")
    second = apply_effect_receipt(
        context=context,
        tracks_context_state=True,
        receipt=_receipt("confirmed_success", contract_key="comment-2", completes_goal=False),
        observation=observation,
    )

    assert first.goal_completed is False
    assert second.goal_completed is True
    assert context.mission.confirmed_effects == 2


def test_multi_operation_general_mission_deduplicates_same_success_receipt():
    goal = "搜索多个相关帖子，打开详情并分别发表评论"
    context = GeneralBrowserContext(
        lang="zh",
        node=CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser"),
        goal=goal,
        original_user_request=goal,
    )
    context.completed.update({"navigate", "search", "open_result"})
    observation = Observation(url="https://example.test/post/1", title="Post", elements=[])
    receipt = _receipt("confirmed_success", contract_key="comment-1", completes_goal=False)

    first = apply_effect_receipt(
        context=context, tracks_context_state=True, receipt=receipt, observation=observation,
    )
    replay = apply_effect_receipt(
        context=context, tracks_context_state=True, receipt=receipt, observation=observation,
    )

    assert first.goal_completed is False
    assert replay.goal_completed is False
    assert context.mission.confirmed_effects == 1


def test_stateless_context_keeps_legacy_receipt_completion_semantics():
    observation = Observation(url="https://example.test", title="Page", elements=[])

    non_terminal = apply_effect_receipt(
        context=NullContext(),
        tracks_context_state=False,
        receipt=_receipt("confirmed_success", completes_goal=False),
        observation=observation,
    )
    terminal = apply_effect_receipt(
        context=NullContext(),
        tracks_context_state=False,
        receipt=_receipt("confirmed_success", completes_goal=True),
        observation=observation,
    )

    assert non_terminal.goal_completed is False
    assert terminal.goal_completed is True


def test_general_single_write_without_search_completes_after_one_success():
    goal = "打开通知页面并发送一条通知"
    context = GeneralBrowserContext(
        lang="zh",
        node=CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser"),
        goal=goal,
        original_user_request=goal,
    )
    context.completed.add("navigate")

    result = apply_effect_receipt(
        context=context,
        tracks_context_state=True,
        receipt=_receipt("confirmed_success", completes_goal=False),
        observation=Observation(url="https://example.test/notifications", title="Notifications", elements=[]),
    )

    assert context.mission.minimum_effects == 1
    assert context.mission.confirmed_effects == 1
    assert result.goal_completed is True


def test_general_multi_write_without_search_waits_for_two_distinct_successes():
    goal = "打开通知页面，分别给多个账号发送通知"
    context = GeneralBrowserContext(
        lang="zh",
        node=CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser"),
        goal=goal,
        original_user_request=goal,
    )
    context.completed.add("navigate")
    observation = Observation(url="https://example.test/notifications", title="Notifications", elements=[])

    first = apply_effect_receipt(
        context=context,
        tracks_context_state=True,
        receipt=_receipt("confirmed_success", contract_key="notice-1", completes_goal=False),
        observation=observation,
    )
    second = apply_effect_receipt(
        context=context,
        tracks_context_state=True,
        receipt=_receipt("confirmed_success", contract_key="notice-2", completes_goal=False),
        observation=observation,
    )

    assert context.mission.search_enabled is False
    assert context.mission.minimum_effects == 2
    assert first.goal_completed is False
    assert second.goal_completed is True


def test_multi_operation_progress_and_deduplication_survive_checkpoint_restore():
    goal = "打开通知页面，分别给多个账号发送通知"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(
        lang="zh", node=node, goal=goal, original_user_request=goal,
    )
    context.completed.add("navigate")
    observation = Observation(url="https://example.test/notifications", title="Notifications", elements=[])
    first_receipt = _receipt(
        "confirmed_success", contract_key="notice-1", completes_goal=False,
    )
    apply_effect_receipt(
        context=context,
        tracks_context_state=True,
        receipt=first_receipt,
        observation=observation,
    )

    restored = GeneralBrowserContext(
        lang="zh", node=node, goal=goal, original_user_request=goal,
    )
    restored.restore_checkpoint_state(context.export_checkpoint_state())
    replay = apply_effect_receipt(
        context=restored,
        tracks_context_state=True,
        receipt=first_receipt,
        observation=observation,
    )
    second = apply_effect_receipt(
        context=restored,
        tracks_context_state=True,
        receipt=_receipt("confirmed_success", contract_key="notice-2", completes_goal=False),
        observation=observation,
    )

    assert replay.goal_completed is False
    assert restored.mission.confirmed_effects == 2
    assert restored.mission.confirmed_contract_keys == {"notice-1", "notice-2"}
    assert second.goal_completed is True


def test_effect_completion_builds_terminal_browser_artifact():
    summary, meta = build_effect_completion(
        receipt=_receipt("confirmed_success"),
        objective="发布一条评论",
        steps=12,
        lang="zh",
        result_data={
            "operation_details": {
                "submitted_fields": [{
                    "label": "评论",
                    "value": "已提交的正文",
                }],
            },
        },
    )

    assert summary == "已确认完成操作：发布评论"
    assert meta["browser_receipt"]["steps"] == 12
    assert meta["operation_result"]["status"] == "confirmed_success"
    assert meta["browser_result"]["objective"] == "发布一条评论"
    assert (
        meta["browser_result"]["data"]["operation_details"]
        ["submitted_fields"][0]["value"]
        == "已提交的正文"
    )


def test_partial_effect_completion_keeps_confirmed_operation_and_task_boundary():
    outcome = EffectTaskOutcome(
        status="partial_success",
        reason="missing prerequisite evidence",
        verified_requirements=("navigate",),
        missing_requirements=("search", "open_result"),
    )

    summary, meta = build_effect_completion(
        receipt=_receipt("confirmed_success"),
        objective="搜索并进入帖子后发布评论",
        steps=9,
        lang="zh",
        outcome=outcome,
    )

    assert "整体仅部分完成" in summary
    assert meta["browser_receipt"]["status"] == "ok_partial"
    assert meta["operation_result"]["status"] == "confirmed_success"
    assert meta["browser_result"]["status"] == "partial_success"
    assert meta["browser_result"]["task_outcome"]["missing_requirements"] == [
        "search", "open_result",
    ]


def test_failure_receipt_preserves_confirmed_side_effect_history():
    payload = build_effect_failure(
        error="read loop",
        receipts=[
            {"contract_key": "one", "status": "confirmed_success"},
            {"contract_key": "two", "status": "confirmed_success"},
        ],
    )

    assert payload["status"] == "failed"
    assert payload["confirmed_effect_count"] == 2
    assert len(payload["effect_receipts"]) == 2
    assert payload["effect_receipt"]["contract_key"] == "two"


def test_failure_receipt_ignores_superseded_unknown_for_terminal_status():
    payload = build_effect_failure(
        error="form target could not be rebound",
        receipts=[{
            "contract_key": "obsolete-navigation",
            "status": "unknown",
            "fingerprint": {"verification_superseded": True},
        }],
    )

    assert payload["status"] == "failed"
    assert payload["effect_receipts"][0]["contract_key"] == "obsolete-navigation"
    assert "effect_receipt" not in payload
    assert "side_effect_status" not in payload


def test_confirmed_business_failure_builds_normal_negative_result():
    receipt = _receipt("confirmed_failure")
    receipt.reason = "请求参数异常，请升级客户端后重试"

    summary, meta = build_effect_business_failure(
        receipt=receipt,
        objective="发布一条评论",
        steps=14,
        lang="zh",
        result_data={"operation_details": {"submitted_fields": []}},
    )

    assert "页面明确拒绝了本次操作" in summary
    assert "未重复提交" in summary
    assert meta["browser_receipt"]["status"] == "business_rejected"
    assert meta["browser_receipt"]["side_effect_status"] == "confirmed_failure"
    assert meta["operation_result"]["status"] == "confirmed_failure"
    assert meta["browser_result"]["status"] == "confirmed_failure"
    assert meta["browser_result"]["task_outcome"]["status"] == "business_failure"


def test_confirmed_business_failure_events_do_not_report_runtime_crash():
    receipt = _receipt("confirmed_failure")
    receipt.reason = "operation rejected"

    events = build_effect_business_failure_events(
        receipt=receipt,
        objective="发布一条评论",
        steps=7,
        lang="zh",
        result_data=None,
        subagent_id="sa-1",
        node_id="browser-1",
        emit_answer=True,
    )

    assert events[0][0]["type"] == "activity"
    assert events[0][0]["content"]["kind"] == "warning"
    assert any(event["type"] == "answer" for event, _artifact in events)
    done_event, artifact = events[-1]
    assert done_event["type"] == "subagent_done"
    assert done_event["content"]["status"] == "succeeded"
    assert artifact["browser_receipt"]["status"] == "business_rejected"
