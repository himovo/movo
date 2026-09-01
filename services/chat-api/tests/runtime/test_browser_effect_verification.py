from __future__ import annotations

import asyncio

from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectContract, EffectEvidence
from app.enterprise_capabilities.browser.engine.effect_verification.discovery import discover_effect_contract
from app.enterprise_capabilities.browser.engine.effect_verification.tracker import EffectTracker
from app.enterprise_capabilities.browser.engine.effect_verification.verifier import verify_effect
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def _obs(
    *,
    url: str,
    editable: int = 0,
    action: str = "",
    effects: list[dict] | None = None,
    page_text: str = "",
) -> Observation:
    elements = [
        {"ref": f"e{index + 1}", "role": "textbox", "name": f"field-{index}", "editable": True}
        for index in range(editable)
    ]
    if action:
        elements.append({"ref": "commit", "role": "button", "name": action, "text": action})
    return Observation(url=url, title="test", elements=elements, effects=list(effects or []), page_text=page_text)


def test_route_and_form_close_leave_generic_commit_pending_without_result_evidence() -> None:
    contract = EffectContract(
        action_name="提交",
        operation_family="submit",
        is_commit=True,
        side_effect="write",
    )
    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(url="https://example.test/edit", editable=3, action="提交"),
        after=_obs(url="https://example.test/list", editable=0),
        lang="zh",
    ))

    assert receipt.status == "pending"
    assert {item.kind for item in receipt.evidence} >= {"route_changed", "form_closed"}


def test_route_form_close_and_submitted_value_confirm_generic_commit() -> None:
    contract = EffectContract(
        action_name="提交",
        operation_family="submit",
        is_commit=True,
        side_effect="write",
    )
    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(url="https://example.test/edit", editable=3, action="提交"),
        after=_obs(url="https://example.test/list", editable=0),
        lang="zh",
        supplemental_evidence=[EffectEvidence(
            evidence_id="field:1",
            kind="submitted_value_present",
            detail="result contains submitted value",
            polarity="positive",
            weight=0.85,
        )],
    ))

    assert receipt.status == "confirmed_success"
    assert receipt.confidence >= 0.9


def test_new_business_object_identifier_confirms_save_without_form_close() -> None:
    contract = EffectContract(
        action_name="存草稿",
        operation_family="save",
        is_commit=True,
        side_effect="write",
    )
    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(
            url="https://example.test/editor?type=news&from=create",
            editable=2,
            action="存草稿",
        ),
        after=_obs(
            url="https://example.test/editor?type=news&article_id=1872038424764100898",
            editable=2,
            action="存草稿",
        ),
        lang="zh",
    ))

    assert receipt.status == "confirmed_success"
    assert any(item.kind == "business_object_id_assigned" for item in receipt.evidence)


def test_volatile_session_identifier_does_not_confirm_commit() -> None:
    contract = EffectContract(
        action_name="提交",
        operation_family="submit",
        is_commit=True,
        side_effect="write",
    )
    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(url="https://example.test/editor", editable=1, action="提交"),
        after=_obs(url="https://example.test/editor?session_id=123456789", editable=1, action="提交"),
        lang="zh",
        llm=_UnknownVerdictLLM(),
    ))

    assert receipt.status == "unknown"
    assert not any(item.kind == "business_object_id_assigned" for item in receipt.evidence)


def test_camel_case_business_identifier_confirms_commit() -> None:
    contract = EffectContract(
        action_name="Save draft",
        operation_family="save",
        is_commit=True,
        side_effect="write",
    )
    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(url="https://example.test/editor", editable=1, action="Save draft"),
        after=_obs(
            url="https://example.test/editor?articleId=opaque-article-123",
            editable=1,
            action="Save draft",
        ),
        lang="en",
    ))

    assert receipt.status == "confirmed_success"
    assert any(item.kind == "business_object_id_assigned" for item in receipt.evidence)


def test_replacing_an_existing_identifier_does_not_prove_new_object_creation() -> None:
    contract = EffectContract(
        action_name="保存",
        operation_family="save",
        is_commit=True,
        side_effect="write",
    )
    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(
            url="https://example.test/editor?article_id=123456",
            editable=1,
            action="保存",
        ),
        after=_obs(
            url="https://example.test/editor?article_id=654321",
            editable=1,
            action="保存",
        ),
        lang="zh",
        llm=_UnknownVerdictLLM(),
    ))

    assert receipt.status == "unknown"
    assert not any(item.kind == "business_object_id_assigned" for item in receipt.evidence)


