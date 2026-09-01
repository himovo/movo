from __future__ import annotations

import json
from typing import Any, Dict, List

from app.infrastructure.observability.artifacts import write_debug_artifact
from app.infrastructure.observability.config import log_print

from .builder import WriterEvidencePacketBuilder
from .models import WriterEvidencePacket


def build_writer_evidence_packet_shadow(
    *,
    evidence_bundle: Dict[str, Any],
    tool_observations: List[Dict[str, Any]],
    output_spec: Dict[str, Any],
    user_query: str = "",
) -> Dict[str, Any]:
    packet = WriterEvidencePacketBuilder().build(
        evidence_bundle=evidence_bundle,
        tool_observations=tool_observations,
        output_spec=output_spec,
        user_query=user_query,
    )
    return persist_writer_evidence_packet(
        packet=packet,
        evidence_bundle=evidence_bundle,
        tool_observations=tool_observations,
        mode="shadow_only_not_sent_to_llm",
    )


def persist_writer_evidence_packet(
    *,
    packet: WriterEvidencePacket,
    evidence_bundle: Dict[str, Any],
    tool_observations: List[Dict[str, Any]],
    mode: str,
) -> Dict[str, Any]:
    packet_payload = packet.model_dump()
    packet_chars = len(json.dumps(packet_payload, ensure_ascii=False, default=str))
    raw_chars = len(
        json.dumps(
            {"evidence_bundle": evidence_bundle, "tool_observations": tool_observations},
            ensure_ascii=False,
            default=str,
        )
    )
    artifact_payload = {
        "mode": str(mode or ""),
        "diagnostics": {
            "packet_chars": packet_chars,
            "writer_input_raw_chars": raw_chars,
            "char_reduction_ratio": round(1 - (packet_chars / raw_chars), 4) if raw_chars else 0.0,
        },
        "packet": packet_payload,
    }
    artifact_path = write_debug_artifact("writer_evidence_packet", "packet", artifact_payload)
    coverage = packet.coverage.model_dump()
    summary = {
        "schema_version": packet.schema_version,
        "mode": str(mode or ""),
        "artifact_path": artifact_path,
        "packet_chars": packet_chars,
        "writer_input_raw_chars": raw_chars,
        "coverage_complete": bool(coverage.get("complete")),
        "coverage_truncated": bool(coverage.get("truncated")),
        "unsupported_records": len(list(coverage.get("unsupported_records") or [])),
        "source_types": coverage.get("source_types") or {},
    }
    event_name = "writer_evidence_packet_shadow" if mode == "shadow_only_not_sent_to_llm" else "writer_evidence_packet_active"
    log_print(f"[{event_name}] " + json.dumps(summary, ensure_ascii=False, default=str), flush=True)
    return summary
