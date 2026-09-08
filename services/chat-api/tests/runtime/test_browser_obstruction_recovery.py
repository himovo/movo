import json
from dataclasses import replace

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord
from app.enterprise_capabilities.browser.engine.interaction_target_recovery import InteractionTargetRecovery
from app.enterprise_capabilities.browser.engine.obstruction_evidence import obstruction_evidence
from app.enterprise_capabilities.browser.engine.passive_wait_recovery import recover_passive_wait


def test_covered_node_is_not_hidden_or_retried_as_missing():
    obs = Observation(url="https://example.test", title="Page", revision="r1", elements=[
        {"ref": "e1", "backendNodeId": 42, "role": "link", "name": "Profile",
         "href": "https://example.test/profile", "hitTestable": True},
    ])
    decision = Decision("browser_click", {"ref": "e1"})
    error = 'Click target moved or is covered; diagnostic=' + json.dumps({
        "targetResolved": True, "hitsTarget": False,
        "hit": {"tag": "div", "text": "overlay"},
    })
    recovery = InteractionTargetRecovery()
    recovery.record_failure(decision, obs, error)
    planning = recovery.planning_observation(obs)
    assert len(planning.elements) == 1
    assert planning.elements[0]["href"] == obs.elements[0]["href"]
    assert planning.elements[0]["hitTestable"] is False
    assert "覆盖" in recovery.blocker(decision, obs)
    assert "occluded_targets" in recovery.augment_state_ledger({})["notes"][0]
    # Only newer, positive hit evidence releases the block.
    recovery.planning_observation(replace(obs, revision="r2"))
    assert recovery.blocker(decision, obs) is None


def test_invalid_or_missing_node_diagnostic_is_not_called_obstruction():
    assert obstruction_evidence("diagnostic=oops") is None
    assert obstruction_evidence('diagnostic={"targetResolved":false,"hitsTarget":false,"hit":{}}') is None


def test_plain_wait_is_bounded_but_real_action_starts_new_wait_budget():
    obs = Observation(url="https://example.test", title="Page", elements=[])
    decision = Decision("browser_wait_for", {"seconds": 3})
    def record(action):
        return StepRecord(observation=obs, decision=action, ok=True, error=None, result_digest="")
    history = [record(decision), record(decision)]
    assert recover_passive_wait(decision, obs, history).tool == "browser_observe"
    history.append(record(Decision("browser_scroll", {"direction": "down"})))
    assert recover_passive_wait(decision, obs, history) is decision
    textual = Decision("browser_wait_for", {"text": "Ready"})
    assert recover_passive_wait(textual, obs, history) is textual
