"""Persistent administrator settings for the sandbox manager."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4


class SettingsStore:
    def __init__(self, root: Path, *, legacy_root: Path | None = None) -> None:
        self.path = root / "sandbox-settings.json"
        self.legacy_path = legacy_root / "sandbox-settings.json" if legacy_root else None

    def _read(self) -> dict:
        source = self.path if self.path.exists() else self.legacy_path
        return json.loads(source.read_text(encoding="utf-8")) if source and source.exists() else {}

    def _value(self, name: str, default: int, minimum: int) -> int:
        value = self._read().get(name, default)
        if type(value) is not int or not minimum <= value <= 100:
            raise ValueError(f"Invalid sandbox {name} setting")
        return value

    def capacity(self, default: int) -> int:
        return self._value("capacity", default, 1)

    def max_pending(self, default: int) -> int:
        return self._value("max_pending", default, 0)

    def runtime_policy(self) -> dict:
        values = self._read()
        placement = values.get("runtime_mode", "on_demand")
        idle = values.get("plugin_idle_seconds", int(os.environ.get("MOVO_SANDBOX_PLUGIN_IDLE_SECONDS", "900")))
        if placement not in ("on_demand", "forced") or type(idle) is not int or not 0 <= idle <= 604800:
            raise ValueError("Invalid sandbox runtime settings")
        return {"runtime_mode": placement, "plugin_idle_seconds": idle}

    def save_max_pending(self, value: int) -> None:
        self.save({**self._read(), "max_pending": value})

    def save(self, values: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                os.chmod(temporary, 0o600)
                json.dump(values, stream)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