def test_navigation_contract_does_not_use_business_object_identity_as_commit_success() -> None:
    contract = EffectContract(
        action_name="打开文章",
        operation_family="navigate",
        is_commit=False,
        side_effect="none",
    )
    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(url="https://example.test/articles"),
        after=_obs(url="https://example.test/articles/123456"),
        lang="zh",
        llm=_UnknownVerdictLLM(),
    ))

    assert receipt.status == "unknown"
    assert not any(item.kind == "business_object_id_assigned" for item in receipt.evidence)


def test_new_submitted_value_in_result_confirms_without_success_text() -> None:
    contract = EffectContract(
        action_name="commit",
        operation_family="custom",
        is_commit=True,
        side_effect="write",
        completes_goal=True,
    )
    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(url="https://example.test/items", editable=1),
        after=_obs(url="https://example.test/items"),
        lang="zh",
        supplemental_evidence=[EffectEvidence(
            evidence_id="field_added:1",
            kind="submitted_value_added_to_result",
            detail="result occurrence changed 0 -> 1",
            polarity="positive",
            weight=0.95,
        )],
    ))

    assert receipt.status == "confirmed_success"
    assert receipt.confidence >= 0.9


def test_collection_growth_and_form_close_confirm_without_status_text() -> None:
    contract = EffectContract(
        action_name="commit",
        operation_family="custom",
        is_commit=True,
        side_effect="write",
    )
    before = Observation(
        url="https://example.test/items",
        title="Items",
        page_text="",
        elements=[
            {"ref": "f1", "role": "textbox", "editable": True},
            {"ref": "f2", "role": "textbox", "editable": True},
            {"ref": "i1", "role": "listitem", "editable": False},
        ],
    )
    after = Observation(
        url=before.url,
        title=before.title,
        page_text="",
        elements=[
            {"ref": "i1", "role": "listitem", "editable": False},
            {"ref": "i2", "role": "listitem", "editable": False},
        ],
    )

    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=before,
        after=after,
        lang="zh",
    ))

    assert receipt.status == "confirmed_success"


def test_fast_transient_success_is_retained_as_evidence() -> None:
    contract = EffectContract(
        action_name="核销",
        operation_family="voucher_redemption",
        is_commit=True,
        side_effect="write",
        source="model",
    )
    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(url="https://example.test/voucher", action="核销"),
        after=_obs(
            url="https://example.test/voucher",
            effects=[{"kind": "dom_added", "timestamp": 1, "role": "status", "text": "核销成功"}],
        ),
        lang="zh",
    ))

    assert receipt.status == "confirmed_success"
    assert receipt.confidence >= 0.9


def test_new_page_status_confirms_success_when_mutation_event_was_missed() -> None:
    contract = EffectContract(
        action_name="发布",
        operation_family="publish",
        is_commit=True,
        side_effect="external",
    )
    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(url="https://example.test/post", action="发布", page_text="评论区\n发布"),
        after=_obs(url="https://example.test/post", page_text="评论区\n评论成功"),
        lang="zh",
    ))

    assert receipt.status == "confirmed_success"
    assert any(item.kind == "page_status_delta" for item in receipt.evidence)


def test_success_inside_flattened_spa_page_text_confirms_operation() -> None:
    contract = EffectContract(
        action_name="发送",
        operation_family="send",
        is_commit=True,
        side_effect="external",
        completes_goal=True,
    )
    shared = " ".join(["帖子正文和评论内容"] * 80)
    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(url="https://example.test/post", action="发送", page_text=f"{shared} 发送 取消"),
        after=_obs(url="https://example.test/post", action="发送", page_text=f"{shared} 发送 取消 评论成功"),
        lang="zh",
    ))

    assert receipt.status == "confirmed_success"
    assert any(item.detail == "评论成功" for item in receipt.evidence)


def test_preexisting_success_in_flattened_spa_text_is_not_reused() -> None:
    contract = EffectContract(action_name="发送", operation_family="send", is_commit=True)
    shared = " ".join(["帖子正文"] * 100)
    page_text = f"{shared} 评论成功"

    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(url="https://example.test/post", action="发送", page_text=page_text),
        after=_obs(url="https://example.test/post", action="发送", page_text=page_text),
        lang="zh",
        llm=_UnknownVerdictLLM(),
    ))

    assert receipt.status == "unknown"


