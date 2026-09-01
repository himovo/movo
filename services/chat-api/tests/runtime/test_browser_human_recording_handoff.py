import asyncio

from app.enterprise_capabilities.browser.engine.human_recording_handoff import begin_recorded_human_handoff


def test_recording_failure_does_not_block_human_ownership() -> None:
    calls = []

    class Bridge:
        async def send_command(self, command, **kwargs):
            calls.append((command, kwargs))
            if command == "recording_start":
                raise RuntimeError("recorder unavailable")

    active_id = asyncio.run(begin_recorded_human_handoff(
        Bridge(), recording_id="assist-1", run_id="run-1",
        node_id="browser", category="browser",
    ))

    assert active_id == ""
    assert [command for command, _ in calls] == ["recording_start", "set_owner"]

