from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.dsh_runtime.personal_output_delivery import _candidates
from app.execution_isolation.personal_space import conversation_space_key, personal_space_key


def test_only_current_user_conversation_outputs_are_delivered(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    started = datetime.now(timezone.utc) - timedelta(minutes=1)
    binding = {
        "execution_location": "server", "tenant_id": "tenant", "user_id": "alice",
        "conversation_id": "chat", "active_turn": {"started_at": started},
    }
    conversation = (tmp_path / "personal" / personal_space_key("tenant", "alice") /
                    "conversations" / conversation_space_key("chat"))
    conversation.mkdir(parents=True)
    report = conversation / "report.docx"
    report.write_bytes(b"report")
    internal = conversation / "outputs" / "script-call" / "other.docx"
    internal.parent.mkdir(parents=True)
    internal.write_bytes(b"script result")
    uploaded = conversation / "inputs" / "message" / "0-upload.docx"
    uploaded.parent.mkdir(parents=True)
    uploaded.write_bytes(b"upload")
    other = (tmp_path / "personal" / personal_space_key("tenant", "bob") /
             "conversations" / conversation_space_key("chat") / "private.docx")
    other.parent.mkdir(parents=True)
    other.write_bytes(b"private")
    assert _candidates(binding) == [report]


def test_symlinked_conversation_cannot_publish_files_outside_personal_space(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    binding = {
        "execution_location": "server", "tenant_id": "tenant", "user_id": "alice",
        "conversation_id": "chat", "active_turn": {"started_at": datetime.now(timezone.utc)},
    }
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("private")
    personal = tmp_path / "personal" / personal_space_key("tenant", "alice") / "conversations"
    personal.mkdir(parents=True)
    (personal / conversation_space_key("chat")).symlink_to(outside, target_is_directory=True)
    assert _candidates(binding) == []
