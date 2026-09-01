from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List

from app.enterprise_capabilities.evidence.foundation.external_web_raw import is_external_web_raw_record


def jsonable(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value or "")


def fingerprint(value: Any) -> str:
    try:
        body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        body = str(value or "")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def text(value: Any) -> str:
    return str(value or "").strip()


def unique_texts(values: Iterable[Any]) -> List[str]:
    output: List[str] = []
    seen: set[str] = set()
    for value in values:
        token = text(value)
        if not token or token in seen:
            continue
        seen.add(token)
        output.append(token)
    return output


def looks_like_serialized_structure(value: Any) -> bool:
    """Detect JSON-like runtime payloads that are not reader-facing facts.

    Runtime normalization can turn a structured result into a string and then
    promote its first 360/1200 characters into ``confirmed_facts``. The text
    may be valid JSON or a deliberately truncated JSON preview. Both forms
    belong in a typed dataset, never in the writer's fact list.
    """
    candidate = text(value)
    if not candidate:
        return False
    if candidate.startswith("{"):
        return True
    if re.match(r'^\[\s*(?:[\[{\"]|-?\d|true\b|false\b|null\b)', candidate, flags=re.IGNORECASE):
        return True
    if "...<truncated>" in candidate and re.search(r'"[A-Za-z_][A-Za-z0-9_]*"\s*:', candidate):
        return True
    return False


def is_writer_fact(value: Any) -> bool:
    candidate = text(value)
    return bool(candidate) and not looks_like_serialized_structure(candidate)


def record_tool(record: Dict[str, Any]) -> str:
    nested = record.get("result") if isinstance(record.get("result"), dict) else {}
    return text(record.get("tool") or record.get("tool_name") or nested.get("tool")).lower()


def record_meta(record: Dict[str, Any]) -> Dict[str, Any]:
    meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
    nested = record.get("result") if isinstance(record.get("result"), dict) else {}
    nested_results = nested.get("results") if isinstance(nested.get("results"), list) else []
    if not meta and nested_results and isinstance(nested_results[0], dict):
        meta = nested_results[0].get("meta") if isinstance(nested_results[0].get("meta"), dict) else {}
    return dict(meta or {})


def classify_record(record: Dict[str, Any]) -> str:
    tool = record_tool(record)
    meta = record_meta(record)
    source = text(record.get("source") or record.get("source_url")).lower()
    provider = text(meta.get("provider") or meta.get("providerType")).lower()
    if source.startswith("graph_artifact:"):
        return "graph"
    if tool == "kb_search" or "knowledge" in tool or "knowledge" in provider:
        return "kb"
    if provider == "mcp" or tool.startswith("external_mcp_") or meta.get("mcpToolName"):
        return "mcp"
    if is_external_web_raw_record(record):
        return "web"
    if not tool and source.startswith(("http://", "https://")):
        return "web"
    if any(token in tool for token in ("document", "file", "docx", "pdf", "xlsx")):
        return "document"
    if any(token in tool for token in ("image", "vision", "multimodal")):
        return "multimodal"
    return "business_tool"


def decode_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith("{") and raw.endswith("}"):
            try:
                parsed = json.loads(raw)
            except Exception:
                return {}
            return dict(parsed) if isinstance(parsed, dict) else {}
    return {}
