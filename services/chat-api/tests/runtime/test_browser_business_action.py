from __future__ import annotations

from app.enterprise_capabilities.browser.engine.business_action import (
    BusinessActionLedger,
    browser_target_identity,
)
from app.enterprise_capabilities.browser.engine.contexts.general_mission import GeneralMissionLedger
from app.enterprise_capabilities.browser.engine.desktop_agent_executor import _obs_from_payload, _update_obs
from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectContract, EffectReceipt
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _contract(ref: str) -> EffectContract:
    return EffectContract(
        action_name="发布",
        operation_family="publish",
        intended_operation="comment",
        intended_entity="post",
        fingerprint={
            "interaction_target_id": ref,
            "confirmed_fill_hashes": ["payload-a"],
        },
    )


def _observation(ref: str, revision: str) -> Observation:
    return Observation(
        url="https://example.test/post/42?sid=secret",
        title="Post",
        revision=revision,
        state_fingerprint=f"state-{revision}",
        elements=[{"ref": ref, "role": "button", "name": "发布"}],
    )


def test_business_action_identity_survives_spa_ref_changes() -> None:
    ledger = BusinessActionLedger()
    first = ledger.bind_contract(_contract("e7"), _observation("e7", "r1"))
    second = ledger.bind_contract(_contract("e99"), _observation("e99", "r2"))

    assert first.key() != second.key()
    assert first.business_action_id == second.business_action_id
    assert first.action_attempt_id == second.action_attempt_id
    assert first.observation_revision == "r1"
    assert second.observation_revision == "r2"


def test_business_action_identity_separates_distinct_detail_targets() -> None:
    ledger = BusinessActionLedger()
    observation = _observation("e7", "r1")

    first = ledger.bind_contract(
        _contract("e7"),
        observation,
        target_hint="https://example.test/post/42",
    )
    second = ledger.bind_contract(
        _contract("e8"),
        observation,
        target_hint="https://example.test/post/43",
    )

    assert first.business_action_id != second.business_action_id


def test_business_action_identity_separates_content_ids_on_same_detail_url() -> None:
    ledger = BusinessActionLedger()
    observation = _observation("e7", "r1")

    first = ledger.bind_contract(
        _contract("e7"),
        observation,
        target_hint="attribute:data-note-id:post-42",
    )
    second = ledger.bind_contract(
        _contract("e8"),
        observation,
        target_hint="attribute:data-note-id:post-43",
    )

    assert first.business_action_id != second.business_action_id


def test_mission_counts_one_business_action_once_across_contract_keys() -> None:
    mission = GeneralMissionLedger(enabled=True, minimum_effects=2)
    first = EffectReceipt(
        contract_key="dom-contract-1",
        business_action_id="comment-post-42",
        status="confirmed_success",
        action_name="发布",
    )
    second = first.model_copy(update={"contract_key": "dom-contract-2"})

    assert mission.record_effect(first) is True
    assert mission.record_effect(second) is False
    assert mission.confirmed_effects == 1


def test_business_action_ledger_checkpoint_preserves_replay_guard() -> None:
    first = BusinessActionLedger()
    contract = first.bind_contract(_contract("e7"), _observation("e7", "r1"))
    first.record(EffectReceipt(
        contract_key=contract.key(),
        business_action_id=contract.business_action_id,
        action_attempt_id=contract.action_attempt_id,
        business_target_id=contract.business_target_id,
        status="unknown",
        action_name="发布",
    ))

    restored = BusinessActionLedger()
    restored.restore_state(first.export_state())
    rebound = restored.bind_contract(_contract("e88"), _observation("e88", "r2"))

    assert restored.replay_blocker(rebound) is not None


def test_missing_post_action_snapshot_invalidates_old_refs() -> None:
    current = _observation("e7", "r1")

    updated = _update_obs(current, "browser_click", {"ok": True})

    assert updated.fresh is False
    assert updated.elements == []
    assert updated.url == current.url


def test_payload_observation_is_marked_fresh_and_fingerprinted() -> None:
    observation = _obs_from_payload({
        "url": "https://example.test/post/42",
        "title": "Post",
        "revision": "tab-1:7",
        "pageText": "Body",
        "elements": [{"ref": "e4", "role": "button", "name": "发布"}],
    })

    assert observation is not None
    assert observation.fresh is True
    assert observation.revision == "tab-1:7"
    assert observation.state_fingerprint


def test_target_identity_ignores_auth_and_tracking_query_values() -> None:
    system, target = browser_target_identity(
        "https://example.test/post/42?sid=secret&utm_source=x&item=7",
    )

    assert system == "example.test"
    assert target == "https://example.test/post/42?item=7"
