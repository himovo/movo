from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from .models import WriterEvidencePacket


def render_writer_evidence_packet(packet: WriterEvidencePacket | Dict[str, Any]) -> str:
    """Render the canonical packet as the final writer-facing evidence block.

    This is deliberately deterministic: it does not summarize, rank, or
    discard materials. Builder owns evidence selection; this module only
    serializes every writer-facing packet field into readable Markdown.
    """
    resolved = packet if isinstance(packet, WriterEvidencePacket) else WriterEvidencePacket.model_validate(packet)
    parts: List[str] = [
        "## Writer Evidence Packet",
        "",
        "Use this packet as the complete factual boundary. Do not invent facts, numbers, sources, or failure states absent from it.",
    ]
    _append_subject(parts, resolved.subject)
    _append_bullets(parts, "Confirmed Facts", resolved.confirmed_facts)
    _append_json_materials(parts, "Business Datasets", resolved.business_datasets, value_key="data")
    _append_json_materials(parts, "Computed Metrics", resolved.computed_metrics, value_key="metrics")
    _append_excerpts(parts, resolved.source_excerpts)
    _append_citations(parts, resolved.citations)
    _append_bullets(parts, "Open Questions", resolved.open_questions)
    _append_json_materials(parts, "Execution Failures", resolved.execution_failures, value_key="")
    _append_coverage(parts, resolved)
    return "\n".join(parts).strip()


def _append_subject(parts: List[str], subject: Dict[str, Any]) -> None:
    if not isinstance(subject, dict):
        return
    values = []
    if str(subject.get("canonical_subject") or "").strip():
        values.append(f"- subject: {str(subject.get('canonical_subject') or '').strip()}")
    for fact in list(subject.get("supporting_facts") or []):
        text = str(fact or "").strip()
        if text:
            values.append(f"- supporting fact: {text}")
    if values:
        parts.extend(["", "### Subject", *values])


def _append_bullets(parts: List[str], heading: str, values: Iterable[Any]) -> None:
    rows = [str(value or "").strip() for value in values if str(value or "").strip()]
    if rows:
        parts.extend(["", f"### {heading}", *[f"- {row}" for row in rows]])


def _append_json_materials(
    parts: List[str],
    heading: str,
    materials: Iterable[Dict[str, Any]],
    *,
    value_key: str,
) -> None:
    rows = [item for item in materials if isinstance(item, dict)]
    if not rows:
        return
    parts.extend(["", f"### {heading}"])
    for index, item in enumerate(rows, start=1):
        title = str(item.get("title") or f"item_{index}").strip()
        parts.extend(["", f"#### {title}"])
        provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
        provenance_text = _provenance_line(provenance)
        if provenance_text:
            parts.append(provenance_text)
        value = item if not value_key else item.get(value_key)
        parts.extend(["```json", _json(value), "```"])


def _append_excerpts(parts: List[str], excerpts: Iterable[Dict[str, Any]]) -> None:
    rows = [item for item in excerpts if isinstance(item, dict)]
    if not rows:
        return
    parts.extend(["", "### Source Excerpts"])
    for index, item in enumerate(rows, start=1):
        title = str(item.get("title") or f"source_{index}").strip()
        content = str(item.get("content") or "").strip()
        parts.extend(["", f"#### {title}"])
        _append_source_locator(parts, item)
        if content:
            parts.append(content)


def _append_citations(parts: List[str], citations: Iterable[Dict[str, Any]]) -> None:
    rows = [item for item in citations if isinstance(item, dict)]
    if not rows:
        return
    parts.extend(["", "### Citations"])
    for index, item in enumerate(rows, start=1):
        title = str(item.get("title") or item.get("citation_id") or f"citation_{index}").strip()
        locator = _source_locator(item)
        parts.append(f"- {title}{': ' + locator if locator else ''}")


def _append_coverage(parts: List[str], packet: WriterEvidencePacket) -> None:
    coverage = packet.coverage
    parts.extend(
        [
            "",
            "### Evidence Boundary",
            f"- coverage_complete: {str(bool(coverage.complete)).lower()}",
            f"- coverage_truncated: {str(bool(coverage.truncated)).lower()}",
        ]
    )
    if coverage.unsupported_records:
        parts.append("- unsupported_records:")
        parts.extend(f"  - {_json(item)}" for item in coverage.unsupported_records)
def _append_source_locator(parts: List[str], item: Dict[str, Any]) -> None:
    locator = _source_locator(item)
    if locator:
        parts.append(f"Source: {locator}")


def _source_locator(item: Dict[str, Any]) -> str:
    values = [
        item.get("source_url"),
        item.get("source"),
        item.get("document_id"),
        item.get("chunk_id"),
        item.get("page_no"),
    ]
    return " | ".join(str(value).strip() for value in values if str(value or "").strip())


def _provenance_line(provenance: Dict[str, Any]) -> str:
    values = [
        f"source_type={provenance.get('source_type')}" if provenance.get("source_type") else "",
        f"tool={provenance.get('tool')}" if provenance.get("tool") else "",
        f"provider_type={provenance.get('provider_type')}" if provenance.get("provider_type") else "",
        f"mcp_tool_name={provenance.get('mcp_tool_name')}" if provenance.get("mcp_tool_name") else "",
    ]
    tokens = [value for value in values if value]
    return "Provenance: " + ", ".join(tokens) if tokens else ""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
