from pathlib import Path
import os
import time

from app.skill_build_records import MAX_LOG_CHARS, SkillBuildRecords
from app.docker_engine import merged_docker_logs


def test_records_keep_retry_history_and_survive_reopen(tmp_path: Path):
    digest = "a" * 64
    store = SkillBuildRecords(tmp_path)
    first = store.create(digest, "sha256:base")
    store.append_attempt(digest, first, source="internal", exit_code=1, output="connection failed\n")
    store.finish(digest, first, "failed")
    second = store.create(digest, "sha256:base")
    store.append_attempt(digest, second, source="internal", exit_code=0, output="installed\n")
    store.finish(digest, second, "ready")

    reopened = SkillBuildRecords(tmp_path)
    assert [item["id"] for item in reopened.list(digest)] == [second, first]
    assert reopened.get(digest, first)["log"].endswith("connection failed\n")
    assert reopened.get(digest, second)["status"] == "ready"


def test_logs_are_bounded_and_common_credentials_are_redacted(tmp_path: Path):
    digest = "b" * 64
    store = SkillBuildRecords(tmp_path)
    record_id = store.create(digest, "sha256:base")
    store.append_attempt(
        digest, record_id, source="internal", exit_code=1,
        output="Authorization: Bearer private123\nhttps://user:pass@registry.internal\n",
    )
    record = store.get(digest, record_id)
    assert "private123" not in record["log"]
    assert "user:pass" not in record["log"]
    store.append_attempt(digest, record_id, source="retry", exit_code=1, output="x" * (MAX_LOG_CHARS + 100))
    record = store.get(digest, record_id)
    assert record["truncated"] is True
    assert len(record["log"]) == MAX_LOG_CHARS


def test_interrupted_record_is_closed_on_restart(tmp_path: Path):
    digest = "c" * 64
    store = SkillBuildRecords(tmp_path)
    record_id = store.create(digest, "sha256:base")
    SkillBuildRecords(tmp_path).recover_interrupted()
    assert store.get(digest, record_id)["status"] == "interrupted"


def test_expired_records_are_pruned_on_restart(tmp_path: Path):
    digest = "e" * 64
    store = SkillBuildRecords(tmp_path)
    record_id = store.create(digest, "sha256:base")
    path = store._path(digest, record_id)
    old = time.time() - 31 * 24 * 60 * 60
    os.utime(path, (old, old))
    store.recover_interrupted()
    assert store.get(digest, record_id) is None


def test_docker_output_keeps_stdout_and_stderr_order():
    def frame(stream: int, payload: bytes) -> bytes:
        return bytes([stream, 0, 0, 0]) + len(payload).to_bytes(4, "big") + payload

    assert merged_docker_logs(frame(1, b"first\n") + frame(2, b"second\n")) == b"first\nsecond\n"
