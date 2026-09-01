from app.enterprise_capabilities.browser.engine.post_action_observation import (
    observation_retry_required,
    reconcile_post_action_observation,
)


def test_reconciles_fresh_observation_without_losing_short_lived_effects() -> None:
    action = {
        "observation_pending": True,
        "action_receipt": {"status": "dispatched_observation_pending", "observationPending": True},
        "observation": {
            "url": "https://example.test/before",
            "elements": [{"ref": "e1"}],
            "effects": [{"kind": "network_response", "status": 200}],
        },
    }
    observed = {
        "observation": {
            "url": "https://example.test/after",
            "title": "After",
            "elements": [{"ref": "e2"}],
        },
    }

    result = reconcile_post_action_observation(action, observed)

    assert observation_retry_required(action) is True
    assert result["observation_pending"] is False
    assert result["observation"]["url"] == "https://example.test/after"
    assert result["observation"]["effects"][0]["status"] == 200
    assert result["action_receipt"]["status"] == "observed_after_retry"


def test_does_not_claim_reconciliation_without_a_fresh_observation() -> None:
    action = {"observation_pending": True, "observation": {"url": "https://example.test", "elements": []}}

    result = reconcile_post_action_observation(action, None)

    assert result["observation_pending"] is True
