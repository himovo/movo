"""Carry DSH attachment objects when MOVO changes a conversation's Runtime Profile.

DSH seeds session events but its local attachment store is scoped to the
Runtime isolation key. MOVO owns the profile change and copies only objects
referenced by the predecessor session before asking DSH to create its seed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from pathlib import Path

from .runtime_storage import RuntimeStorageLocator


_DIGEST = re.compile(r"^sha256:([a-f0-9]{64})$")


class SeedAttachmentTransfer:
    def __init__(self, storage_root: Path, workspace_root: Path | None = None) -> None:
        self.storage = RuntimeStorageLocator(storage_root, workspace_root)

    @staticmethod
    def _references(value: object):
        if isinstance(value, list):
            for item in value:
                yield from SeedAttachmentTransfer._references(item)
        elif isinstance(value, dict):
            ref = value.get("attachment")
            match = _DIGEST.fullmatch(ref.get("attachmentId", "")) if isinstance(ref, dict) else None
            if isinstance(value.get("type"), str) and value["type"] in {"image", "file"} and match:
                name = ref.get("name")
                if value["type"] == "image" or (
                    isinstance(name, str) and name not in {"", ".", ".."}
                    and not any(c in name for c in "/\\\x00\n\r")
                ):
                    yield value["type"], match.group(1), name
            for child in value.values():
                yield from SeedAttachmentTransfer._references(child)

    @staticmethod
    def _copy(source: Path, target: Path) -> None:
        if target.is_file():
            return
        if not source.is_file():
            raise FileNotFoundError(f"DSH seed attachment is missing: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def transfer(self, *, source_key: str, target_key: str, session_id: str) -> None:
        if source_key == target_key:
            return
        source_domain, journal_path = self.storage.predecessor(source_key, session_id)
        references: set[tuple[str, str, str | None]] = set()
        with journal_path.open(encoding="utf-8") as journal:
            for line in journal:
                references.update(self._references(json.loads(line)))
        source = source_domain / "dsh-home" / "attachments" / "v1"
        target = self.storage.successor(target_key) / "dsh-home" / "attachments" / "v1"
        for kind, digest, name in references:
            directory = "file-objects" if kind == "file" else "objects"
            relative = Path(directory) / digest[:2] / digest
            self._copy(source / relative, target / relative)
            if kind == "file":
                alias = Path("files") / digest[:2] / digest / name
                self._copy(source / alias, target / alias)