def test_new_explicit_rejection_inside_flattened_spa_text_confirms_failure() -> None:
    contract = EffectContract(
        action_name="发布",
        operation_family="publish",
        is_commit=True,
        side_effect="external",
        completes_goal=True,
    )
    shared = " ".join(["帖子正文和评论内容"] * 80)

    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(
            url="https://example.test/post",
            action="发布",
            page_text=f"{shared} 评论输入框 发布",
        ),
        after=_obs(
            url="https://example.test/post",
            action="发布",
            page_text=(
                f"{shared} 评论输入框 发布 "
                "10001: 请求参数异常，请升级客户端后重试"
            ),
        ),
        lang="zh",
    ))

    assert receipt.status == "confirmed_failure"
    assert receipt.blocks_replay is True
    assert any(
        item.kind == "page_message_delta"
        and "请求参数异常" in item.detail
        and item.polarity == "negative"
        for item in receipt.evidence
    )


def test_dynamic_page_text_still_extracts_new_explicit_rejection() -> None:
    contract = EffectContract(
        action_name="提交",
        operation_family="submit",
        is_commit=True,
        side_effect="write",
    )
    shared = " ".join(["稳定页面内容"] * 90)

    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(
            url="https://example.test/form",
            action="提交",
            page_text=f"未读消息 9 {shared} 提交",
        ),
        after=_obs(
            url="https://example.test/form",
            action="提交",
            page_text=f"未读消息 10 {shared} 提交 当前请求无效，请稍后重试",
        ),
        lang="zh",
    ))

    assert receipt.status == "confirmed_failure"
    assert any(
        "当前请求无效" in item.detail and item.polarity == "negative"
        for item in receipt.evidence
    )


def test_preexisting_rejection_in_flattened_spa_text_is_not_reused() -> None:
    contract = EffectContract(
        action_name="发布",
        operation_family="publish",
        is_commit=True,
        side_effect="external",
    )
    shared = " ".join(["帖子正文"] * 100)
    page_text = f"{shared} 请求参数异常，请稍后重试"

    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(url="https://example.test/post", action="发布", page_text=page_text),
        after=_obs(url="https://example.test/post", action="发布", page_text=page_text),
        lang="zh",
        llm=_UnknownVerdictLLM(),
    ))

    assert receipt.status == "unknown"


def test_new_business_copy_is_not_mistaken_for_operation_status() -> None:
    contract = EffectContract(
        action_name="提交",
        operation_family="submit",
        is_commit=True,
        side_effect="write",
    )
    shared = " ".join(["页面导航"] * 80)

    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(
            url="https://example.test/form",
            action="提交",
            page_text=f"{shared} 提交",
        ),
        after=_obs(
            url="https://example.test/form",
            action="提交",
            page_text=f"{shared} 提交 成功案例与异常处理方法",
        ),
        lang="zh",
        llm=_UnknownVerdictLLM(),
    ))

    assert receipt.status == "unknown"


def test_preexisting_success_text_is_not_reused_as_new_success() -> None:
    contract = EffectContract(action_name="提交", operation_family="submit", is_commit=True)
    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(url="https://example.test", action="提交", page_text="上次操作成功"),
        after=_obs(url="https://example.test", action="提交", page_text="上次操作成功"),
        lang="zh",
        llm=_UnknownVerdictLLM(),
    ))

    assert receipt.status == "unknown"


def test_navigation_menu_text_is_not_treated_as_success_toast() -> None:
    contract = EffectContract(
        action_name="发送",
        operation_family="send",
        is_commit=True,
        side_effect="external",
    )
    receipt = asyncio.run(verify_effect(
        contract=contract,
        before=_obs(url="https://example.test/compose", action="发送"),
        after=_obs(
            url="https://example.test/compose",
            action="发送",
            effects=[{"kind": "dom_added", "timestamp": 1, "role": "", "text": "已发送"}],
        ),
        lang="zh",
        llm=_UnknownVerdictLLM(),
    ))

    assert receipt.status == "unknown"


def test_pending_or_unknown_side_effect_blocks_replay() -> None:
    tracker = EffectTracker(goal="提交申请", capability_id="browser.submit", lang="zh")
    before = _obs(url="https://example.test/edit", editable=1, action="提交")
    target = next(item for item in before.elements if item.get("ref") == "commit")
    prepared = asyncio.run(tracker.prepare_click(target=target, before=before))
    assert prepared is not None

    receipt = asyncio.run(tracker.record(
        prepared=prepared,
        after=_obs(
            url="https://example.test/edit",
            editable=1,
            action="提交",
            effects=[{"kind": "dom_added", "timestamp": 1, "role": "status", "text": "正在处理"}],
        ),
    ))

    assert receipt.status == "pending"
    assert tracker.replay_blocker(prepared) is receipt


