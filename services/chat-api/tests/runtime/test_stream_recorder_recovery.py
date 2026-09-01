import asyncio

from app.infrastructure.execution_events.persistence import V3StreamRecorder, compact_v3_events


def test_compacted_text_preserves_recovery_sequence_range():
    events = [
        {"v": 3, "event_id": "a", "id": "a", "type": "item.delta", "item_kind": "final_answer", "payload": {"text": "hello"}, "stream_seq": 4, "stream_seq_end": 4},
        {"v": 3, "event_id": "b", "id": "b", "type": "item.delta", "item_kind": "final_answer", "payload": {"text": " world"}, "stream_seq": 5, "stream_seq_end": 5},
    ]

    compacted = compact_v3_events(events)

    assert len(compacted) == 1
    assert compacted[0]["type"] == "item.completed"
    assert compacted[0]["payload"]["text"] == "hello world"
    assert compacted[0]["stream_seq"] == 4
    assert compacted[0]["stream_seq_end"] == 5
    assert compacted[0]["id"] == "a"


def test_finalize_flushes_tail_buffer_before_closing():
    class FakeStore:
        def __init__(self):
            self.events = []
            self.status = ""

        async def append_events(self, _session_id, _message_id, events, **_kwargs):
            self.events.extend(events)

        async def get_events_for_message(self, _message_id):
            return list(self.events)

        async def replace_events(self, _message_id, events):
            self.events = list(events)

        async def finalize(self, _message_id, *, summary, status):
            self.status = status

    async def exercise():
        store = FakeStore()
        recorder = V3StreamRecorder(store, "session", "message", batch_size=25)
        recorder.observe_line('{"v":3,"event_id":"one","id":"one","type":"run.started","revision":1,"payload":{}}\n')

        await recorder.finalize(status="completed")

        assert len(store.events) == 1
        assert store.status == "completed"

    asyncio.run(exercise())


def test_finalize_waits_for_scheduled_batch_flush_before_compacting():
    class SlowStore:
        def __init__(self):
            self.events = []
            self.append_started = asyncio.Event()
            self.allow_append = asyncio.Event()
            self.replaced = False

        async def append_events(self, _session_id, _message_id, events, **_kwargs):
            self.append_started.set()
            await self.allow_append.wait()
            self.events.extend(events)

        async def get_events_for_message(self, _message_id):
            return list(self.events)

        async def replace_events(self, _message_id, events):
            self.replaced = True
            self.events = list(events)

        async def finalize(self, _message_id, *, summary, status):
            return None

    async def exercise():
        store = SlowStore()
        recorder = V3StreamRecorder(store, "session", "message", batch_size=1)
        recorder.observe_line('{"v":3,"event_id":"one","id":"one","type":"run.started","revision":1,"payload":{},"stream_seq":1,"stream_seq_end":1}\n')
        await store.append_started.wait()

        finalize_task = asyncio.create_task(recorder.finalize())
        await asyncio.sleep(0)
        assert not finalize_task.done()
        store.allow_append.set()
        await finalize_task

        assert store.replaced is False
        assert len(store.events) == 1

    asyncio.run(exercise())
