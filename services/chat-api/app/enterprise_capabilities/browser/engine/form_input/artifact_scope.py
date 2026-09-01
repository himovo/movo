from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Set


def browser_publish_ancestor_artifacts(
    *,
    node: Any,
    output_spec: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Return publish payloads from the current browser node's ancestor chain."""
    if _capability_id(node, output_spec) != "browser.publish":
        return {}

    current_id = str(
        getattr(node, "node_id", "")
        or output_spec.get("current_task_node_id")
        or ""
    ).strip()
    if not current_id:
        return {}

    topology = list(output_spec.get("graph_topology") or [])
    dependencies = {
        str(item.get("node_id") or "").strip(): _string_list(item.get("depends_on"))
        for item in topology
        if isinstance(item, dict) and str(item.get("node_id") or "").strip()
    }
    ancestor_ids = _upstream_closure(current_id, dependencies)
    if not ancestor_ids:
        return {}

    graph_artifacts = (
        output_spec.get("graph_artifacts")
        if isinstance(output_spec.get("graph_artifacts"), dict)
        else {}
    )
    return {
        source_id: artifact
        for source_id, artifact in graph_artifacts.items()
        if source_id in ancestor_ids
        and isinstance(artifact, dict)
        and _has_publish_payload(artifact)
    }


def _capability_id(node: Any, output_spec: Mapping[str, Any]) -> str:
    node_meta = getattr(node, "meta", None)
    if isinstance(node_meta, dict):
        capability = str(node_meta.get("capability_id") or "").strip().lower()
        if capability:
            return capability
    current_meta = output_spec.get("current_task_node_meta")
    if isinstance(current_meta, dict):
        return str(current_meta.get("capability_id") or "").strip().lower()
    return ""


def _upstream_closure(
    current_id: str,
    dependencies: Mapping[str, Iterable[str]],
) -> Set[str]:
    seen: Set[str] = set()
    stack = list(dependencies.get(current_id) or [])
    while stack:
        dependency_id = str(stack.pop() or "").strip()
        if not dependency_id or dependency_id in seen:
            continue
        seen.add(dependency_id)
        stack.extend(dependencies.get(dependency_id) or [])
    return seen


def _has_publish_payload(artifact: Mapping[str, Any]) -> bool:
    payload = artifact.get("publish_payload")
    return (
        isinstance(payload, dict)
        and str(payload.get("schema_version") or "").strip() == "1.0"
        and any(
            str(payload.get(key) or "").strip()
            for key in ("title", "body_markdown", "body_plain_text", "body_html")
        )
    )


def _string_list(value: Any) -> list[str]:
    return [
        str(item or "").strip()
        for item in list(value or [])
        if str(item or "").strip()
    ]


__all__ = ["browser_publish_ancestor_artifacts"]
