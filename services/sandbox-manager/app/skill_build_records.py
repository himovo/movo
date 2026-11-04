"""Bounded, persistent records for isolated Skill image preparation."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .storage_paths import manager_state_root


MAX_LOG_CHARS = 262_144
MAX_RECORDS = 20
MAX_AGE_SECONDS = 30 * 24 * 60 * 60
_SECRET = re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?|(?:password|passwd|token|api[_-]?key|secret)\s*[:=]\s*)[^\s,'\"]+")
_URL_CREDENTIALS = re.compile(r"(https?://)[^/@\s]+@")
_QUERY_SECRET = re.compile(r"(?i)([?&](?:token|access_token|api_key|signature|x-oss-signature)=)[^&\s]+")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_log(value: str) -> str:
    text = _ANSI.sub("", value).replace("\x00", "")
    text = _URL_CREDENTIALS.sub(r"\1<redacted>@", text)
    text = _QUERY_SECRET.sub(r"\1<redacted>", text)
    return _SECRET.sub(r"\1<redacted>", text)


class SkillBuildRecords:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or manager_state_root() / "skill-build-records"
        self.lock = threading.RLock()

    def _directory(self, digest: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid Skill digest")
        return self.root / digest

    def _path(self, digest: str, record_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", record_id):
            raise ValueError("Invalid preparation ID")
        return self._directory(digest) / f"{record_id}.json"

    def create(self, digest: str, base_image_id: str) -> str:
        record_id = uuid4().hex
        record = {
            "id": record_id, "digest": digest, "baseImageId": base_image_id,
            "status": "preparing", "startedAt": _timestamp(), "finishedAt": "",
            "attempts": [], "log": "", "truncated": False,
        }
        with self.lock:
            self._write(digest, record_id, record)
            self._prune(digest)
        return record_id

    def append_attempt(self, digest: str, record_id: str, *, source: str, exit_code: int, output: str) -> None:
        with self.lock:
            record = self.get(digest, record_id)
            if record is None:
                return
            heading = f"\n=== Attempt {len(record['attempts']) + 1}: {source} (exit {exit_code}) ===\n"
            chunk = _safe_log(heading + output)
            combined = record["log"] + chunk
            record["truncated"] = record["truncated"] or len(combined) > MAX_LOG_CHARS
            record["log"] = combined[-MAX_LOG_CHARS:]
            record["attempts"].append({"source": source, "exitCode": exit_code})
            self._write(digest, record_id, record)

    def finish(self, digest: str, record_id: str, status: str, note: str = "") -> None:
        with self.lock:
            record = self.get(digest, record_id)
            if record is None:
                return
            record["status"] = status
            record["finishedAt"] = _timestamp()
            if note:
                chunk = _safe_log(f"\n=== {note} ===\n")
                combined = record["log"] + chunk
                record["truncated"] = record["truncated"] or len(combined) > MAX_LOG_CHARS
                record["log"] = combined[-MAX_LOG_CHARS:]
            self._write(digest, record_id, record)

    def get(self, digest: str, record_id: str) -> dict | None:
        path = self._path(digest, record_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None

    def list(self, digest: str) -> list[dict]:
        directory = self._directory(digest)
        records = []
        for path in directory.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            records.append({key: value for key, value in record.items() if key != "log"})
        return sorted(records, key=lambda item: item["startedAt"], reverse=True)[:MAX_RECORDS]

    def _write(self, digest: str, record_id: str, record: dict) -> None:
        path = self._path(digest, record_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False)
        os.replace(temporary, path)

    def _prune(self, digest: str) -> None:
        paths = sorted(self._directory(digest).glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in paths[MAX_RECORDS:]:
            path.unlink(missing_ok=True)

    def recover_interrupted(self) -> None:
        cutoff = time.time() - MAX_AGE_SECONDS
        for path in self.root.glob("*/*.json"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    continue
                record = json.loads(path.read_text(encoding="utf-8"))
                if record.get("status") == "preparing":
                    record["status"] = "interrupted"
                    record["finishedAt"] = _timestamp()
                    temporary = path.with_suffix(".tmp")
                    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                        json.dump(record, stream, ensure_ascii=False)
                    os.replace(temporary, path)
            except (OSError, ValueError):
                continue