def test_same_label_buttons_in_different_forms_do_not_share_effect_receipts() -> None:
    tracker = EffectTracker(goal="提交两个独立表单", capability_id="browser.submit", lang="zh")
    before = Observation(
        url="https://example.test/forms",
        title="forms",
        elements=[
            {
                "ref": "e1", "role": "button", "name": "提交", "text": "提交",
                "selector": "#form-a button", "scopeId": "form-a",
            },
            {
                "ref": "e2", "role": "button", "name": "提交", "text": "提交",
                "selector": "#form-b button", "scopeId": "form-b",
            },
        ],
    )
    first = asyncio.run(tracker.prepare_click(target=before.elements[0], before=before))
    second = asyncio.run(tracker.prepare_click(target=before.elements[1], before=before))
    assert first is not None and second is not None
    assert first.contract.key() != second.contract.key()

    receipt = asyncio.run(tracker.record(
        prepared=first,
        after=Observation(
            url=before.url,
            title=before.title,
            elements=before.elements,
            effects=[{"kind": "dom_added", "role": "status", "text": "正在处理"}],
        ),
    ))

    assert receipt is not None and receipt.status == "pending"
    assert tracker.replay_blocker(first) is receipt
    assert tracker.replay_blocker(second) is None


def test_same_label_buttons_in_one_scope_do_not_share_effect_receipts() -> None:
    tracker = EffectTracker(goal="分别提交两项", capability_id="browser.submit", lang="zh")
    before = Observation(
        url="https://example.test/form",
        title="form",
        elements=[
            {"ref": "e1", "role": "button", "name": "提交", "scopeId": "form"},
            {"ref": "e2", "role": "button", "name": "提交", "scopeId": "form"},
        ],
    )

    first = asyncio.run(tracker.prepare_click(target=before.elements[0], before=before))
    second = asyncio.run(tracker.prepare_click(target=before.elements[1], before=before))

    assert first is not None and second is not None
    assert first.contract.key() != second.contract.key()


def test_search_click_does_not_enter_pending_effects_in_publish_mission() -> None:
    tracker = EffectTracker(
        goal="搜索帖子并发表评论",
        capability_id="browser.publish_or_submit",
        lang="zh",
    )
    before = Observation(
        url="https://example.test/search",
        title="Search",
        page_text="",
        elements=[{"ref": "search", "role": "button", "name": "搜索", "text": "搜索"}],
    )

    prepared = asyncio.run(tracker.prepare_click(target=before.elements[0], before=before))

    assert prepared is None
    assert tracker.pending_receipts() == []


def test_refined_generic_submit_is_removed_from_effect_tracking() -> None:
    tracker = EffectTracker(
        goal="搜索帖子并发表评论",
        capability_id="browser.publish_or_submit",
        lang="zh",
    )
    before = Observation(
        url="https://example.test/explore",
        title="Explore",
        page_text="",
        elements=[{"ref": "search", "role": "button", "name": "Submit", "type": "submit"}],
    )
    prepared = asyncio.run(tracker.prepare_click(target=before.elements[0], before=before))
    assert prepared is not None

    refined = prepared.contract.model_copy(update={
        "operation_family": "search",
        "side_effect": "none",
        "is_commit": False,
        "completes_goal": False,
        "fingerprint": {"interaction_purpose": "search"},
    })

    assert tracker.update_contract(prepared, refined) is None
    assert tracker.pending_receipts() == []


def test_pending_effect_can_be_confirmed_by_later_durable_observation() -> None:
    tracker = EffectTracker(goal="提交申请", capability_id="browser.submit", lang="zh")
    before = _obs(url="https://example.test/edit", editable=3, action="提交")
    target = next(item for item in before.elements if item.get("ref") == "commit")
    prepared = asyncio.run(tracker.prepare_click(target=target, before=before))
    assert prepared is not None
    first = asyncio.run(tracker.record(
        prepared=prepared,
        after=_obs(url="https://example.test/list", editable=0),
    ))
    assert first is not None and first.status == "pending"

    changed = asyncio.run(tracker.refresh_pending(
        after=_obs(url="https://example.test/list", editable=0),
        supplemental_evidence=[EffectEvidence(
            evidence_id="field:1",
            kind="submitted_value_present",
            detail="result contains submitted value",
            polarity="positive",
            weight=0.85,
        )],
    ))

    assert len(changed) == 1
    assert changed[0].status == "confirmed_success"


