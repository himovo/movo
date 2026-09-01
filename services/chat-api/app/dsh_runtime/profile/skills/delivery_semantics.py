"""Infer which workflow artifacts are handoff-only rather than user delivery."""

from __future__ import annotations

from typing import Any


def intermediate_artifact_nodes(nodes: list[dict[str, Any]]) -> set[int]:
    """Return indexes of artifact nodes consumed by a later final export.

    ASKAI workflows are advisory to the DSH loop, but their declared delivery
    chain still owns artifact visibility. A spreadsheet or governed-script file
    prepared before a final export is a handoff object, while its standalone
    counterpart remains final.
    """
    final_export_indexes = {
        index for index, node in enumerate(nodes)
        if str(node.get("type") or "").strip() == "export_delivery"
    }
    if not final_export_indexes:
        return set()
    return {
        index for index, node in enumerate(nodes)
        if str(node.get("type") or "").strip() in {"fill_table", "script_plugin"}
        and any(export_index > index for export_index in final_export_indexes)
    }
