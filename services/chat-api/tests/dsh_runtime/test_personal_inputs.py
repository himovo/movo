from __future__ import annotations

from pathlib import Path
import pytest

from app.dsh_runtime import personal_inputs
from app.execution_isolation.personal_space import conversation_space_key, personal_space_key


class FakeUploader:
    def read_bytes(self, object_path: str) -> bytes:
        assert object_path == "alice/report.docx"
        return b"document"


def test_staged_document_is_available_in_personal_conversation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(personal_inputs, "AliyunOSSUploader", FakeUploader)
    binding = {"tenant_id": "tenant", "user_id": "alice", "conversation_id": "chat"}
    result = personal_inputs._stage(binding, "message", [{
        "object_path": "alice/report.docx", "filename": "report.docx",
    }])
    local = result[0]["local_path"]
    assert local.startswith(f"/job/home/conversations/{conversation_space_key('chat')}/inputs/")
    path = tmp_path / "personal" / personal_space_key("tenant", "alice") / local.removeprefix("/job/home/")
    assert path.read_bytes() == b"document"


def test_staging_rejects_a_symlinked_input_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(personal_inputs, "AliyunOSSUploader", FakeUploader)
    binding = {"tenant_id": "tenant", "user_id": "alice", "conversation_id": "chat"}
    personal = tmp_path / "personal" / personal_space_key("tenant", "alice")
    conversation = personal / "conversations" / conversation_space_key("chat")
    conversation.mkdir(parents=True)
    (conversation / "inputs").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(PermissionError, match="escapes"):
        personal_inputs._stage(binding, "message", [{
            "object_path": "alice/report.docx", "filename": "report.docx",
        }])
