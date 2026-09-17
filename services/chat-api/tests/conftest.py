"""Real-MongoDB test harness for the chat-api test suite.

Server requirements
-------------------
The guarantees this harness exists to prove (unique index behaviour,
concurrent upserts, partial-filter-expression indexes) are only meaningful
against a real server:

- MongoDB >= 3.2 is required for ``partialFilterExpression`` indexes
  (``app/dsh_runtime/bindings/repository.py`` relies on one). The repo pins
  pymongo 3.12.3 / motor 2.5.1, both of which support
  ``partialFilterExpression``. The local deployment pins ``mongo:6.0.20``
  (docker-compose.yml).

Connecting
----------
The fixture resolves its server from the environment:

- ``MOVO_TEST_MONGODB_URI`` — default ``mongodb://localhost:27017`` (the
  Compose mongod, or the dedicated ``movo-test-mongo`` container published
  on host port 27017).

Provision a local server if none is reachable::

    docker run -d --name movo-test-mongo -p 27017:27017 mongo:6.0.20

Semantics
---------
- The fixture **fails, never skips**, when the server is unreachable. Index
  and race assertions are meaningless without a real server; skipping would
  silently turn those tests into theatre.
- Every test receives its own uniquely named database
  (``movo_test_<uuid>``), which is dropped on teardown. Tests can never
  observe each other's rows and no database outside the ``movo_test_``
  prefix is ever touched.
- motor 2.5.1 pins the event loop at client creation, so the fixture creates
  a dedicated loop per test and binds the motor client to it. Drive async
  repository/service code through ``harness.run(...)``, not
  ``asyncio.run(...)`` — the client's futures would otherwise be attached to
  a different loop.
- To point application code at the test database, monkeypatch the ``get_db``
  seam the same way the fake-collection tests do (see
  tests/services/test_skill_sharing.py)::

      monkeypatch.setattr(module_under_test, "get_db", lambda: harness.db)
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
from typing import Any, Coroutine

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.errors import PyMongoError

MOVO_TEST_MONGODB_URI_ENV = "MOVO_TEST_MONGODB_URI"
DEFAULT_TEST_MONGODB_URI = "mongodb://localhost:27017"
DB_NAME_PREFIX = "movo_test_"


@dataclass(frozen=True)
class RealMongoHarness:
    """A real motor database bound to a dedicated event loop.

    ``db`` is a real ``AsyncIOMotorDatabase``: construct repositories with it
    directly, or monkeypatch the app's ``get_db`` to return it.
    """

    db: Any
    loop: asyncio.AbstractEventLoop
    name: str
    uri: str

    def run(self, awaitable: Coroutine[Any, Any, Any]) -> Any:
        """Drive a coroutine to completion on the database's event loop."""
        return self.loop.run_until_complete(awaitable)


@pytest.fixture
def real_mongo_db():
    """Yield a clean real-mongo database; drop it on teardown.

    Fails the test (never skips) when the configured mongod is unreachable.
    """
    uri = os.environ.get(MOVO_TEST_MONGODB_URI_ENV, DEFAULT_TEST_MONGODB_URI)
    admin = MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=2000)
    try:
        try:
            admin.admin.command("ping")
        except PyMongoError as exc:
            pytest.fail(
                f"A real MongoDB server is required for this test, but {uri} is"
                f" unreachable: {exc!r}. Set {MOVO_TEST_MONGODB_URI_ENV} to a"
                " reachable mongod, or start one locally with: docker run -d"
                " --name movo-test-mongo -p 27017:27017 mongo:6.0.20"
            )
        name = f"{DB_NAME_PREFIX}{uuid.uuid4().hex}"
        loop = asyncio.new_event_loop()
        client = AsyncIOMotorClient(
            uri,
            io_loop=loop,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=2000,
        )
        db = client[name]
        try:
            yield RealMongoHarness(db=db, loop=loop, name=name, uri=uri)
        finally:
            # AsyncIOMotorClient.close() is a synchronous delegate in motor 2.5.1.
            client.close()
            loop.close()
            admin.drop_database(name)
    finally:
        admin.close()
