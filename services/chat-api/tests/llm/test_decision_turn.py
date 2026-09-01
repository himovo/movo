from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncGenerator, List, Type

import pytest
from pydantic import BaseModel

from app.llm.base import BaseLLMClient
from app.llm.decision_turn import (
    DecisionOutput,
    DecisionTurnSpec,
    DecisionTurnVisibility,
    invoke_json_decision,
    invoke_structured_decision,
    invoke_tool_decision,
    bind_decision_turn_channel,
)
from app.llm.types import LLMResponse, Message, Role
from app.enterprise_capabilities.content.evaluation.issue_finder import _FoundIssues
from app.enterprise_capabilities.content.evaluation.standards_generator import _GeneratedStandards
from app.enterprise_capabilities.research.progressive.models import ResearchTurnDecision
from app.enterprise_capabilities.content.subject_resolution.resolver import SubjectResolutionDecision
from app.enterprise_capabilities.content.planning.contracts import ContentPlanSpec
from app.services.skill_assets.composite_task import CompositeSkillMatchDecision
from app.enterprise_capabilities.content.publish_assembly.assembler import VisualSlotGenerationDecision
from app.enterprise_capabilities.browser.engine.agent_loop.planner import _DecisionSchema
from app.enterprise_capabilities.content.writer_engine.unified_compose.components import PlanAlignmentAssessment, ReportOutlinePlan


class _BusinessDecision(DecisionOutput):
    decision: str
    count: int


class _PlainOutput(BaseModel):
    decision: str


class _FakeClient(BaseLLMClient):
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: List[List[Message]] = []

    async def ainvoke(self, messages: List[Message], **kwargs) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(
            message=Message(role=Role.ASSISTANT, content=json.dumps(self.payload, ensure_ascii=False))
        )

    async def astream(self, messages: List[Message], **kwargs) -> AsyncGenerator[LLMResponse, None]:
        if False:
            yield await self.ainvoke(messages, **kwargs)

    async def ainvoke_structured(
        self,
        messages: List[Message],
        schema: Type[BaseModel],
        **kwargs,
    ) -> BaseModel:
        self.calls.append(messages)
        return schema.model_validate(self.payload)


def _prompt(client: _FakeClient) -> str:
    return "\n".join(str(message.content or "") for message in client.calls[0])


def test_structured_decision_preserves_business_result_and_publishes_once() -> None:
    async def exercise():
        emitted = []
        client = _FakeClient(
            {
                "decision": "continue",
                "count": 7,
                "commentary": {"text": "已确认缺少治理政策证据，下一轮将补充权威机构来源。", "reason": "pivot"},
            }
        )

        result = await invoke_structured_decision(
            client,
            _BusinessDecision,
            [Message(role=Role.USER, content="继续研究")],
            spec=DecisionTurnSpec(locale="zh", turn_id="research.review.1", sink=emitted.append),
        )
        return client, emitted, result

    import asyncio
    client, emitted, result = asyncio.run(exercise())

    assert (result.decision, result.count) == ("continue", 7)
    assert len(client.calls) == 1
    assert emitted == [
        {
            "text": "已确认缺少治理政策证据，下一轮将补充权威机构来源。",
            "reason": "pivot",
            "locale": "zh-CN",
            "source": "model",
            "turn_id": "research.review.1",
        }
    ]
    assert "This is a decision turn" in _prompt(client)
    assert "继续研究" in _prompt(client)


def test_malformed_commentary_and_sink_failure_never_change_business_fields() -> None:
    async def exercise():
        malformed = _FakeClient({"decision": "deliver", "count": 3, "commentary": ["bad provider shape"]})
        malformed_result = await invoke_structured_decision(
            malformed,
            _BusinessDecision,
            [Message(role=Role.USER, content="deliver")],
            spec=DecisionTurnSpec(locale="en", turn_id="quality.review", sink=lambda _payload: None),
        )

        async def broken_sink(_payload):
            raise RuntimeError("UI transport unavailable")

        valid = _FakeClient(
            {
                "decision": "deliver",
                "count": 4,
                "commentary": {"text": "The evidence now covers the requested scope.", "reason": "finding"},
            }
        )
        valid_result = await invoke_structured_decision(
            valid,
            _BusinessDecision,
            [Message(role=Role.USER, content="deliver")],
            spec=DecisionTurnSpec(locale="en", turn_id="quality.review", sink=broken_sink),
        )
        return malformed_result, valid_result

    import asyncio
    malformed_result, valid_result = asyncio.run(exercise())
    assert (malformed_result.decision, malformed_result.count, malformed_result.commentary) == ("deliver", 3, None)
    assert (valid_result.decision, valid_result.count) == ("deliver", 4)


