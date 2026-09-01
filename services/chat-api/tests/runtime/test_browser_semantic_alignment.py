from __future__ import annotations

import asyncio

import pytest

from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectContract
from app.enterprise_capabilities.browser.engine.effect_verification.semantic_alignment import (
    SemanticDescriptor,
    assess_target_alignment,
)
from app.enterprise_capabilities.browser.engine.effect_verification.tracker import (
    EffectTracker,
    SemanticActionRejected,
)
from app.enterprise_capabilities.browser.engine.effect_verification.verifier import verify_effect
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _obs(*, url: str, editable: int = 0, label: str = "") -> Observation:
    elements = [
        {"ref": f"field-{index}", "role": "textbox", "name": f"field {index}", "editable": True}
        for index in range(editable)
    ]
    if label:
        elements.append({"ref": "target", "role": "button", "name": label, "text": label})
    return Observation(url=url, title="test", elements=elements)


class _AlignmentLLM:
    def __init__(self, *, status: str, intended: str, observed: str, confidence: float = 0.96) -> None:
        self.status = status
        self.intended = intended
        self.observed = observed
        self.confidence = confidence

    async def ainvoke_structured(self, _messages, schema):
        if schema.__name__ == "_DiscoveredContract":
            return schema(
                is_commit=True,
                action_name="open editor",
                operation_family="create",
                entity=self.intended,
                side_effect="write",
                completes_goal=True,
            )
        return schema(
            status=self.status,
            confidence=self.confidence,
            intended=SemanticDescriptor(operation="publish", entity=self.intended, confidence=0.97),
            observed=SemanticDescriptor(operation="publish", entity=self.observed, confidence=0.97),
            reason=f"expected {self.intended}; observed {self.observed}",
        )


class _UnexpectedLLM:
    async def ainvoke_structured(self, _messages, _schema):
        raise AssertionError("ordinary navigation must not invoke semantic write alignment")


def test_pre_click_gate_blocks_different_open_ended_business_objects() -> None:
    tracker = EffectTracker(
        goal="在内容下提交反馈甲",
        original_request="请发布反馈甲",
        capability_id="browser.publish",
        lang="zh",
        llm=_AlignmentLLM(status="incompatible", intended="反馈甲", observed="文章乙"),
    )
    before = _obs(url="https://example.test/item", label="撰写文章乙")

    with pytest.raises(SemanticActionRejected) as error:
        asyncio.run(tracker.prepare_click(target=before.elements[-1], before=before))

    assert error.value.alignment.intended.entity == "反馈甲"
    assert error.value.alignment.observed.entity == "文章乙"


def test_ordinary_result_link_bypasses_write_object_alignment() -> None:
    tracker = EffectTracker(
        goal="打开小红书，搜索智能体并进入相关帖子发表评论",
        original_request="进入相关帖子发表评论",
        capability_id="browser.publish",
        lang="zh",
        llm=_UnexpectedLLM(),
    )
    before = Observation(
        url="https://example.test/search?q=智能体",
        title="搜索结果",
        elements=[{
            "ref": "post", "role": "link", "name": "豆包智能体",
            "href": "https://example.test/post/1",
        }],
    )

    prepared = asyncio.run(tracker.prepare_click(target=before.elements[0], before=before))

    assert prepared is None


def test_commit_labelled_link_still_uses_effect_and_semantic_verification() -> None:
    tracker = EffectTracker(
        goal="删除月度复盘记录",
        original_request="请删除月度复盘记录",
        capability_id="browser.delete",
        lang="zh",
        llm=_AlignmentLLM(status="compatible", intended="月度复盘记录", observed="月度复盘记录"),
    )
    before = Observation(
        url="https://example.test/records",
        title="记录",
        elements=[{
            "ref": "delete", "role": "link", "name": "立即删除此记录", "text": "立即删除此记录",
            "href": "https://example.test/records/1/delete",
        }],
    )

    prepared = asyncio.run(tracker.prepare_click(target=before.elements[0], before=before))

    assert prepared is not None
    assert prepared.contract.is_commit is True
    assert prepared.contract.operation_family != "navigate"
    assert prepared.contract.semantic_confidence > 0


