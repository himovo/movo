from __future__ import annotations

from typing import Any, Dict, List

from .models import WriterEvidencePacket
from .renderer import render_writer_evidence_packet


def render_section_writer_evidence_packet(packet: WriterEvidencePacket | Dict[str, Any]) -> str:
    """Render the canonical Packet unchanged for a sectional writer prompt."""
    return render_writer_evidence_packet(packet)


def build_writer_packet_source_references(packet: WriterEvidencePacket | Dict[str, Any]) -> List[Dict[str, Any]]:
    """Expose packet provenance in the legacy reference-list shape used by section prompts."""
    resolved = packet if isinstance(packet, WriterEvidencePacket) else WriterEvidencePacket.model_validate(packet)
    refs: List[Dict[str, Any]] = []
    seen = set()
    for item in [*resolved.citations, *resolved.source_excerpts]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("source_url") or item.get("url") or item.get("source") or "").strip()
        title = str(item.get("title") or item.get("citation_id") or url).strip()
        key = (url, title)
        if not title or key in seen:
            continue
        seen.add(key)
        refs.append({"index": len(refs) + 1, "title": title, "url": url})
    return refs
