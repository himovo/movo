import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from app.dsh_runtime.profile.attachment_transfer import SeedAttachmentTransfer
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator


def _domain(root: Path, key: str) -> Path:
    return root / hashlib.sha256(key.encode()).hexdigest()


def _object(root: Path, key: str, digest: str) -> Path:
    return _domain(root, key) / "dsh-home/attachments/v1/objects" / digest[:2] / digest


def test_image_survives_two_profile_rotations(tmp_path: Path):
    source, middle, final = "tenant:t:profile:a", "tenant:t:profile:b", "tenant:t:profile:c"
    data = b"historical image"
    digest = hashlib.sha256(data).hexdigest()
    origin = _object(tmp_path, source, digest)
    origin.parent.mkdir(parents=True)
    origin.write_bytes(data)
    event = {"type": "user/message", "data": {"content": [
        {"type": "image", "attachment": {"attachmentId": f"sha256:{digest}"}},
    ]}}
    for key, session_id in [(source, "original"), (middle, "successor")]:
        journal = _domain(tmp_path, key) / "_no-cwd" / session_id / "session.v4.jsonl"
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text(json.dumps(event) + "\n", encoding="utf-8")
    transfer = SeedAttachmentTransfer(tmp_path)
    transfer.transfer(source_key=source, target_key=middle, session_id="original")
    transfer.transfer(source_key=middle, target_key=final, session_id="successor")
    assert _object(tmp_path, final, digest).read_bytes() == data


def test_missing_object_blocks_successor_creation(tmp_path: Path):
    source, target = "tenant:t:profile:a", "tenant:t:profile:b"
    digest = "a" * 64
    journal = _domain(tmp_path, source) / "_no-cwd" / "original" / "session.v4.jsonl"
    journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({"data": {"content": [
        {"type": "image", "attachment": {"attachmentId": f"sha256:{digest}"}},
    ]}}) + "\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="seed attachment is missing"):
        SeedAttachmentTransfer(tmp_path).transfer(source_key=source, target_key=target, session_id="original")


def test_isolated_runtime_journal_and_attachment_are_migrated(tmp_path: Path):
    primary, workspaces = tmp_path / "runtime", tmp_path / "workspaces"
    source, target = "tenant:t:profile:isolated-a", "tenant:t:profile:isolated-b"
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    target_hash = hashlib.sha256(target.encode()).hexdigest()
    source_domain = workspaces / "plugin-runtimes" / source_hash / source_hash
    target_domain = workspaces / "plugin-runtimes" / target_hash / target_hash
    payload = b"isolated image"
    digest = hashlib.sha256(payload).hexdigest()
    attachment = source_domain / "dsh-home/attachments/v1/objects" / digest[:2] / digest
    attachment.parent.mkdir(parents=True)
    attachment.write_bytes(payload)
    journal = source_domain / "_no-cwd/original/session.v4.jsonl"
    journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({"data": {"content": [
        {"type": "image", "attachment": {"attachmentId": f"sha256:{digest}"}},
    ]}}) + "\n")

    SeedAttachmentTransfer(primary, workspaces).transfer(
        source_key=source, target_key=target, session_id="original",
    )
    copied = target_domain / "dsh-home/attachments/v1/objects" / digest[:2] / digest
    assert copied.read_bytes() == payload


def test_legacy_isolated_runtime_uses_runtime_volume(tmp_path: Path):
    primary, workspaces = tmp_path / "runtime", tmp_path / "workspaces"
    source, target = "tenant:t:profile:legacy-a", "tenant:t:profile:legacy-b"
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    target_hash = hashlib.sha256(target.encode()).hexdigest()
    source_domain = primary / "sandbox-runtimes" / source_hash / source_hash
    target_domain = primary / "sandbox-runtimes" / target_hash / target_hash
    target_domain.mkdir(parents=True)
    journal = source_domain / "_no-cwd/original/session.v4.jsonl"
    journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({"data": {"content": []}}) + "\n")
    SeedAttachmentTransfer(primary, workspaces).transfer(
        source_key=source, target_key=target, session_id="original",
    )
    assert not (workspaces / "plugin-runtimes" / target_hash).exists()


def test_business_conversation_stays_the_same_while_internal_session_rotates(tmp_path: Path):
    source = "tenant:t:profile:old"
    digest = hashlib.sha256(b"image").hexdigest()
    image = _object(tmp_path, source, digest)
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    journal = _domain(tmp_path, source) / "_no-cwd" / "session-old" / "session.v4.jsonl"
    journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({"data": {"content": [
        {"type": "image", "attachment": {"attachmentId": f"sha256:{digest}"}},
    ]}}) + "\n")

    class RecordingCoordinator(RuntimeCoordinator):
        async def _replace_binding(self, binding, *, profile_version, model_instance_id, seed):
            assert _object(tmp_path, "tenant:t:profile:new", digest).read_bytes() == b"image"
            assert seed is True
            return {**binding, "kernel_session_id": "session-new", "profile_version": profile_version}

    coordinator = RecordingCoordinator(None, None, SeedAttachmentTransfer(tmp_path))
    result = asyncio.run(coordinator.rotate_binding({
        "tenant_id": "t", "conversation_id": "business-conversation",
        "kernel_session_id": "session-old", "profile_version": "old",
    }, profile_version="new", model_instance_id="model"))
    assert result["conversation_id"] == "business-conversation"
    assert result["kernel_session_id"] == "session-new"
