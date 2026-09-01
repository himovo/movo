from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime
from typing import Dict, Optional

from app.core.db import get_db
from pydantic import BaseModel, Field


class StateVersionConflict(RuntimeError):
    pass


class SubAgentRuntimeRecord(BaseModel):
    subagent_id: str
    parent_task_id: str
    run_id: str = ""
    node_id: str
    assigned_agent: str
    skill_name: str = ""
    skill_version: str = ""
    current_skill: str = ""
    skill_step: int = 0
    step_seq: int = 0
    checkpoint_ref: str = ""
    artifacts_index: Dict[str, object] = Field(default_factory=dict)
    last_error: str = ""
    retries: int = 0
    status: str = "pending"
    env_session_id: str = ""
    storage_state_ref: str = ""
    lease_owner: str = ""
    lease_expires_at: Optional[datetime] = None
    heartbeat_at: Optional[datetime] = None
    state_version: int = 0
    approval_action_id: str = ""
    approval_expires_at: Optional[datetime] = None
    idempotency_cursor: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SubAgentStateStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._records: Dict[str, SubAgentRuntimeRecord] = {}
        self._collection = "runtime_subagent_runs"

    async def upsert(self, record: SubAgentRuntimeRecord) -> SubAgentRuntimeRecord:
        async with self._lock:
            existing = self._records.get(record.subagent_id)
            if existing and existing.state_version != record.state_version:
                raise StateVersionConflict(f"CAS failed for {record.subagent_id}: expected {existing.state_version}, got {record.state_version}")
            
            record.state_version += 1
            record.updated_at = datetime.utcnow()
            self._records[record.subagent_id] = deepcopy(record)
            await self._persist(record)
            return deepcopy(record)

    async def get(self, subagent_id: str) -> Optional[SubAgentRuntimeRecord]:
        async with self._lock:
            row = self._records.get(subagent_id)
            if row:
                return deepcopy(row)
            loaded = await self._load_one({"subagent_id": subagent_id})
            if loaded:
                self._records[subagent_id] = deepcopy(loaded)
                return deepcopy(loaded)
            return None

    async def get_by_node(self, task_id: str, node_id: str, run_id: str = "") -> Optional[SubAgentRuntimeRecord]:
        async with self._lock:
            for rec in self._records.values():
                if rec.parent_task_id == task_id and rec.node_id == node_id and (not run_id or rec.run_id == run_id):
                    # Return the latest one if multiple (though technically shouldn't happen concurrently for same node)
                    return deepcopy(rec)
            query = {"parent_task_id": task_id, "node_id": node_id}
            if run_id:
                query["run_id"] = run_id
            return await self._load_one(query, sort=[("updated_at", -1)])

    async def get_by_action(self, action_id: str) -> Optional[SubAgentRuntimeRecord]:
        async with self._lock:
            for rec in self._records.values():
                if rec.approval_action_id and rec.approval_action_id == action_id:
                    return deepcopy(rec)
            return await self._load_one({"approval_action_id": action_id})

    async def list_by_run(self, run_id: str, limit: int = 20) -> list[SubAgentRuntimeRecord]:
        async with self._lock:
            rows = [deepcopy(rec) for rec in self._records.values() if rec.run_id == run_id]
            if rows:
                rows.sort(key=lambda x: x.updated_at, reverse=True)
                return rows[: max(1, int(limit))]
            loaded = await self._load_many({"run_id": run_id}, sort=[("updated_at", -1)], limit=limit)
            return loaded

    async def get_latest_by_run(self, run_id: str) -> Optional[SubAgentRuntimeRecord]:
        rows = await self.list_by_run(run_id, limit=1)
        return rows[0] if rows else None

    async def _persist(self, record: SubAgentRuntimeRecord) -> None:
        try:
            db = get_db()
            await db[self._collection].update_one(
                {"subagent_id": record.subagent_id},
                {"$set": record.model_dump(mode="json")},
                upsert=True,
            )
        except Exception:
            return

    async def _load_one(self, query: dict, sort: Optional[list[tuple[str, int]]] = None) -> Optional[SubAgentRuntimeRecord]:
        try:
            db = get_db()
            cursor = db[self._collection].find(query)
            if sort:
                cursor = cursor.sort(sort)
                docs = await cursor.to_list(length=1)
                row = docs[0] if docs else None
            else:
                row = await db[self._collection].find_one(query)
            if not row:
                return None
            row.pop("_id", None)
            return SubAgentRuntimeRecord.model_validate(row)
        except Exception:
            return None

    async def _load_many(self, query: dict, sort: Optional[list[tuple[str, int]]] = None, limit: int = 20) -> list[SubAgentRuntimeRecord]:
        try:
            db = get_db()
            cursor = db[self._collection].find(query)
            if sort:
                cursor = cursor.sort(sort)
            docs = await cursor.to_list(length=max(1, int(limit)))
            out: list[SubAgentRuntimeRecord] = []
            for row in docs:
                row.pop("_id", None)
                out.append(SubAgentRuntimeRecord.model_validate(row))
            return out
        except Exception:
            return []
