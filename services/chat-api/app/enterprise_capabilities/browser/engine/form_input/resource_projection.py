"""Project typed resource artifacts into browser form inputs.

Resource collection nodes intentionally retain research evidence, raw tool
results, and several aliases of the same downloaded file. Those values are
useful to downstream reasoning, but only the canonical images/attachments are
valid browser form inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple


_RESOURCE_ENVELOPE_KEYS = {
    "answer",
    "attachments",
    "business_payload",
    "business_schema",
    "collected_pages",
    "decoded_data",
    "decoded_payload",
    "downloaded_files",
    "failures",
    "images",
    "research_bundle",
    "resource_bundle",
    "resource_counts",
    "resources",
    "results",
    "source_material",
    "tool_results",
    "tools_used",
    "urls",
}


@dataclass(frozen=True)
class ResourceInputBatch:
    semantic_name: str
    source_path: str
    values: Tuple[Any, ...]


@dataclass(frozen=True)
class ResourceArtifactProjection:
    batches: Tuple[ResourceInputBatch, ...]
    remainder: Dict[str, Any]


@dataclass(frozen=True)
class _LocatedResourceBundle:
    payload: Mapping[str, Any]
    payload_path: str
    bundle: Mapping[str, Any]
    bundle_key: str


def project_resource_artifact(
    artifact: Mapping[str, Any],
    *,
    source_path: str,
) -> Optional[ResourceArtifactProjection]:
    """Use the canonical resource envelope instead of recursively flattening it."""

    located = _locate_resource_bundle(artifact)
    if located is None:
        return None

    payload_path = _join_path(source_path, located.payload_path)
    batches = []
    for semantic_name in ("images", "attachments"):
        values, values_path, projected_name = _resource_values(
            located.payload,
            located.bundle,
            semantic_name=semantic_name,
            bundle_path=_join_path(payload_path, located.bundle_key),
            artifact_path=payload_path,
        )
        if values:
            batches.append(ResourceInputBatch(
                semantic_name=projected_name,
                source_path=values_path,
                values=values,
            ))

    remainder = {
        str(key): value
        for key, value in artifact.items()
        if str(key) not in _RESOURCE_ENVELOPE_KEYS
        and not str(key).startswith("_")
    }
    return ResourceArtifactProjection(
        batches=tuple(batches),
        remainder=remainder,
    )


def _resource_values(
    artifact: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    semantic_name: str,
    bundle_path: str,
    artifact_path: str,
) -> tuple[Tuple[Any, ...], str, str]:
    canonical = _located_values(bundle.get(semantic_name))
    if canonical:
        return canonical, f"{bundle_path}.{semantic_name}", semantic_name

    aliases = (
        ("images",)
        if semantic_name == "images"
        else ("attachments", "downloaded_files")
    )
    for alias in aliases:
        fallback = _located_values(artifact.get(alias))
        if fallback:
            return fallback, f"{artifact_path}.{alias}", alias
    return (), "", semantic_name


def _located_values(value: Any) -> Tuple[Any, ...]:
    return tuple(
        item
        for item in list(value or [])
        if _has_resource_location(item)
    )


def _locate_resource_bundle(
    artifact: Mapping[str, Any],
) -> Optional[_LocatedResourceBundle]:
    direct = _direct_resource_bundle(artifact)
    if direct is not None:
        bundle_key, bundle = direct
        return _LocatedResourceBundle(
            payload=artifact,
            payload_path="",
            bundle=bundle,
            bundle_key=bundle_key,
        )

    decoded = artifact.get("decoded_payload")
    if not isinstance(decoded, Mapping):
        return None

    decoded_direct = _direct_resource_bundle(decoded)
    if decoded_direct is not None:
        bundle_key, bundle = decoded_direct
        return _LocatedResourceBundle(
            payload=decoded,
            payload_path="decoded_payload",
            bundle=bundle,
            bundle_key=bundle_key,
        )

    # ToolGateway receipts created by the research executor historically
    # stored the raw tool payload under {"ok": true, "result": ...}. On
    # idempotent reuse that receipt becomes decoded_payload. Recognize only
    # this explicit resource-bearing envelope; do not recursively unwrap
    # arbitrary tool or business payloads.
    nested = decoded.get("result")
    if decoded.get("ok") is not True or not isinstance(nested, Mapping):
        return None
    nested_direct = _direct_resource_bundle(nested)
    if nested_direct is None:
        return None
    bundle_key, bundle = nested_direct
    return _LocatedResourceBundle(
        payload=nested,
        payload_path="decoded_payload.result",
        bundle=bundle,
        bundle_key=bundle_key,
    )


def _direct_resource_bundle(
    payload: Mapping[str, Any],
) -> Optional[tuple[str, Mapping[str, Any]]]:
    for key in ("resource_bundle", "resources"):
        value = payload.get(key)
        if not isinstance(value, Mapping):
            continue
        if any(name in value for name in (
            "requested_types", "images", "attachments", "urls", "resource_counts",
        )):
            return key, value
    return None


def _join_path(root: str, suffix: str) -> str:
    return f"{root}.{suffix}" if suffix else root


def _has_resource_location(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if not isinstance(value, Mapping):
        return False
    return any(
        str(value.get(key) or "").strip()
        for key in (
            "local_path",
            "path_or_url",
            "signed_url",
            "url",
            "path",
            "source_url",
            "object_path",
        )
    )


__all__ = [
    "ResourceArtifactProjection",
    "ResourceInputBatch",
    "project_resource_artifact",
]
