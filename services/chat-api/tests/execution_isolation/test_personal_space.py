from __future__ import annotations

from pathlib import Path
import pytest

from app.execution_isolation.personal_space import bind_script_task, personal_space_key
from app.execution_isolation.script_backend import task_workspace
from app.enterprise_capabilities.data.script_engine.personal_outputs import save_outputs


def test_personal_files_survive_task_cleanup_and_isolate_users(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_URL", "http://sandbox-manager")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    key = personal_space_key("tenant", "alice")
    conversation_key = bind_script_task("message-one", "tenant", "alice", "chat")
    assert (task_workspace("message-one") / "personal-space-key").read_text() == key
    work = tmp_path / "personal" / key / "work"
    assert (work / "tmp").is_dir()
    (work / "intermediate.csv").write_text("saved across turns")
    output = tmp_path / "output"
    output.mkdir()
    (output / "report.txt").write_text("saved")
    conversation = tmp_path / "personal" / key / "conversations" / conversation_key
    save_outputs(output, conversation, "call-one")
    assert (conversation / "outputs" / "call-one" / "report.txt").read_text() == "saved"
    assert bind_script_task("message-two", "tenant", "alice", "chat") == conversation_key
    assert (work / "intermediate.csv").read_text() == "saved across turns"
    assert personal_space_key("tenant", "bob") != key


def test_output_copy_respects_personal_capacity_without_deleting_existing_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_PERSONAL_SPACE_MAX_BYTES", "5")
    conversation = tmp_path / "personal" / "alice" / "conversations" / "chat"
    conversation.mkdir(parents=True)
    (conversation / "existing.txt").write_bytes(b"1234")
    output = tmp_path / "output"
    output.mkdir()
    (output / "report.txt").write_bytes(b"12")
    with pytest.raises(ValueError, match="storage limit"):
        save_outputs(output, conversation, "call")
    assert (conversation / "existing.txt").read_bytes() == b"1234"
    assert not (conversation / "outputs").exists()
