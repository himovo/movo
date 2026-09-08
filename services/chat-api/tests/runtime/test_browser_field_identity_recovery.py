"""Cross-observation identity and bounded recovery regressions (site neutral)."""
from dataclasses import replace

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation
from app.enterprise_capabilities.browser.engine.form_input.identity import find_field
from app.enterprise_capabilities.browser.engine.form_input.fill_retry import FillRetryPolicy
from app.enterprise_capabilities.browser.engine.form_input.fill_outcome import resolve_fill_outcome
from app.enterprise_capabilities.browser.engine.form_input.observation_update import apply_confirmed_fill


def field(**changes):
    return {"ref": "e1", "selector": "#editor", "backendNodeId": 10,
            "editable": True, "role": "textbox", "value": "", **changes}


def obs(*elements, url="https://example.test/item"):
    return Observation(url=url, title="fixture", elements=list(elements))


def test_identity_does_not_use_reassigned_ref_or_first_duplicate():
    assert find_field([field(selector="#other", backendNodeId=20)], field(), "e1") is None
    assert find_field([field(backendNodeId=20), field(backendNodeId=30)], field(), "e1") is None
    correct = field(ref="e9")
    assert find_field([field(backendNodeId=20), correct], field(), "e1") is correct


def test_scope_prevents_cross_form_rebinding():
    assert find_field([field(scopeSelector="#reply")], field(scopeSelector="#main"), "e1") is None


def test_receipt_never_fabricates_value_on_replacement_or_other_page():
    before = obs(field())
    for after in (obs(field(backendNodeId=20)), obs(field(), url="https://example.test/other")):
        updated = apply_confirmed_fill(after, before=before, args={"ref": "e1", "value": "hello"},
                                       result={"fill_receipt": {"status": "confirmed"}}, ok=True)
        assert updated.elements[0]["value"] == ""


def test_receipt_follows_proven_node_not_old_ref():
    before = obs(field())
    after = obs(field(ref="e2"), field(selector="#other", backendNodeId=20))
    updated = apply_confirmed_fill(after, before=before, args={"ref": "e1", "value": "hello"},
                                   result={"fill_receipt": {"status": "confirmed"}}, ok=True)
    assert [item["value"] for item in updated.elements] == ["hello", ""]


def pending():
    retry = FillRetryPolicy()
    retry.after_result(Decision("browser_fill", {"ref": "e1", "value": "hello"}),
                       ok=False, error="value_not_applied", before=obs(field()))
    return retry


def test_missing_field_recovery_is_bounded_and_survives_restore():
    retry = pending()
    assert retry.after_observation(obs()).tool == "browser_observe"
    restored = FillRetryPolicy()
    restored.restore_state(retry.export_state())
    assert restored.after_observation(obs()).tool == "browser_ask_user"
    assert restored.after_observation(obs()) is None


def test_recovery_never_mutates_other_page_or_disabled_field():
    assert pending().after_observation(obs(field(), url="https://example.test/other")).tool == "browser_ask_user"
    assert pending().after_observation(obs(field(disabled=True))).tool == "browser_ask_user"


def test_stale_observation_does_not_consume_missing_field_budget():
    retry = pending()
    assert retry.after_observation(replace(obs(), fresh=False)).tool == "browser_observe"
    assert retry.after_observation(obs()).tool == "browser_observe"
    assert retry.after_observation(obs(field(value="hello"))) is None


def test_transport_success_is_not_fill_confirmation():
    for receipt in ({"status": "ambiguous"}, {"status": "unknown"}, "invalid"):
        assert resolve_fill_outcome(result={"fill_receipt": receipt}, ok=True).status == "ambiguous"
