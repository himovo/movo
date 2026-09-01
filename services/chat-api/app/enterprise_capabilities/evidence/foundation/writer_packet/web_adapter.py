from __future__ import annotations

from typing import Any, Dict, List

from app.enterprise_capabilities.evidence.foundation.user_payload import build_user_evidence_payload

from .common import classify_record, fingerprint, text


def build_web_materials(
    evidence_bundle: Dict[str, Any],
    tool_observations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    combined = dict(evidence_bundle or {})
    candidate_records = list(combined.get("results") or []) + list(tool_observations or [])
    web_records = [
        dict(item)
        for item in candidate_records
        if isinstance(item, dict) and classify_record(item) == "web"
    ]
    combined["results"] = web_records
    payload = build_user_evidence_payload(combined)
    excerpts: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    seen: set[str] = set()
    direct_source_urls: set[str] = set()
    for item in web_records:
        url = text(item.get("source_url") or item.get("url") or item.get("link"))
        if url.startswith(("http://", "https://")):
            direct_source_urls.add(url)
    for source in list(payload.get("sources") or []):
        if not isinstance(source, dict) or text(source.get("source_type")).lower() != "web":
            continue
        key = text(source.get("source_url") or source.get("id") or source.get("title"))
        token = key or fingerprint(source)
        if token in seen:
            continue
        seen.add(token)
        excerpts.append(
            {
                "source_type": "web",
                "title": text(source.get("title")),
                "content": text(source.get("content") or source.get("snippet")),
                "source_url": text(source.get("source_url")),
                "source_name": text(source.get("source_name")),
            }
        )
        citations.append(
            {
                "source_type": "web",
                "title": text(source.get("title")),
                "source_url": text(source.get("source_url")),
                "source_name": text(source.get("source_name")),
            }
        )
    return {
        "source_excerpts": excerpts,
        "citations": citations,
        "expected_direct_source_urls": sorted(direct_source_urls),
    }
