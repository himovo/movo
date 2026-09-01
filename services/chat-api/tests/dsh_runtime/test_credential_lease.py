import asyncio

from app.dsh_runtime.credential_lease import ActiveTurnCredentialLease


class _Refresher:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[str] = []

    async def refresh_session_credentials(self, session_id: str) -> None:
        self.calls.append(session_id)
        if self.failures:
            self.failures -= 1
            raise RuntimeError("transient")


def test_active_turn_credential_lease_refreshes_until_stopped() -> None:
    async def run() -> None:
        refresher = _Refresher()
        lease = ActiveTurnCredentialLease(
            refresher, session_id="session-a", interval_seconds=0.05
        )
        lease.start()
        await asyncio.sleep(0.13)
        await lease.stop()
        count = len(refresher.calls)
        await asyncio.sleep(0.07)
        assert count >= 2
        assert refresher.calls == ["session-a"] * count

    asyncio.run(run())


def test_transient_refresh_failure_does_not_end_the_lease() -> None:
    async def run() -> None:
        refresher = _Refresher(failures=1)
        lease = ActiveTurnCredentialLease(
            refresher, session_id="session-b", interval_seconds=0.05
        )
        lease.start()
        await asyncio.sleep(0.13)
        await lease.stop()
        assert len(refresher.calls) >= 2

    asyncio.run(run())
