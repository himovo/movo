"""Locate MOVO-owned DSH data across the main and isolated Runtime volumes."""

from __future__ import annotations

import hashlib
from pathlib import Path


class RuntimeStorageLocator:
    def __init__(self, primary_root: Path, workspace_root: Path | None = None) -> None:
        self.primary_root = primary_root
        self.workspace_root = workspace_root

    @staticmethod
    def _digest(isolation_key: str) -> str:
        return hashlib.sha256(isolation_key.encode()).hexdigest()

    def _candidates(self, isolation_key: str) -> tuple[Path, ...]:
        digest = self._digest(isolation_key)
        roots = [
            self.primary_root / digest,
            self.primary_root / "sandbox-runtimes" / digest / digest,
        ]
        if self.workspace_root is not None:
            roots.append(self.workspace_root / "plugin-runtimes" / digest / digest)
        return tuple(roots)

    def predecessor(self, isolation_key: str, session_id: str) -> tuple[Path, Path]:
        found = [
            (root, journal)
            for root in self._candidates(isolation_key)
            if root.is_dir()
            for journal in root.rglob(f"{session_id}/session.v4.jsonl")
        ]
        if len(found) != 1:
            raise FileNotFoundError(
                f"Expected one DSH predecessor journal for {session_id}; found {len(found)}"
            )
        return found[0]

    def successor(self, isolation_key: str) -> Path:
        digest = self._digest(isolation_key)
        if self.workspace_root is None:
            return self.primary_root / digest
        legacy = self.primary_root / "sandbox-runtimes" / digest
        if legacy.is_dir():
            return legacy / digest
        return self.workspace_root / "plugin-runtimes" / digest / digest
