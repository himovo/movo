from __future__ import annotations

from typing import Any, Dict, List

from .common import (
    decode_mapping,
    fingerprint,
    jsonable,
    looks_like_serialized_structure,
    record_meta,
    record_tool,
    text,
)


METRIC_KEYS = ("computed_metrics", "metric_table", "per_item_metrics")
DATA_KEYS = (
    "structured_payload",
    "business_data",
    "business_payload",
    "data",
    "analysis_result",
    "map_results",
    "reduce_result",
    "inspection_details",
)


def _payload(record: Dict[str, Any], source_type: str) -> Dict[str, Any]:
    raw_result = record.get("result")
    if isinstance(raw_result, list) and raw_result:
        return {"result": jsonable(raw_result)}
    nested = decode_mapping(record.get("result"))
    if source_type == "mcp" and "raw" in nested and nested.get("raw") not in (None, "", [], {}):
        return {"mcp_raw": jsonable(nested.get("raw"))}
    for container in (record, nested):
        for key in DATA_KEYS:
            if key in container and container.get(key) not in (None, "", [], {}):
                value = jsonable(container.get(key))
                if key == "structured_payload" and isinstance(value, dict):
                    return value
                return {key: value}
    if nested.get("raw") not in (None, "", [], {}):
        return {"raw": jsonable(nested.get("raw"))}
    if nested:
        excluded = {"ok", "message", "durationMs", "results", "raw"}
        material = {key: jsonable(value) for key, value in nested.items() if key not in excluded and value not in (None, "", [], {})}
        if material:
            return material
    return {}


def _failure(record: Dict[str, Any], source_type: str) -> Dict[str, Any]:
    nested = decode_mapping(record.get("result"))
    failed = record.get("ok") is False or nested.get("ok") is False or bool(record.get("error"))
    if not failed:
        return {}
    return {
        "source_type": source_type,
        "tool": record_tool(record),
        "error": text(record.get("error") or nested.get("message") or nested.get("error") or "tool returned ok=false"),
    }


def build_tool_material(record: Dict[str, Any], source_type: str) -> Dict[str, Any]:
    failure = _failure(record, source_type)
    if failure:
        return {"failure": failure}

    meta = record_meta(record)
    structured = _payload(record, source_type)
    title = text(record.get("title") or record.get("name") or record_tool(record) or source_type)
    summary = text(record.get("summary") or record.get("content") or record.get("snippet"))
    nested = decode_mapping(record.get("result"))
    if not summary and isinstance(nested.get("results"), list) and nested.get("results"):
        first = nested["results"][0] if isinstance(nested["results"][0], dict) else {}
        summary = text(first.get("summary") or first.get("content"))
        title = text(first.get("title")) or title
    if not summary and isinstance(record.get("result"), str):
        summary = text(record.get("result"))

    summary_is_structured = bool(structured) and looks_like_serialized_structure(summary)
    if summary_is_structured:
        summary = ""

    metrics: List[Dict[str, Any]] = []
    datasets: List[Dict[str, Any]] = []
    if structured:
        metric_payload = {key: value for key, value in structured.items() if key in METRIC_KEYS}
        other_payload = {key: value for key, value in structured.items() if key not in METRIC_KEYS}
        provenance = {
            "source_type": source_type,
            "tool": record_tool(record),
            "provider_type": text(meta.get("providerType")),
            "mcp_tool_name": text(meta.get("mcpToolName")),
        }
        if metric_payload:
            metrics.append({"title": title, "metrics": metric_payload, "provenance": provenance})
        if other_payload:
            datasets.append({"title": title, "data": other_payload, "provenance": provenance})

    evidence_item = {}
    # A structured payload is already represented once in a typed dataset or
    # metric. Do not add a second empty/JSON-preview evidence item merely for
    # provenance. Plain-language summaries remain useful alongside data.
    if summary:
        evidence_item = {
            "source_type": source_type,
            "title": title,
            "summary": summary,
            "structured_data_ref": fingerprint(structured) if structured else "",
            "source": text(record.get("source") or record.get("source_url")),
            "provenance": {
                "tool": record_tool(record),
                "provider_type": text(meta.get("providerType")),
                "mcp_tool_name": text(meta.get("mcpToolName")),
            },
        }
    source_excerpt = {}
    if source_type == "document" and summary:
        source_excerpt = {
            "source_type": "document",
            "title": title,
            "content": summary,
            "source_url": text(record.get("source_url") or record.get("url")),
            "source": text(record.get("source")),
        }
    return {
        "datasets": datasets,
        "metrics": metrics,
        "evidence_item": evidence_item,
        "source_excerpt": source_excerpt,
        "suppressed_structured_summary": summary_is_structured,
    }