def test_json_decision_uses_same_single_turn_contract() -> None:
    emitted = []
    client = _FakeClient(
        {
            "next_queries": ["official policy"],
            "commentary": {"text": "I will prioritize official policy and standards sources.", "reason": "intent"},
        }
    )
    import asyncio
    result = asyncio.run(invoke_json_decision(
        client,
        [Message(role=Role.USER, content="research governance")],
        parser=json.loads,
        spec=DecisionTurnSpec(locale="en", turn_id="research.plan", sink=emitted.append),
    ))
    assert result["next_queries"] == ["official policy"]
    assert len(client.calls) == 1
    assert emitted[0]["turn_id"] == "research.plan"


def test_non_decision_schema_cannot_bypass_the_contract() -> None:
    import asyncio
    with pytest.raises(TypeError):
        asyncio.run(invoke_structured_decision(
            _FakeClient({"decision": "x"}),
            _PlainOutput,
            [Message(role=Role.USER, content="x")],
            spec=DecisionTurnSpec(locale="en", turn_id="invalid"),
        ))


def test_internal_decision_preserves_business_result_without_user_commentary_prompt_or_event() -> None:
    async def exercise():
        emitted = []
        client = _FakeClient({
            "decision": "graph",
            "count": 2,
            "commentary": {"text": "This internal classification should not be shown.", "reason": "intent"},
        })
        result = await invoke_structured_decision(
            client,
            _BusinessDecision,
            [Message(role=Role.USER, content="plan this")],
            spec=DecisionTurnSpec(
                locale="en",
                turn_id="task_intent.internal",
                sink=emitted.append,
                visibility=DecisionTurnVisibility.INTERNAL,
            ),
        )
        return client, emitted, result

    import asyncio
    client, emitted, result = asyncio.run(exercise())
    assert (result.decision, result.count) == ("graph", 2)
    assert emitted == []
    assert "This is a decision turn" not in _prompt(client)


def test_request_channel_collects_without_manual_sink_and_isolates_concurrency() -> None:
    async def worker(locale: str, text: str):
        with bind_decision_turn_channel(locale=locale) as channel:
            client = _FakeClient({
                "decision": "continue",
                "count": 1,
                "commentary": {"text": text, "reason": "finding"},
            })
            result = await invoke_structured_decision(
                client,
                _BusinessDecision,
                [Message(role=Role.USER, content=text)],
                spec=DecisionTurnSpec(locale="", turn_id=f"turn.{locale}"),
            )
            return result, channel.drain()

    async def collect():
        return await asyncio.gather(
            worker("zh-CN", "已确认需要补充治理政策来源，下一步将检索官方材料。"),
            worker("en-US", "The evidence gap is policy coverage, so I will check official sources next."),
        )

    import asyncio
    zh, en = asyncio.run(collect())
    assert zh[0].decision == en[0].decision == "continue"
    assert zh[1][0]["locale"] == "zh-CN"
    assert en[1][0]["locale"] == "en-US"


def test_tool_decision_preserves_tool_calls_and_only_publishes_assistant_commentary() -> None:
    class _ToolClient(_FakeClient):
        async def ainvoke(self, messages, **kwargs):
            self.calls.append(messages)
            return LLMResponse(message=Message(
                role=Role.ASSISTANT,
                content="I found a policy gap, so I will query the official standards source next.",
                tool_calls=[{"id": "call_1", "name": "search", "args": {"q": "official standard"}}],
            ))

    async def exercise():
        with bind_decision_turn_channel(locale="en-US") as channel:
            response = await invoke_tool_decision(
                _ToolClient({}),
                [Message(role=Role.USER, content="research")],
                spec=DecisionTurnSpec(locale="", turn_id="tools.1"),
            )
            return response, channel.drain()

    import asyncio
    response, emitted = asyncio.run(exercise())
    assert response.tool_calls[0]["name"] == "search"
    assert emitted[0]["turn_id"] == "tools.1"
    assert "official standards" in emitted[0]["text"]