def test_pending_effect_survives_checkpoint_restore() -> None:
    tracker = EffectTracker(goal="提交申请", capability_id="browser.submit", lang="zh")
    before = _obs(url="https://example.test/edit", editable=2, action="提交")
    target = next(item for item in before.elements if item.get("ref") == "commit")
    prepared = asyncio.run(tracker.prepare_click(target=target, before=before))
    assert prepared is not None
    receipt = asyncio.run(tracker.record(
        prepared=prepared,
        after=Observation(
            url=before.url,
            title=before.title,
            elements=before.elements,
            effects=[{"kind": "dom_added", "role": "status", "text": "正在处理"}],
        ),
    ))
    assert receipt is not None and receipt.status == "pending"

    restored = EffectTracker(goal="提交申请", capability_id="browser.submit", lang="zh")
    restored.restore_state(tracker.export_state())

    assert len(restored.pending_receipts()) == 1
    assert restored.pending_receipts()[0].contract_key == receipt.contract_key


def test_new_interaction_supersedes_pending_effect_verification_window() -> None:
    tracker = EffectTracker(goal="提交申请", capability_id="browser.submit", lang="zh")
    before = _obs(url="https://example.test/edit", editable=2, action="提交")
    target = next(item for item in before.elements if item.get("ref") == "commit")
    prepared = asyncio.run(tracker.prepare_click(target=target, before=before))
    assert prepared is not None
    receipt = tracker.defer_until_fresh_observation(
        prepared=prepared,
        reason="post-action observation unavailable",
    )

    changed = tracker.supersede_pending_for_action(
        Decision(tool="browser_click", args={"ref": "open-other-item"}),
    )

    assert len(changed) == 1
    assert changed[0].contract_key == receipt.contract_key
    assert changed[0].status == "unknown"
    assert changed[0].fingerprint["verification_superseded"] is True
    assert tracker.pending_receipts() == []


def test_passive_observation_keeps_pending_effect_verification_window() -> None:
    tracker = EffectTracker(goal="提交申请", capability_id="browser.submit", lang="zh")
    before = _obs(url="https://example.test/edit", editable=2, action="提交")
    target = next(item for item in before.elements if item.get("ref") == "commit")
    prepared = asyncio.run(tracker.prepare_click(target=target, before=before))
    assert prepared is not None
    tracker.defer_until_fresh_observation(
        prepared=prepared,
        reason="post-action observation unavailable",
    )

    changed = tracker.supersede_pending_for_action(
        Decision(tool="browser_observe", args={}),
    )

    assert changed == []
    assert len(tracker.pending_receipts()) == 1


def test_unknown_effect_verification_has_a_bounded_refresh_budget() -> None:
    tracker = EffectTracker(goal="提交申请", capability_id="browser.submit", lang="zh")
    tracker.max_refresh_attempts = 2
    before = _obs(url="https://example.test/edit", editable=2, action="提交")
    target = next(item for item in before.elements if item.get("ref") == "commit")
    prepared = asyncio.run(tracker.prepare_click(target=target, before=before))
    assert prepared is not None
    initial = asyncio.run(tracker.record(
        prepared=prepared,
        after=_obs(url="https://example.test/list", editable=0),
    ))
    assert initial is not None and initial.status in {"pending", "unknown"}

    asyncio.run(tracker.refresh_pending(after=_obs(url="https://example.test/list", editable=0)))
    changed = asyncio.run(
        tracker.refresh_pending(after=_obs(url="https://example.test/list", editable=0)),
    )

    assert len(changed) == 1
    assert changed[0].fingerprint["verification_exhausted"] is True
    assert tracker.pending_receipts() == []


def test_entry_click_that_opens_editor_is_not_recorded_as_commit() -> None:
    tracker = EffectTracker(
        goal="Create a response",
        capability_id="browser.publish",
        lang="en",
        llm=_CustomLLM(),
    )
    before = _obs(url="https://example.test/item", action="Add response")
    target = next(item for item in before.elements if item.get("ref") == "commit")
    prepared = asyncio.run(tracker.prepare_click(target=target, before=before))
    assert prepared is not None

    receipt = asyncio.run(tracker.record(
        prepared=prepared,
        after=_obs(url="https://example.test/item", editable=1, action="Publish"),
    ))

    assert receipt is None
    assert asyncio.run(tracker.prepare_click(target=target, before=before)) is None
    editing = _obs(url="https://example.test/item", editable=1, action="Add response")
    editing_target = next(item for item in editing.elements if item.get("ref") == "commit")
    assert asyncio.run(tracker.prepare_click(target=editing_target, before=editing)) is not None


