"""Identify package-manager bookkeeping that must not overwrite local state."""

from pathlib import PurePosixPath


def is_mutable_cache_index(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    if len(parts) == 3 and parts[0] == "pnpm" and parts[1].startswith("v"):
        return parts[2] == "index.db"
    if parts == ("pnpm-cache", "lockfile-verified.jsonl"):
        return True
    return (len(parts) >= 4 and parts[0] == "pnpm-cache" and
            parts[1].startswith("v") and parts[2] == "metadata" and
            parts[-1].endswith(".jsonl"))
