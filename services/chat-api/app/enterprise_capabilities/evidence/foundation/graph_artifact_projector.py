from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple


SUMMARY_KEYS = (
    "filter_summary",
    "map_summary",
    "extraction_summary",
    "branch_decision",
    "calculation_notes",
    "uncomputed_metrics",
)

METRIC_KEYS = (
    "computed_metrics",
    "metric_table",
    "per_item_metrics",
    "selected_records",
    "filtered_records",
)

ANALYSIS_KEYS = (
    "analysis_result",
    "map_results",
    "reduce_result",
    "inspection_details",
    "plugin_result",
)

RESEARCH_KEYS = ("research_bundle", "source_material", "tool_results")


def _is_present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _json_dumps(value: Any, *, limit: int) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str, indent=2)
    except Exception:
        text = str(value or "")
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...<truncated>"


def _compact_text(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...<truncated>"


def _project_value(value: Any, *, depth: int = 0) -> Any:
    if value in (None, "", [], {}):
        return value
    if isinstance(value, str):
        return _compact_text(value, limit=1200 if depth <= 1 else 600)
    if isinstance(value, (int, float, bool)):
        return value
    if depth >= 4:
        return _compact_text(value, limit=800)
    if isinstance(value, list):
        limit = 12 if depth <= 1 else 8
        projected = [_project_value(item, depth=depth + 1) for item in value[:limit]]
        if len(value) > limit:
            projected.append({"_omitted_items": len(value) - limit})
        return projected
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 24:
                out["_omitted_keys"] = len(value) - 24
                break
            if item in (None, "", [], {}):
                continue
            out[str(key)] = _project_value(item, depth=depth + 1)
        return out
    return _compact_text(value, limit=800)


def _business_payload_data(value: Any) -> Optional[Any]:
    if isinstance(value, dict) and _is_present(value.get("data")):
        return value.get("data")
    return None


def _project_research_value(value: Any) -> Any:
    if isinstance(value, dict):
        projected: Dict[str, Any] = {}
        for key in ("query", "topic", "tools_used", "confirmed_facts", "open_questions", "evidence_count"):
            if _is_present(value.get(key)):
                projected[key] = _project_value(value.get(key))
        results = value.get("results")
        if isinstance(results, list) and results:
            projected["results"] = _project_value(results[:8])
        return projected
    if isinstance(value, list):
        return _project_value(value[:8])
    return _project_value(value)


def _first_present_key(artifact: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        if key in artifact and _is_present(artifact.get(key)):
            return key
    return None


def _select_primary_payload(artifact: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    payload: Dict[str, Any] = {}
    selected_keys: List[str] = []

    if _is_present(artifact.get("browser_result")):
        payload["browser_result"] = _project_value(artifact.get("browser_result"))
        selected_keys.append("browser_result")
        return payload, selected_keys

    metric_payload = {
        key: _project_value(artifact.get(key))
        for key in METRIC_KEYS
        if key in artifact and _is_present(artifact.get(key))
    }
    if metric_payload:
        payload.update(metric_payload)
        selected_keys.extend(metric_payload.keys())
        return payload, selected_keys

    if _is_present(artifact.get("business_data")):
        payload["business_data"] = _project_value(artifact.get("business_data"))
        selected_keys.append("business_data")
        if _is_present(artifact.get("business_schema")):
            payload["business_schema"] = _project_value(artifact.get("business_schema"))
            selected_keys.append("business_schema")
        return payload, selected_keys

    business_payload_data = _business_payload_data(artifact.get("business_payload"))
    if _is_present(business_payload_data):
        payload["business_data"] = _project_value(business_payload_data)
        selected_keys.append("business_payload.data")
        if _is_present(artifact.get("business_schema")):
            payload["business_schema"] = _project_value(artifact.get("business_schema"))
            selected_keys.append("business_schema")
        return payload, selected_keys

    analysis_key = _first_present_key(artifact, ANALYSIS_KEYS)
    if analysis_key:
        payload[analysis_key] = _project_value(artifact.get(analysis_key))
        selected_keys.append(analysis_key)
        return payload, selected_keys

    research_key = _first_present_key(artifact, RESEARCH_KEYS)
    if research_key:
        payload[research_key] = _project_research_value(artifact.get(research_key))
        selected_keys.append(research_key)
        return payload, selected_keys

    decoded_data = _business_payload_data(artifact.get("decoded_payload"))
    if _is_present(decoded_data):
        payload["business_data"] = _project_value(decoded_data)
        selected_keys.append("decoded_payload.data")
        return payload, selected_keys

    if _is_present(artifact.get("decoded_payload")):
        payload["decoded_payload"] = _project_value(artifact.get("decoded_payload"))
        selected_keys.append("decoded_payload")
        return payload, selected_keys

    return payload, selected_keys


def project_graph_artifact_result(
    *,
    node_id: str,
    artifact_bucket: str,
    artifact: Dict[str, Any],
    summary_limit: int = 2600,
) -> Optional[Dict[str, Any]]:
    if not isinstance(artifact, dict):
        return None

    payload, selected_keys = _select_primary_payload(artifact)
    for key in SUMMARY_KEYS:
        if key in artifact and _is_present(artifact.get(key)):
            payload[key] = _project_value(artifact.get(key))
            selected_keys.append(key)

    if not payload:
        return None

    node_key = str(node_id or "").strip() or "graph_node"
    summary = _json_dumps(payload, limit=summary_limit)
    if not summary:
        return None

    return {
        "title": f"{node_key} graph artifacts",
        "summary": summary,
        "content": summary,
        "source": f"graph_artifact:{artifact_bucket}",
        "structured_payload": payload,
        "meta": {
            "node_id": node_key,
            "artifact_bucket": str(artifact_bucket or ""),
            "artifact_keys": list(artifact.keys()),
            "projected_keys": selected_keys,
        },
    }
