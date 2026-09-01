from types import SimpleNamespace

from app.enterprise_capabilities.browser.engine.run_request import (
    RUN_ORIGINAL_USER_REQUEST,
    bind_run_original_request,
    resolve_run_original_request,
    restore_run_original_request,
)


def test_bind_run_original_request_is_immutable_for_the_run():
    output_spec = {}

    assert bind_run_original_request(output_spec, "当前任务") == "当前任务"
    assert bind_run_original_request(output_spec, "恢复时的新消息") == "当前任务"


def test_restore_prefers_persisted_policy_context_over_resume_messages():
    output_spec = {}
    state = SimpleNamespace(
        policy_context={RUN_ORIGINAL_USER_REQUEST: "知乎原始任务"},
        graph=SimpleNamespace(globals={RUN_ORIGINAL_USER_REQUEST: "图中的备用值"}),
        goal_contract={"objective": "截断的目标"},
    )

    restored = restore_run_original_request(
        output_spec=output_spec,
        state=state,
        fallback="恢复请求",
    )

    assert restored == "知乎原始任务"
    assert output_spec[RUN_ORIGINAL_USER_REQUEST] == "知乎原始任务"


def test_resolve_uses_run_bound_request_in_multi_turn_conversation():
    messages = [
        {"role": "user", "content": "上一轮 AskBot 任务"},
        {"role": "assistant", "content": "上一轮结果"},
        {"role": "user", "content": "当前知乎任务，不要搜索 AskBot"},
    ]

    assert resolve_run_original_request(
        output_spec={RUN_ORIGINAL_USER_REQUEST: "当前知乎任务，不要搜索 AskBot"},
        messages=messages,
    ) == "当前知乎任务，不要搜索 AskBot"


def test_old_run_fallback_uses_latest_user_message_not_first_message():
    messages = [
        {"role": "user", "content": "上一轮 AskBot 任务"},
        {"role": "assistant", "content": "上一轮结果"},
        {"role": "user", "content": "当前知乎任务，不要搜索 AskBot"},
    ]

    assert resolve_run_original_request(output_spec={}, messages=messages) == "当前知乎任务，不要搜索 AskBot"
