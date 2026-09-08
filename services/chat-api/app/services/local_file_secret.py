from __future__ import annotations

import os
import secrets
from pathlib import Path


_SECRET_DIR = ".movo"
_SECRET_FILE = "file-url-signing.key"
_MIN_SECRET_LENGTH = 32


def resolve_local_file_signing_secret(
    *,
    configured_secret: str,
    storage_root: str | Path,
) -> str:
    """Return the configured secret or a stable secret owned by local storage.

    Local source installs should work without asking an operator to provision an
    authentication secret.  The generated value is persisted beside the local
    artifact store so every worker and every later restart uses the same key.
    """

    explicit = str(configured_secret or "").strip()
    if explicit:
        return explicit

    secret_path = Path(storage_root).expanduser() / _SECRET_DIR / _SECRET_FILE
    existing = _read_valid_secret(secret_path)
    if existing:
        return existing

    secret_path.parent.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_hex(32)
    try:
        descriptor = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        concurrent = _read_valid_secret(secret_path)
        if concurrent:
            return concurrent
        raise RuntimeError(f"Local file signing secret is invalid: {secret_path}")

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(generated + "\n")
    except Exception:
        secret_path.unlink(missing_ok=True)
        raise
    return generated


def _read_valid_secret(secret_path: Path) -> str:
    try:
        value = secret_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    if len(value) < _MIN_SECRET_LENGTH:
        return ""
    return value