def test_same_dynamic_entity_is_allowed_without_entity_dictionary() -> None:
    alignment = asyncio.run(assess_target_alignment(
        goal="创建月度复盘记录",
        original_request="请新建一条月度复盘记录",
        target={"role": "button", "name": "新建月度复盘记录"},
        lang="zh",
        llm=None,
    ))

    assert alignment.status == "compatible"
    assert alignment.source == "local_rule"
    assert alignment.observed.entity == "月度复盘记录"


def test_negated_entity_does_not_bypass_model_alignment() -> None:
    alignment = asyncio.run(assess_target_alignment(
        goal="不要发布文章乙，只发布反馈甲",
        original_request="不要发布文章乙",
        target={"role": "button", "name": "撰写文章乙"},
        lang="zh",
        llm=_AlignmentLLM(status="incompatible", intended="反馈甲", observed="文章乙"),
    ))

    assert alignment.status == "incompatible"
    assert alignment.source == "model"
    assert alignment.blocks_action is True


def test_contextual_entity_mention_does_not_count_as_goal_object() -> None:
    alignment = asyncio.run(assess_target_alignment(
        goal="在现有回答下面发表评论",
        original_request="请发表评论",
        target={"role": "button", "name": "写回答"},
        lang="zh",
        llm=_AlignmentLLM(status="incompatible", intended="评论", observed="回答"),
    ))

    assert alignment.status == "incompatible"
    assert alignment.source == "model"
    assert alignment.blocks_action is True


def test_low_confidence_mismatch_does_not_block_action() -> None:
    alignment = asyncio.run(assess_target_alignment(
        goal="处理季度资料",
        original_request="处理季度资料",
        target={"role": "button", "name": "进入归档流程"},
        lang="zh",
        llm=_AlignmentLLM(
            status="incompatible",
            intended="季度资料",
            observed="归档流程",
            confidence=0.55,
        ),
    ))

    assert alignment.status == "incompatible"
    assert alignment.blocks_action is False


def test_generic_commit_inherits_entity_from_editor_entry() -> None:
    tracker = EffectTracker(
        goal="发布月度复盘记录",
        capability_id="browser.publish",
        lang="zh",
        llm=_AlignmentLLM(
            status="compatible",
            intended="月度复盘记录",
            observed="月度复盘记录",
        ),
    )
    entry = _obs(url="https://example.test/list", label="新建月度复盘记录")
    # Entry is classified locally as the requested entity. It is not a
    # commit after the editable surface appears.
    prepared_entry = asyncio.run(tracker.prepare_click(target=entry.elements[-1], before=entry))
    assert prepared_entry is not None
    assert asyncio.run(tracker.record(
        prepared=prepared_entry,
        after=_obs(url="https://example.test/list", editable=1, label="发布"),
    )) is None

    editing = _obs(url="https://example.test/list", editable=1, label="发布")
    prepared_commit = asyncio.run(tracker.prepare_click(target=editing.elements[-1], before=editing))

    assert prepared_commit is not None
    assert prepared_commit.contract.intended_entity == "月度复盘记录"


def test_post_action_guard_rejects_success_on_different_object() -> None:
    contract = EffectContract(
        action_name="发布",
        operation_family="publish",
        is_commit=True,
        side_effect="external",
        intended_operation="publish",
        intended_entity="反馈甲",
    )
    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(url="https://example.test/editor", editable=2, label="发布"),
        after=_obs(url="https://example.test/article/123", editable=0),
        lang="zh",
        llm=_AlignmentLLM(status="incompatible", intended="反馈甲", observed="文章乙"),
    ))

    assert receipt.status == "confirmed_failure"
    assert receipt.blocks_replay is True
    assert any(item.kind == "semantic_mismatch" for item in receipt.evidence)


def test_post_action_guard_preserves_pending_without_durable_result_evidence() -> None:
    contract = EffectContract(
        action_name="发布",
        operation_family="publish",
        is_commit=True,
        side_effect="external",
        intended_operation="publish",
        intended_entity="月度复盘记录",
    )
    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(url="https://example.test/editor", editable=2, label="发布"),
        after=_obs(url="https://example.test/records/123", editable=0),
        lang="zh",
        llm=_AlignmentLLM(
            status="compatible",
            intended="月度复盘记录",
            observed="月度复盘记录",
        ),
    ))

    assert receipt.status == "pending"
    assert not any(item.kind == "semantic_mismatch" for item in receipt.evidence)
