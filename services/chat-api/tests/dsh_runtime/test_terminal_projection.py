import asyncio

from app.dsh_runtime.conversation.repository import ConversationRepository
from app.dsh_runtime.conversation.terminal_projection import with_terminal


def test_cancelled_projection_closes_an_unfinished_tool() -> None:
    events = [
        {"type": "run.started", "stream_seq": 1},
        {"type": "item.started", "item_kind": "tool", "stream_seq": 2},
    ]
    completed = with_terminal("message-a", "cancelled", events)
    assert [item["type"] for item in completed] == ["run.started", "item.started", "run.cancelled"]
    assert completed[-1]["stream_seq"] == 3
    assert with_terminal("message-a", "cancelled", completed) is completed


def test_repository_repairs_terminal_history_idempotently() -> None:
    class Messages:
        def __init__(self) -> None:
            self.row = {"_id": "row-a", "main_id": "tenant", "message_id": "message-a", "execution_events": [{"type": "run.started", "stream_seq": 1}]}

        async def find_one(self, query):
            return self.row if query.get("message_id") == self.row["message_id"] else None

        async def update_one(self, query, update):
            assert query["_id"] == self.row["_id"]
            self.row.update(update["$set"])

    class Database:
        chat_messages = Messages()
        chat_sessions = object()

    async def check() -> None:
        db = Database()
        repository = ConversationRepository(db)
        await repository.ensure_assistant_terminal(message_id="message-a", tenant_id="tenant", status="cancelled")
        await repository.ensure_assistant_terminal(message_id="message-a", tenant_id="tenant", status="cancelled")
        assert [item["type"] for item in db.chat_messages.row["execution_events"]] == ["run.started", "run.cancelled"]

    asyncio.run(check())