def test_local_publish_label_that_opens_editor_is_navigation_not_commit() -> None:
    tracker = EffectTracker(
        goal="发布一篇文章",
        capability_id="browser.publish",
        lang="zh",
    )
    before = _obs(url="https://example.test/creator", action="发布")
    target = next(item for item in before.elements if item.get("ref") == "commit")
    prepared = asyncio.run(tracker.prepare_click(target=target, before=before))
    assert prepared is not None
    assert prepared.contract.source == "local_rule"

    receipt = asyncio.run(tracker.record(
        prepared=prepared,
        after=_obs(
            url="https://example.test/creator/editor",
            editable=2,
            action="确认发布",
        ),
    ))

    assert receipt is None
    assert tracker.pending_receipts() == []


def test_confirmed_form_payload_keeps_local_publish_effect_tracking() -> None:
    tracker = EffectTracker(
        goal="发布一篇文章",
        capability_id="browser.publish",
        lang="zh",
    )
    before = _obs(url="https://example.test/editor", editable=1, action="发布")
    target = next(item for item in before.elements if item.get("ref") == "commit")
    prepared = asyncio.run(tracker.prepare_click(target=target, before=before))
    assert prepared is not None
    prepared.contract = prepared.contract.model_copy(update={
        "fingerprint": {
            **dict(prepared.contract.fingerprint),
            "confirmed_fill_count": 1,
        },
    })

    receipt = asyncio.run(tracker.record(
        prepared=prepared,
        after=_obs(
            url="https://example.test/editor/review",
            editable=2,
        ),
    ))

    assert receipt is not None


def test_submit_after_existing_editor_still_uses_effect_verification() -> None:
    tracker = EffectTracker(goal="提交表单", capability_id="browser.submit", lang="zh")
    before = _obs(url="https://example.test/edit", editable=1, action="提交")
    target = next(item for item in before.elements if item.get("ref") == "commit")
    prepared = asyncio.run(tracker.prepare_click(target=target, before=before))
    assert prepared is not None

    receipt = asyncio.run(tracker.record(
        prepared=prepared,
        after=_obs(
            url="https://example.test/edit",
            effects=[{"kind": "dom_added", "role": "status", "text": "提交成功"}],
        ),
    ))

    assert receipt is not None
    assert receipt.status == "confirmed_success"


def test_explicit_outcome_wins_over_new_editable_surface() -> None:
    tracker = EffectTracker(
        goal="Redeem voucher ABC-123",
        capability_id="browser.modify",
        lang="en",
        llm=_CustomLLM(),
    )
    before = _obs(url="https://example.test/voucher", action="Redeem now")
    target = next(item for item in before.elements if item.get("ref") == "commit")
    prepared = asyncio.run(tracker.prepare_click(target=target, before=before))
    assert prepared is not None

    receipt = asyncio.run(tracker.record(
        prepared=prepared,
        after=_obs(
            url="https://example.test/voucher",
            editable=1,
            effects=[{"kind": "dom_added", "role": "status", "text": "Redeem success"}],
        ),
    ))

    assert receipt is not None
    assert receipt.status == "confirmed_success"


class _CustomLLM:
    async def ainvoke_structured(self, _messages, schema):
        return schema(
            is_commit=True,
            action_name="核销券码",
            operation_family="voucher_redemption",
            entity="优惠券",
            side_effect="write",
            completes_goal=True,
            fingerprint={"code": "ABC-123"},
            expected_effects=["券码状态变为已核销"],
            verification_hints=["根据券码回查状态"],
        )


class _UnknownVerdictLLM:
    async def ainvoke_structured(self, _messages, schema):
        return schema(status="unknown", confidence=0.2, evidence_ids=[], reason="insufficient evidence")


def test_model_can_discover_open_ended_custom_action() -> None:
    contract = asyncio.run(discover_effect_contract(
        goal="核销券码 ABC-123",
        capability_id="browser.modify",
        target={"role": "button", "name": "执行核销"},
        lang="zh",
        llm=_CustomLLM(),
    ))

    assert contract.is_commit is True
    assert contract.operation_family == "voucher_redemption"
    assert contract.source == "model"
