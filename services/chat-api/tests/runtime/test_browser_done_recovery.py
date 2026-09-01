from app.enterprise_capabilities.browser.engine.contexts.done_recovery import DoneBlockRecovery
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision


def test_done_block_recovery_observes_then_terminates_bounded_loop() -> None:
    recovery = DoneBlockRecovery(max_attempts=3)

    first = recovery.blocked()
    second = recovery.blocked()
    third = recovery.blocked()

    assert first.retry is not None and first.retry.tool == "browser_observe"
    assert second.retry is not None and second.retry.tool == "browser_observe"
    assert third.terminal is True


def test_real_action_resets_done_block_chain_but_system_probe_does_not() -> None:
    recovery = DoneBlockRecovery(max_attempts=3)
    recovery.blocked()
    recovery.record_action(
        Decision(tool="browser_observe", args={}),
    )
    assert recovery.attempts == 1

    recovery.record_action(
        Decision(tool="browser_click", args={"ref": "e1"}),
    )
    assert recovery.attempts == 0


def test_new_context_phase_starts_a_fresh_done_recovery_chain() -> None:
    recovery = DoneBlockRecovery(max_attempts=3)
    recovery.blocked(fingerprint="awaiting_search")
    recovery.blocked(fingerprint="awaiting_search")

    next_phase = recovery.blocked(fingerprint="awaiting_read")

    assert next_phase.terminal is False
    assert next_phase.attempts == 1
