"""A duplicate in-flight request must observe the original execution."""
import asyncio

from tests.dsh_runtime.test_step5_tool_policy import (
    FakeExecutor, FakeProfileStore, FakeRepository, EnterpriseToolService,
    ToolExecuteRequest, _claims, _profile, _tool, service_module,
)


def test_concurrent_duplicate_executes_once_and_keeps_owner_private(monkeypatch):
    async def verify():
        tool = _tool('askai_http_read', source='http', approval=False)
        class RacingRepository(FakeRepository):
            first_reads = 0
            barrier = asyncio.Event()
            async def receipt_by_idempotency(self, key):
                if self.first_reads < 8:
                    self.first_reads += 1
                    if self.first_reads == 8:
                        self.barrier.set()
                    await self.barrier.wait()
                    return None
                return await super().receipt_by_idempotency(key)
        repository = RacingRepository()
        executor = FakeExecutor()
        executor.delay = .15
        monkeypatch.setattr(service_module, 'external_tool_service', executor)
        service = EnterpriseToolService(repository, FakeProfileStore(_profile(tool)))
        request = ToolExecuteRequest(
            profileVersion='profile-a', sessionId='session-a', toolName=tool.name,
            actionId='duplicate', idempotencyKey='same-request', arguments={},
        )
        results = await asyncio.gather(*(service.execute(request, _claims([tool])) for _ in range(8)))
        assert len(executor.calls) == 1
        assert all(result.status == 'succeeded' for result in results)
        assert all('execution_owner' not in result.model_dump() for result in results)
    asyncio.run(verify())
