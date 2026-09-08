from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation
from app.enterprise_capabilities.browser.engine.effect_verification.form_transaction import FormTransactionTracker
from app.enterprise_capabilities.browser.engine.form_input.fill_retry import FillRetryPolicy
from app.enterprise_capabilities.browser.engine.form_input.step_reconciliation import reconcile_input_step


def observation(value="", ref="e1"):
    return Observation(url="https://example.test", title="fixture", elements=[{
        "ref": ref, "selector": "#editor", "backendNodeId": 42,
        "role": "textbox", "editable": True, "value": value,
    }])


def test_ambiguous_fill_observe_retry_confirm_uses_one_transaction():
    tracker, retry = FormTransactionTracker(), FillRetryPolicy()
    before = observation()
    fill = Decision("browser_fill", {"ref": "e1", "value": "hello"})

    def step(decision, previous, after, result=None, ok=True):
        return reconcile_input_step(decision=decision, before=previous, after=after,
                                    result=result, ok=ok, error=None, transaction=tracker,
                                    retry=retry, lang="zh")

    first = step(fill, before, before, {"fill_receipt": {"status": "ambiguous"}})
    assert not tracker.has_confirmed_fill()
    assert first.next_decision.tool == "browser_observe"
    fresh = observation(ref="e9")
    second = step(first.next_decision, before, fresh)
    assert second.next_decision.tool == "browser_fill"
    assert second.next_decision.args["ref"] == "e9"
    final = step(second.next_decision, fresh, fresh, {"fill_receipt": {"status": "confirmed"}})
    assert final.next_decision is None
    assert final.observation.elements[0]["value"] == "hello"
    assert tracker.has_confirmed_fill()


def test_already_applied_ambiguous_fill_is_confirmed_without_second_mutation():
    tracker, retry = FormTransactionTracker(), FillRetryPolicy()
    before = observation()
    first = reconcile_input_step(
        decision=Decision("browser_fill", {"ref": "e1", "value": "hello"}),
        before=before, after=before, result={"fill_receipt": {"status": "ambiguous"}},
        ok=True, error=None, transaction=tracker, retry=retry, lang="zh",
    )
    result = reconcile_input_step(
        decision=first.next_decision, before=before, after=observation("hello", "e9"),
        result={}, ok=True, error=None, transaction=tracker, retry=retry, lang="zh",
    )
    assert result.next_decision is None
    assert tracker.has_confirmed_fill()
