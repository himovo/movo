from __future__ import annotations

import os

from pymongo import MongoClient
from pymongo.database import Database

from app.core.config import settings

_client: MongoClient | None = None
_db: Database | None = None


def init_db() -> None:
    global _client, _db
    if _db is not None:
        return
    if not settings.mongodb_uri:
        raise RuntimeError("MongoDB URI is not configured")
    server_selection_timeout_ms = int(os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "5000"))
    connect_timeout_ms = int(os.getenv("MONGODB_CONNECT_TIMEOUT_MS", "5000"))
    socket_timeout_ms = int(os.getenv("MONGODB_SOCKET_TIMEOUT_MS", "10000"))
    _client = MongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=server_selection_timeout_ms,
        connectTimeoutMS=connect_timeout_ms,
        socketTimeoutMS=socket_timeout_ms,
    )
    _db = _client[settings.mongodb_db]


def close_db() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


def get_db() -> Database:
    if _db is None:
        init_db()
    if _db is None:
        raise RuntimeError("MongoDB is not initialized")
    return _db
