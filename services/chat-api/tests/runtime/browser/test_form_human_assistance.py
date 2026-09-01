from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectReceipt
from app.enterprise_capabilities.browser.engine.form_human_assistance import (
    FORM_COMMIT_CATEGORY,
    FORM_EFFECT_VERIFY_CATEGORY,
    FORM_TASK_COMPLETION_CATEGORY,
    build_commit_assistance_decision,
    build_effect_verification_decision,
    build_form_repair_assistance_decision,
    build_task_completion_confirmation_decision,
    manual_effect_receipt,
    resume_contract,
    resume_outcome,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _receipt() -> EffectReceipt:
    return EffectReceipt(
        contract_key="save:1",
        status="unknown",
        action_name="保存为草稿",
        operation_family="save",
        side_effect="write",
        completes_goal=True,
        fingerprint={"verification_exhausted": True},
        reason="verification budget exhausted",
    )


def test_commit_assistance_is_typed_and_blocks_completed_replay() -> None:
    decision = build_commit_assistance_decision(
        reason="no semantic commit control in active form",
        candidate_refs=(),
        lang="zh",
    )

    contract = decision.args["handoff"]["contract"]
    assert decision.tool == "browser_ask_user"
    assert decision.args["category"] == FORM_COMMIT_CATEGORY
    assert contract["replay_policy"] == "never_replay_after_human_completed"


def test_effect_verification_handoff_and_resume_are_contract_bound() -> None:
    decision = build_effect_verification_decision(_receipt(), lang="zh")
    contract = decision.args["handoff"]["contract"]
    signal = {
        "type": "human_intervention_completed",
        "human_outcome": "succeeded",
        "assistance_contract": contract,
    }

    assert decision.args["category"] == FORM_EFFECT_VERIFY_CATEGORY
    assert resume_contract(signal)["contract_id"] == contract["contract_id"]
    assert resume_outcome(signal, expected_kind=FORM_EFFECT_VERIFY_CATEGORY) == "succeeded"
    assert resume_outcome(signal, expected_kind=FORM_COMMIT_CATEGORY) == ""


def test_manual_effect_outcome_preserves_receipt_identity_and_replay_block() -> None:
    observation = Observation(
        url="https://example.test/list",
        title="list",
        elements=[],
        revision="r2",
        fresh=True,
    )

    receipt = manual_effect_receipt(
        previous=_receipt(),
        outcome="succeeded",
        observation=observation,
    )

    assert receipt.contract_key == "save:1"
    assert receipt.status == "confirmed_success"
    assert receipt.fingerprint["human_verified"] is True
    assert receipt.blocks_replay


def test_task_completion_confirmation_has_continue_and_complete_outcomes() -> None:
    decision = build_task_completion_confirmation_decision(
        reason="possible human commit",
        evidence=("editor disappeared",),
        lang="zh",
    )
    contract = decision.args["handoff"]["contract"]

    assert decision.args["category"] == FORM_TASK_COMPLETION_CATEGORY
    assert contract["allowed_outcomes"] == [
        "task_completed", "continue_agent", "uncertain",
    ]
    assert contract["replay_policy"] == "never_replay_after_human_task_completed"


def test_form_repair_assistance_uses_task_completion_resume_contract() -> None:
    decision = build_form_repair_assistance_decision(
        reason="editor action blocked",
        lang="zh",
    )
    contract = decision.args["handoff"]["contract"]

    assert decision.args["category"] == FORM_TASK_COMPLETION_CATEGORY
    assert contract["action"] == "repair_or_complete_form"
    assert contract["allowed_outcomes"] == [
        "task_completed", "continue_agent", "uncertain",
    ]
    assert contract["replay_policy"] == "never_replay_after_human_task_completed"
