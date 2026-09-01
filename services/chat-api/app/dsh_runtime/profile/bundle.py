"""Offline Runtime Profile export and integrity-checked replay."""

from __future__ import annotations

import json

from .compiler import ModelProfileCompiler
from .models import RuntimeProfileSnapshot


class RuntimeProfileBundle:
    @staticmethod
    def export(snapshot: RuntimeProfileSnapshot) -> bytes:
        document = snapshot.model_dump(mode="json")
        return json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")

    @staticmethod
    def load(payload: bytes | str) -> RuntimeProfileSnapshot:
        snapshot = RuntimeProfileSnapshot.model_validate_json(payload)
        document = snapshot.model_dump(mode="json")
        claimed_hash = document.pop("content_hash")
        document.pop("profile_version")
        actual_hash = ModelProfileCompiler.content_hash(document)
        if actual_hash != claimed_hash or snapshot.profile_version != f"rp-{actual_hash[:24]}":
            raise ValueError("Runtime Profile bundle integrity check failed")
        return snapshot
