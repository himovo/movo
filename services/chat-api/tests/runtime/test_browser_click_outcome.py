import asyncio

from app.enterprise_capabilities.browser.engine.click_outcome import (
    ClickOutcome,
    ClickOutcomePolicy,
    effect_verification_eligible,
)
from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectContract
from app.enterprise_capabilities.browser.engine.effect_verification.tracker import EffectTracker, PreparedEffect
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def _observation(url: str = "https://example.test/search") -> Observation:
    return Observation(
        url=url,
        title="Search",
        elements=[{"ref": "e7", "role": "link", "name": "Result"}],
        page_text="Results",
        interaction={"tabId": "tab-1"},
    )


def test_delivered_click_is_not_treated_as_progress_and_cannot_be_replayed():
    policy = ClickOutcomePolicy()
    decision = Decision(tool="browser_click", args={"ref": "e7"})
    result = {"action_receipt": {"status": "delivered", "observationPending": False}}

    outcome = policy.evaluate(decision, result, _observation())

    assert outcome.ok is False
    assert outcome.delivered is True
    assert outcome.progressed is False
    assert "页面没有推进" in (policy.blocker(decision, _observation()) or "")


def test_progressed_click_clears_previous_replay_block():
    policy = ClickOutcomePolicy()
    decision = Decision(tool="browser_click", args={"ref": "e7"})
    policy.evaluate(
        decision,
        {"action_receipt": {"status": "delivered", "observationPending": False}},
        _observation(),
    )
    policy.evaluate(
        decision,
        {"action_receipt": {"status": "progressed", "observationPending": False}},
        _observation(),
    )

    assert policy.blocker(decision, _observation()) is None


def test_same_ref_is_allowed_after_interactive_page_state_changes():
    policy = ClickOutcomePolicy()
    decision = Decision(tool="browser_click", args={"ref": "e7"})
    before = _observation()
    policy.evaluate(
        decision,
        {"action_receipt": {"status": "delivered", "observationPending": False}},
        before,
    )
    changed = _observation()
    changed.elements[0]["disabled"] = True

    assert policy.blocker(decision, changed) is None


def test_delivered_commit_remains_eligible_for_business_effect_verification():
    before = Observation(
        url="https://example.test/item/1",
        title="Item",
        elements=[{"ref": "send", "role": "button", "name": "发布"}],
        page_text="发布",
    )
    after = Observation(
        url=before.url,
        title=before.title,
        elements=before.elements,
        page_text=f"{'页面业务内容 ' * 20} 发布 取消 评论成功 {'更多页面内容 ' * 20}",
    )
    prepared = PreparedEffect(
        target_key="send",
        contract=EffectContract(
            action_name="发布",
            operation_family="publish",
            is_commit=True,
            completes_goal=True,
        ),
        before=before,
    )
    outcome = ClickOutcome(
        ok=False,
        error="delivered without structural progress",
        delivered=True,
    )

    assert effect_verification_eligible(
        prepared_effect=prepared,
        action_ok=False,
        click_outcome=outcome,
    ) is True

    receipt = asyncio.run(EffectTracker(
        goal="发表评论",
        capability_id="browser.publish_or_submit",
        lang="zh",
    ).record(prepared=prepared, after=after))

    assert receipt is not None
    assert receipt.status == "confirmed_success"
    assert receipt.blocks_replay is True


def test_failed_or_non_commit_click_does_not_enter_effect_verification():
    not_delivered = ClickOutcome(ok=False, error="target moved")
    delivered = ClickOutcome(ok=False, delivered=True)

    assert effect_verification_eligible(
        prepared_effect=object(),
        action_ok=False,
        click_outcome=not_delivered,
    ) is False
    assert effect_verification_eligible(
        prepared_effect=None,
        action_ok=False,
        click_outcome=delivered,
    ) is False


def test_delivered_commit_without_business_evidence_stays_unknown():
    observation = Observation(
        url="https://example.test/item/1",
        title="Item",
        elements=[{"ref": "send", "role": "button", "name": "发布"}],
        page_text="发布",
    )
    prepared = PreparedEffect(
        target_key="send",
        contract=EffectContract(
            action_name="发布",
            operation_family="publish",
            is_commit=True,
            completes_goal=True,
        ),
        before=observation,
    )

    receipt = asyncio.run(EffectTracker(
        goal="发表评论",
        capability_id="browser.publish_or_submit",
        lang="zh",
    ).record(prepared=prepared, after=observation))

    assert receipt is not None
    assert receipt.status == "unknown"
    assert receipt.blocks_replay is True