def test_internal_tool_decision_does_not_request_or_publish_commentary() -> None:
    class _ToolClient(_FakeClient):
        async def ainvoke(self, messages, **kwargs):
            self.calls.append(messages)
            return LLMResponse(message=Message(
                role=Role.ASSISTANT,
                content="Internal tool selection",
                tool_calls=[{"id": "call_1", "name": "search", "args": {"q": "policy"}}],
            ))

    async def exercise():
        emitted = []
        client = _ToolClient({})
        response = await invoke_tool_decision(
            client,
            [Message(role=Role.USER, content="research")],
            spec=DecisionTurnSpec(
                locale="en",
                turn_id="tools.internal",
                sink=emitted.append,
                visibility=DecisionTurnVisibility.INTERNAL,
            ),
        )
        return client, emitted, response

    import asyncio
    client, emitted, response = asyncio.run(exercise())
    assert response.tool_calls[0]["name"] == "search"
    assert emitted == []
    assert "tool-selection decision turn" not in _prompt(client)


def test_all_migrated_decision_schemas_inherit_the_common_contract() -> None:
    schemas = (
        ResearchTurnDecision,
        _GeneratedStandards,
        _FoundIssues,
        ReportOutlinePlan,
        PlanAlignmentAssessment,
        _DecisionSchema,
        SubjectResolutionDecision,
        ContentPlanSpec,
        CompositeSkillMatchDecision,
        VisualSlotGenerationDecision,
    )
    assert all(issubclass(schema, DecisionOutput) for schema in schemas)
    commentary_schema = _BusinessDecision.model_json_schema()["properties"]["commentary"]
    assert "anyOf" in commentary_schema
    assert any(item.get("type") == "null" for item in commentary_schema["anyOf"])
    assert "commentary" not in _BusinessDecision(decision="continue", count=1).model_dump()


def test_migrated_modules_do_not_own_scenario_commentary_prompts() -> None:
    app_root = Path(__file__).resolve().parents[2] / "app"
    targets = (
        app_root / "enterprise_capabilities/research/progressive/agent.py",
        app_root / "enterprise_capabilities/content/evaluation/standards_generator.py",
        app_root / "enterprise_capabilities/content/evaluation/issue_finder.py",
        app_root / "enterprise_capabilities/content/writer_engine/unified_compose/components.py",
        app_root / "enterprise_capabilities/browser/engine/agent_loop/planner.py",
    )
    forbidden = (
        "commentary is REQUIRED",
        "commentary 是每次成功证据判断必填",
        "Also return commentary=",
        "Optionally return commentary=",
        "initial_commentary as an object",
    )
    violations = {
        str(path.relative_to(app_root)): token
        for path in targets
        for token in forbidden
        if token in path.read_text(encoding="utf-8")
    }
    assert violations == {}


def test_decision_critical_modules_cannot_bypass_the_common_runner() -> None:
    app_root = Path(__file__).resolve().parents[2] / "app"
    targets = (
        "enterprise_capabilities/browser/engine/action_resolution.py",
        "enterprise_capabilities/browser/engine/effect_verification/discovery.py",
        "enterprise_capabilities/browser/engine/effect_verification/semantic_alignment.py",
        "enterprise_capabilities/browser/engine/effect_verification/verifier.py",
        "enterprise_capabilities/browser/engine/action_history.py",
        "enterprise_capabilities/browser/engine/form_input/model_fallback.py",
        "services/skill_assets/composite_task.py",
        "enterprise_capabilities/content/publish_assembly/assembler.py",
        "enterprise_capabilities/content/publish_assembly/deferred_finalizer.py",
    )
    forbidden = (".with_structured_output(", ".ainvoke_structured(")
    violations = {
        relative: token
        for relative in targets
        for token in forbidden
        if token in (app_root / relative).read_text(encoding="utf-8")
    }
    assert violations == {}
