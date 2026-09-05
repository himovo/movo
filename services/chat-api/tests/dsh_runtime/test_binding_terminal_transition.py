from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.dsh_runtime.bindings.repository import KernelBindingRepository


class _Collection:
    def __init__(self) -> None:
        self.row = {
            "binding_id": "binding-a",
            "status": "running",
            "active_turn": {"message_id": "message-a", "status": "running"},
        }

    async def update_one(self, query, update):
        matched = (
            query.get("binding_id") == self.row["binding_id"]
            and query.get("active_turn.message_id") == self.row["active_turn"]["message_id"]
            and query.get("active_turn.status") == self.row["active_turn"]["status"]
        )
        if matched:
            values = update["$set"]
            self.row["status"] = values["status"]
            self.row["active_turn"]["status"] = values["active_turn.status"]
        return SimpleNamespace(matched_count=1 if matched else 0)

    async def find_one_and_update(self, query, update, **_kwargs):
        terminal = self.row["active_turn"] is None or self.row["active_turn"]["status"] in {
            "completed", "failed", "cancelled",
        }
        if query.get("binding_id") != self.row["binding_id"] or not terminal:
            return None
        values = update["$set"]
        self.row["status"] = values["status"]
        self.row["active_turn"] = dict(values["active_turn"])
        return dict(self.row)


class _Db:
    def __init__(self, collection: _Collection) -> None:
        self.collection = collection

    def __getitem__(self, _name: str):
        return self.collection


def test_first_terminal_status_wins_and_same_status_is_idempotent() -> None:
    async def run() -> None:
        collection = _Collection()
        repository = KernelBindingRepository(_Db(collection))

        assert await repository.finish_turn(
            "binding-a", message_id="message-a", status="completed"
        ) is True
        assert await repository.finish_turn(
            "binding-a", message_id="message-a", status="cancelled"
        ) is False
        assert collection.row["active_turn"]["status"] == "completed"
        assert await repository.finish_turn(
            "binding-a", message_id="message-a", status="completed"
        ) is False

    asyncio.run(run())


def test_cancelled_turn_immediately_releases_admission_for_the_next_turn() -> None:
    async def run() -> None:
        collection = _Collection()
        repository = KernelBindingRepository(_Db(collection))

        assert await repository.finish_turn(
            "binding-a", message_id="message-a", status="cancelled"
        ) is True
        claimed = await repository.claim_turn(
            "binding-a", message_id="message-b", request_id="request-b"
        )

        assert claimed is not None
        assert claimed["active_turn"]["message_id"] == "message-b"
        assert claimed["active_turn"]["status"] == "running"

    asyncio.run(run())
