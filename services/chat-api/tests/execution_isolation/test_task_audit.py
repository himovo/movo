from __future__ import annotations

import json
import io
import zipfile
import asyncio
import pytest
from pathlib import Path

from app.execution_isolation import task_audit
from app.execution_isolation.task_audit import _archive
from app.execution_isolation.call_audit import record_call


def test_archive_contains_intermediate_files_logs_and_failed_calls(tmp_path: Path) -> None:
    call = tmp_path / "audit" / ("a" * 32)
    call.mkdir(parents=True)
    (call / "audit.json").write_text(json.dumps({"status": "failed", "duration_ms": 12}))
    (call / "stderr.log").write_text("traceback")
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "intermediate.log").write_text("processing")
    archive, files, calls = _archive(tmp_path)
    assert calls == [{"call_id": "a" * 32, "status": "failed", "duration_ms": 12}]
    assert any(row["path"] == "work/intermediate.log" for row in files)
    with zipfile.ZipFile(io.BytesIO(archive)) as saved:
        assert saved.read("audit/" + "a" * 32 + "/stderr.log") == b"traceback"


def test_each_call_keeps_its_own_intermediate_snapshot(tmp_path: Path) -> None:
    work = tmp_path / "work"
    first = work / "calls" / ("a" * 32)
    second = work / "calls" / ("b" * 32)
    first.mkdir(parents=True)
    intermediate = work / "intermediate.log"
    intermediate.write_text("first")
    record_call(first, action_id="first", skill_digest="", duration_ms=1,
                status="succeeded", started_ns=0)
    second.mkdir()
    intermediate.write_text("second")
    record_call(second, action_id="second", skill_digest="", duration_ms=1,
                status="succeeded", started_ns=0)
    assert (tmp_path / "audit" / ("a" * 32) / "files" / "intermediate.log").read_text() == "first"
    assert (tmp_path / "audit" / ("b" * 32) / "files" / "intermediate.log").read_text() == "second"


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
def test_finalization_archives_before_releasing_container(tmp_path: Path, monkeypatch, status: str) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_URL", "http://manager")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    message_id = "message-1"
    workspace = task_audit.task_workspace(message_id)
    (workspace / "work").mkdir(parents=True)
    (workspace / "work" / "result.txt").write_text("result")
    order = []

    class Storage:
        def upload_bytes_with_path(self, content, user_id, file_name, content_type):
            order.append("uploaded")
            with zipfile.ZipFile(io.BytesIO(content)) as saved:
                assert saved.read("work/result.txt") == b"result"
            return "signed", "audit/path.zip"

    class Collection:
        async def find_one(self, query, projection):
            return None

        async def update_one(self, query, update, upsert=False):
            if "object_path" in update["$set"]:
                order.append("indexed")
                assert update["$set"]["object_path"] == "audit/path.zip"

    class Database:
        sandbox_task_audits = Collection()

    def manager_action(task_id, *, freeze):
        order.append("frozen" if freeze else "released")

    monkeypatch.setattr(task_audit, "AliyunOSSUploader", Storage)
    monkeypatch.setattr(task_audit, "get_db", Database)
    monkeypatch.setattr(task_audit, "_manager_action", manager_action)
    async def run() -> None:
        assert await task_audit.finalize_task_audit(
            message_id=message_id, tenant_id="tenant", user_id="user",
            conversation_id="conversation", status=status,
        )
        assert order == ["frozen", "uploaded", "indexed"]
        assert await task_audit.cleanup_task_audit(message_id=message_id, audit_id="tenant:" + message_id)

    asyncio.run(run())
    assert order == ["frozen", "uploaded", "indexed", "released"]
    assert not workspace.exists()


def test_cleanup_failure_does_not_block_archived_turn(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_URL", "http://manager")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    workspace = task_audit.task_workspace("message")
    (workspace / "work").mkdir(parents=True)
    states = []

    class Storage:
        def upload_bytes_with_path(self, *args):
            return "signed", "audit/path.zip"

    class Collection:
        async def find_one(self, query, projection):
            return None

        async def update_one(self, query, update, upsert=False):
            states.append(update["$set"].get("cleanup_pending"))

    class Database:
        sandbox_task_audits = Collection()

    def manager_action(task_id, *, freeze):
        if not freeze:
            raise RuntimeError("Docker cleanup failed")

    monkeypatch.setattr(task_audit, "AliyunOSSUploader", Storage)
    monkeypatch.setattr(task_audit, "get_db", Database)
    monkeypatch.setattr(task_audit, "_manager_action", manager_action)
    async def run() -> None:
        assert await task_audit.finalize_task_audit(
            message_id="message", tenant_id="tenant", user_id="user",
            conversation_id="conversation", status="completed",
        )
        assert not await task_audit.cleanup_task_audit(message_id="message", audit_id="tenant:message")

    asyncio.run(run())
    assert states == [True]
    assert workspace.exists()


def test_archive_failure_keeps_workspace_for_retry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_URL", "http://manager")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    workspace = task_audit.task_workspace("message")
    (workspace / "work").mkdir(parents=True)
    (workspace / "work" / "result.txt").write_text("keep")
    actions = []

    class Storage:
        def upload_bytes_with_path(self, *args):
            raise RuntimeError("storage unavailable")

    class Collection:
        async def find_one(self, query, projection):
            return None

    class Database:
        sandbox_task_audits = Collection()

    monkeypatch.setattr(task_audit, "AliyunOSSUploader", Storage)
    monkeypatch.setattr(task_audit, "get_db", Database)
    monkeypatch.setattr(task_audit, "_manager_action", lambda task_id, *, freeze: actions.append(freeze))
    with pytest.raises(RuntimeError, match="storage unavailable"):
        asyncio.run(task_audit.finalize_task_audit(
            message_id="message", tenant_id="tenant", user_id="user",
            conversation_id="conversation", status="failed",
        ))
    assert actions == [True]
    assert (workspace / "work" / "result.txt").read_text() == "keep"
