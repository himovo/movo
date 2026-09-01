from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Dict, Optional

from app.core.db import get_db
from app.governance.action_receipt import ActionReceipt


class ActionReceiptStore:
    def __init__(self, running_timeout_seconds: int = 300) -> None:
        self.running_timeout_seconds = max(10, int(running_timeout_seconds))
        self._lock = asyncio.Lock()
        self._by_action_id: Dict[str, ActionReceipt] = {}
        self._by_idempotency: Dict[str, ActionReceipt] = {}
        self._by_business: Dict[str, Dict[str, ActionReceipt]] = {}
        self._collection = "runtime_action_receipts"

    async def find_by_idempotency(self, key: str) -> Optional[ActionReceipt]:
        async with self._lock:
            row = self._by_idempotency.get(key)
            if row:
                return deepcopy(row)
            loaded = await self._load_one({"idempotency_key": key})
            if loaded:
                self._cache(loaded)
                return deepcopy(loaded)
            return None

    async def find_by_action_id(self, action_id: str) -> Optional[ActionReceipt]:
        async with self._lock:
            row = self._by_action_id.get(action_id)
            if row:
                return deepcopy(row)
            loaded = await self._load_one({"action_id": action_id})
            if loaded:
                self._cache(loaded)
                return deepcopy(loaded)
            return None

    async def find_succeeded_by_business_key(self, key: str) -> Optional[ActionReceipt]:
        """Return the latest confirmed receipt for a durable business key.

        This is intentionally separate from attempt idempotency.  Callers
        decide whether a business key should guard future runs; the store only
        persists and retrieves facts.
        """
        normalized = str(key or "").strip()
        if not normalized:
            return None
        async with self._lock:
            cached_rows = [
                row for row in self._by_business.get(normalized, {}).values()
                if row.status == "succeeded"
            ]
            cached = max(cached_rows, key=lambda item: item.updated_at) if cached_rows else None
            loaded = await self._load_latest(
                {"business_key": normalized, "status": "succeeded"},
            )
            if loaded:
                self._cache(loaded)
            latest = max(
                (item for item in (cached, loaded) if item is not None),
                key=lambda item: item.updated_at,
                default=None,
            )
            return deepcopy(latest) if latest is not None else None

    async def count_succeeded_by_business_key(self, key: str) -> int:
        normalized = str(key or "").strip()
        if not normalized:
            return 0
        async with self._lock:
            local_count = sum(
                1 for row in self._by_business.get(normalized, {}).values()
                if row.status == "succeeded"
            )
        try:
            db = get_db()
            database_count = int(await db[self._collection].count_documents({
                "business_key": normalized,
                "status": "succeeded",
            }))
            return max(local_count, database_count)
        except Exception:
            return local_count

    async def upsert(self, receipt: ActionReceipt) -> ActionReceipt:
        async with self._lock:
            receipt.updated_at = datetime.utcnow()
            self._cache(receipt)
            await self._persist(receipt)
            return deepcopy(receipt)

    def _cache(self, receipt: ActionReceipt) -> None:
        cached = deepcopy(receipt)
        self._by_action_id[receipt.action_id] = cached
        self._by_idempotency[receipt.idempotency_key] = deepcopy(cached)
        business_key = str(receipt.business_key or "").strip()
        if business_key:
            self._by_business.setdefault(business_key, {})[receipt.action_id] = deepcopy(cached)

    async def recover_stale_running(self) -> int:
        async with self._lock:
            now = datetime.utcnow()
            changed = 0
            try:
                db = get_db()
                stale_docs = await db[self._collection].find(
                    {
                        "status": "running",
                        "updated_at": {"$lt": (now - timedelta(seconds=self.running_timeout_seconds)).isoformat()},
                    }
                ).to_list(length=500)
                for raw in stale_docs:
                    raw.pop("_id", None)
                    row = ActionReceipt.model_validate(raw)
                    self._cache(row)
            except Exception:
                pass
            for action_id, row in list(self._by_action_id.items()):
                if row.status != "running":
                    continue
                if row.updated_at + timedelta(seconds=self.running_timeout_seconds) < now:
                    if self._has_trustworthy_evidence(row.evidence):
                        row.status = "succeeded"
                    else:
                        row.status = "abandoned"
                    row.updated_at = now
                    self._cache(row)
                    await self._persist(row)
                    changed += 1
            return changed

    async def reconcile_abandoned(self) -> int:
        async with self._lock:
            changed = 0
            for action_id, row in list(self._by_action_id.items()):
                if row.status != "abandoned":
                    continue
                if self._has_trustworthy_evidence(row.evidence):
                    row.status = "succeeded"
                    row.updated_at = datetime.utcnow()
                    self._cache(row)
                    await self._persist(row)
                    changed += 1
            return changed

    def _has_trustworthy_evidence(self, evidence: dict | None) -> bool:
        evidence = dict(evidence or {})
        if evidence.get("screenshot_hash") and evidence.get("url"):
            return True
        if evidence.get("dom_snippet_hash") and evidence.get("url"):
            return True
        if evidence.get("receipt_id"):
            return True
        return False

    async def _persist(self, receipt: ActionReceipt) -> None:
        try:
            db = get_db()
            await db[self._collection].update_one(
                {"idempotency_key": receipt.idempotency_key},
                {"$set": receipt.model_dump(mode="json")},
                upsert=True,
            )
        except Exception:
            return

    async def _load_one(self, query: dict) -> Optional[ActionReceipt]:
        try:
            db = get_db()
            row = await db[self._collection].find_one(query)
            if not row:
                return None
            row.pop("_id", None)
            return ActionReceipt.model_validate(row)
        except Exception:
            return None

    async def _load_latest(self, query: dict) -> Optional[ActionReceipt]:
        try:
            db = get_db()
            row = await db[self._collection].find_one(query, sort=[("updated_at", -1)])
            if not row:
                return None
            row.pop("_id", None)
            return ActionReceipt.model_validate(row)
        except Exception:
            return None

    async def ensure_indexes(self) -> None:
        try:
            db = get_db()
            coll = db[self._collection]
            await coll.create_index("idempotency_key", unique=True)
            await coll.create_index("action_id", unique=True)
            await coll.create_index([("status", 1), ("updated_at", -1)])
            await coll.create_index([("business_key", 1), ("status", 1), ("updated_at", -1)])
        except Exception:
            return
