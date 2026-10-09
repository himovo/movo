"""DSH message-version compatibility at the MOVO model gateway boundary."""

from app.dsh_runtime.model_gateway.service import ModelGatewayRequest, ModelGatewayService
from app.llm.types import Role


def _request(messages: list[dict]) -> ModelGatewayRequest:
    return ModelGatewayRequest(
        profileVersion="profile-a",
        modelInstanceId="model-a",
        provider="askai-model-gateway",
        model="deepseek-chat",
        messages=messages,
    )


def test_v4_native_tool_result_preserves_call_id() -> None:
    messages = ModelGatewayService._messages(_request([
        {"role": "assistant", "content": [{"type": "tool-call", "id": "call-a", "name": "skill", "arguments": "{}"}]},
        {"role": "tool", "toolCallId": "call-a", "content": [{"type": "text", "text": "skill answer"}]},
    ]))

    assert messages[0].tool_calls[0]["id"] == "call-a"
    assert messages[1].role == Role.TOOL
    assert messages[1].tool_call_id == "call-a"
    assert messages[1].content == "skill answer"


def test_legacy_wrapped_tool_result_still_maps() -> None:
    messages = ModelGatewayService._messages(_request([
        {"role": "user", "content": [{"type": "tool-result", "toolCallId": "call-old", "content": [{"type": "text", "text": "old answer"}]}]},
    ]))

    assert messages[0].role == Role.TOOL
    assert messages[0].tool_call_id == "call-old"
    assert messages[0].content == "old answer"


def test_explicit_result_does_not_complete_a_different_pending_call() -> None:
    messages = ModelGatewayService._messages(_request([
        {"role": "assistant", "content": [
            {"type": "text", "text": "checking"},
            {"type": "tool-call", "id": "call-current", "name": "read", "arguments": "{}"},
        ]},
        {"role": "user", "content": [
            {"type": "tool-result", "toolCallId": "call-other", "content": [{"type": "text", "text": "unrelated"}]},
        ]},
        {"role": "user", "content": [{"type": "text", "text": "continue"}]},
    ]))

    assert len(messages) == 2
    assert messages[0].content == "checking"
    assert messages[0].tool_calls is None
    assert messages[1].content == "continue"


def test_legacy_wrapped_result_recovers_the_only_pending_call_id() -> None:
    messages = ModelGatewayService._messages(_request([
        {"role": "assistant", "content": [
            {"type": "text", "text": "checking"},
            {"type": "tool-call", "id": "call-only", "name": "read", "arguments": "{}"},
        ]},
        {"role": "user", "content": [
            {"type": "tool-result", "content": [{"type": "text", "text": "file contents"}]},
        ]},
        {"role": "user", "content": [{"type": "text", "text": "continue"}]},
    ]))

    assert messages[0].tool_calls[0]["id"] == "call-only"
    assert messages[1].role == Role.TOOL
    assert messages[1].tool_call_id == "call-only"
    assert messages[2].content == "continue"


def test_legacy_native_result_recovers_id_from_source_metadata() -> None:
    messages = ModelGatewayService._messages(_request([
        {"role": "assistant", "content": [
            {"type": "tool-call", "id": "call-source", "name": "read", "arguments": "{}"},
        ]},
        {"role": "tool", "source": {"kind": "tool", "callId": "call-source"}, "content": [
            {"type": "text", "text": "answer"},
        ]},
    ]))

    assert messages[1].tool_call_id == "call-source"


def test_ambiguous_legacy_result_drops_the_incomplete_exchange_only() -> None:
    messages = ModelGatewayService._messages(_request([
        {"role": "assistant", "content": [
            {"type": "text", "text": "I will inspect both files."},
            {"type": "tool-call", "id": "call-a", "name": "read", "arguments": "{}"},
            {"type": "tool-call", "id": "call-b", "name": "read", "arguments": "{}"},
        ]},
        {"role": "user", "content": [
            {"type": "tool-result", "content": [{"type": "text", "text": "unknown result"}]},
        ]},
        {"role": "user", "content": [{"type": "text", "text": "continue safely"}]},
    ]))

    assert len(messages) == 2
    assert messages[0].role == Role.ASSISTANT
    assert messages[0].content == "I will inspect both files."
    assert messages[0].tool_calls is None
    assert messages[1].content == "continue safely"


def test_unanswered_tool_call_is_removed_before_the_next_user_message() -> None:
    messages = ModelGatewayService._messages(_request([
        {"role": "assistant", "content": [
            {"type": "text", "text": "starting"},
            {"type": "tool-call", "id": "call-lost", "name": "read", "arguments": "{}"},
        ]},
        {"role": "user", "content": [{"type": "text", "text": "resume"}]},
    ]))

    assert messages[0].content == "starting"
    assert messages[0].tool_calls is None
    assert messages[1].content == "resume"
