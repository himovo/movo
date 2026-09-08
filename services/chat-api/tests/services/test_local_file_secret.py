from __future__ import annotations

from app.services.local_file_secret import resolve_local_file_signing_secret


def test_configured_secret_takes_precedence(tmp_path) -> None:
    assert resolve_local_file_signing_secret(
        configured_secret="operator-provided-secret",
        storage_root=tmp_path,
    ) == "operator-provided-secret"
    assert not (tmp_path / ".movo" / "file-url-signing.key").exists()


def test_missing_secret_is_generated_and_persisted(tmp_path) -> None:
    first = resolve_local_file_signing_secret(configured_secret="", storage_root=tmp_path)
    second = resolve_local_file_signing_secret(configured_secret="", storage_root=tmp_path)

    assert len(first) == 64
    assert second == first
    assert (tmp_path / ".movo" / "file-url-signing.key").read_text(encoding="utf-8").strip() == first
