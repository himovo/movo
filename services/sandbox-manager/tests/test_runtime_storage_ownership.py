from pathlib import Path
import os

import pytest

from app import runtime_storage_ownership
from app.runtime_storage_ownership import repair_runtime_storage


def test_repair_rejects_symlink_in_attachment_tree(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runtime_storage_ownership, "RUNTIME_UID", os.getuid())
    monkeypatch.setattr(runtime_storage_ownership, "RUNTIME_GID", os.getgid())
    domain = tmp_path / "domain"
    attachments = domain / "dsh-home" / "attachments"
    attachments.mkdir(parents=True)
    (attachments / "redirect").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        repair_runtime_storage(domain)


def test_repair_accepts_missing_runtime(tmp_path: Path) -> None:
    repair_runtime_storage(tmp_path / "missing")
    assert not (tmp_path / "missing").exists()
