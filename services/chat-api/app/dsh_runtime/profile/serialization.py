"""Preserve immutable profile wire shapes across optional schema additions."""

from __future__ import annotations

from .models import RuntimeProfileSnapshot


def snapshot_document(snapshot: RuntimeProfileSnapshot) -> dict:
    document = snapshot.model_dump(
        mode="json", exclude={"plugins", "plugin_versions"} if not snapshot.plugins else None,
    )
    if not snapshot.agent_name:
        from .compiler import ModelProfileCompiler

        candidate = {key: value for key, value in document.items() if key not in {"agent_name", "content_hash", "profile_version"}}
        if ModelProfileCompiler.content_hash(candidate) == snapshot.content_hash:
            document.pop("agent_name", None)
    return document
