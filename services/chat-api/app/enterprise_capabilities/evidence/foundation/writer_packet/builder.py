from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from .common import classify_record, fingerprint, is_writer_fact, jsonable, text, unique_texts
from .document_adapter import build_special_document_excerpts, build_user_source_section_excerpt
from .kb_adapter import build_kb_materials
from .models import SourceCoverage, WriterEvidenceCoverage, WriterEvidencePacket
from .tool_adapter import build_tool_material
from .web_adapter import build_web_materials


class WriterEvidencePacketBuilder:
    def __init__(self) -> None:
        self._seen_by_target: Dict[int, set[str]] = {}

    def build(
        self,
        *,
        evidence_bundle: Dict[str, Any],
        tool_observations: List[Dict[str, Any]],
        output_spec: Dict[str, Any],
        user_query: str = "",
    ) -> WriterEvidencePacket:
        bundle = dict(evidence_bundle or {})
        observations = [dict(item) for item in list(tool_observations or []) if isinstance(item, dict)]
        results = [dict(item) for item in list(bundle.get("results") or []) if isinstance(item, dict)]
        raw_results = [dict(item) for item in list(bundle.get("raw_tool_results") or []) if isinstance(item, dict)]
        records = [("result", item) for item in results] + [("observation", item) for item in observations] + [
            ("raw_tool_result", item) for item in raw_results
        ]

        coverage_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        records_by_type: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for _origin, record in records:
            source_type = classify_record(record)
            coverage_counts[source_type]["input_records"] += 1
            records_by_type[source_type].append(record)

        packet = WriterEvidencePacket(
            subject=self._subject(output_spec),
            confirmed_facts=[],
            open_questions=unique_texts(bundle.get("open_questions") or []),
            multimodal_facts=self._multimodal_facts(output_spec),
        )
        packet.confirmed_facts, filtered_structured_facts = self._confirmed_facts(bundle)
        packet.coverage.filtered_structured_facts = filtered_structured_facts
        special_document_excerpts = build_special_document_excerpts(bundle)
        user_source_section = build_user_source_section_excerpt(user_query)
        if user_source_section:
            special_document_excerpts.append(user_source_section)
        coverage_counts["document"]["input_records"] += len(special_document_excerpts)
        self._extend_unique(
            packet.source_excerpts,
            special_document_excerpts,
            coverage_counts["document"],
        )
        coverage_counts["multimodal"]["input_records"] += len(packet.multimodal_facts)
        coverage_counts["multimodal"]["included_materials"] += len(packet.multimodal_facts)

        web = build_web_materials(bundle, observations)
        self._extend_unique(packet.source_excerpts, web.get("source_excerpts") or [], coverage_counts["web"])
        self._extend_unique(packet.citations, web.get("citations") or [], coverage_counts["web"], count_included=False)
        coverage_counts["web"]["filtered_records"] += sum(
            1 for item in raw_results if classify_record(item) == "web"
        )
        expected_web_urls = set(web.get("expected_direct_source_urls") or [])
        included_web_urls = {
            text(item.get("source_url")) for item in packet.citations if item.get("source_type") == "web"
        }
        if not expected_web_urls.issubset(included_web_urls):
            packet.coverage.truncated = True
            packet.coverage.notes.append("One or more direct external-web source URLs were not retained.")

        kb = build_kb_materials(records_by_type.get("kb") or [])
        self._extend_unique(packet.source_excerpts, kb.get("source_excerpts") or [], coverage_counts["kb"])
        self._extend_unique(packet.citations, kb.get("citations") or [], coverage_counts["kb"], count_included=False)
        self._extend_unique(packet.evidence_items, kb.get("evidence_items") or [], coverage_counts["kb"])
        expected_kb_citations = set(kb.get("expected_citation_keys") or [])
        included_kb_citations = {
            f"{item.get('document_id') or ''}:{item.get('chunk_id') or ''}"
            for item in packet.citations
            if item.get("source_type") == "kb"
        }
        if not expected_kb_citations.issubset(included_kb_citations):
            packet.coverage.truncated = True
            packet.coverage.notes.append("One or more KB citation coordinates were not retained.")

        for source_type, typed_records in records_by_type.items():
            if source_type in {"web", "kb"}:
                continue
            for record in typed_records:
                material = build_tool_material(record, source_type)
                failure = material.get("failure")
                if failure:
                    self._append_unique(packet.execution_failures, failure, coverage_counts[source_type])
                    continue
                if material.get("suppressed_structured_summary"):
                    packet.coverage.suppressed_duplicate_representations += 1
                    coverage_counts[source_type]["filtered_records"] += 1
                added = False
                for item in list(material.get("datasets") or []):
                    added = self._append_unique(packet.business_datasets, item, coverage_counts[source_type]) or added
                for item in list(material.get("metrics") or []):
                    added = self._append_unique(packet.computed_metrics, item, coverage_counts[source_type]) or added
                evidence_item = material.get("evidence_item") if isinstance(material.get("evidence_item"), dict) else {}
                if evidence_item:
                    added = self._append_unique(packet.evidence_items, evidence_item, coverage_counts[source_type]) or added
                source_excerpt = material.get("source_excerpt") if isinstance(material.get("source_excerpt"), dict) else {}
                if source_excerpt:
                    added = self._append_unique(packet.source_excerpts, source_excerpt, coverage_counts[source_type]) or added
                if not added:
                    coverage_counts[source_type]["unsupported_records"] += 1
                    packet.coverage.unsupported_records.append(
                        {
                            "source_type": source_type,
                            "tool": text(record.get("tool")),
                            "keys": sorted(str(key) for key in record.keys()),
                        }
                    )

        packet.coverage = self._coverage(
            coverage_counts,
            packet.coverage.unsupported_records,
            truncated=packet.coverage.truncated,
            extra_notes=packet.coverage.notes,
            filtered_structured_facts=packet.coverage.filtered_structured_facts,
            suppressed_duplicate_representations=packet.coverage.suppressed_duplicate_representations,
        )
        return packet

    @staticmethod
    def _subject(output_spec: Dict[str, Any]) -> Dict[str, Any]:
        resolution = output_spec.get("subject_resolution") if isinstance(output_spec.get("subject_resolution"), dict) else {}
        return {
            "canonical_subject": text(resolution.get("canonical_subject")),
            "status": text(resolution.get("status")),
            "supporting_facts": unique_texts(resolution.get("supporting_facts") or []),
        }

    @staticmethod
    def _confirmed_facts(bundle: Dict[str, Any]) -> tuple[List[str], int]:
        facts: List[Any] = list(bundle.get("confirmed_facts") or [])
        for item in list(bundle.get("user_request_facts") or []):
            if isinstance(item, dict):
                facts.append(item.get("text"))
        structured_count = sum(1 for item in facts if text(item) and not is_writer_fact(item))
        return unique_texts(item for item in facts if is_writer_fact(item)), structured_count

    @staticmethod
    def _multimodal_facts(output_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        multimodal = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
        image_facts = multimodal.get("image_facts") if isinstance(multimodal.get("image_facts"), dict) else {}
        output: List[Dict[str, Any]] = []
        for key in ("cross_image_facts", "uncertain", "images"):
            value = image_facts.get(key)
            if value not in (None, "", [], {}):
                output.append({"kind": key, "value": jsonable(value)})
        for key in ("vision_summary", "uploaded_assets", "image_layout_hints"):
            value = multimodal.get(key)
            if value not in (None, "", [], {}):
                output.append({"kind": key, "value": jsonable(value)})
        for key in ("image_assets", "image_observations", "vision_observations", "document_images", "uploaded_images"):
            value = output_spec.get(key)
            if value not in (None, "", [], {}):
                output.append({"kind": key, "value": jsonable(value)})
        return output

    def _append_unique(self, target: List[Dict[str, Any]], item: Dict[str, Any], counts: Dict[str, int]) -> bool:
        seen = self._seen_by_target.setdefault(id(target), {fingerprint(existing) for existing in target})
        token = fingerprint(item)
        if token in seen:
            counts["deduplicated_materials"] += 1
            return False
        target.append(jsonable(item))
        seen.add(token)
        counts["included_materials"] += 1
        return True

    def _extend_unique(
        self,
        target: List[Dict[str, Any]],
        items: List[Dict[str, Any]],
        counts: Dict[str, int],
        *,
        count_included: bool = True,
    ) -> None:
        for item in items:
            before = counts["included_materials"]
            self._append_unique(target, item, counts)
            if not count_included and counts["included_materials"] > before:
                counts["included_materials"] -= 1

    @staticmethod
    def _coverage(
        coverage_counts: Dict[str, Dict[str, int]],
        unsupported_records: List[Dict[str, Any]],
        *,
        truncated: bool,
        extra_notes: List[str],
        filtered_structured_facts: int,
        suppressed_duplicate_representations: int,
    ) -> WriterEvidenceCoverage:
        source_types = {
            source_type: SourceCoverage(**dict(counts))
            for source_type, counts in sorted(coverage_counts.items())
        }
        return WriterEvidenceCoverage(
            complete=not unsupported_records and not truncated,
            truncated=truncated,
            source_types=source_types,
            unsupported_records=list(unsupported_records),
            filtered_structured_facts=filtered_structured_facts,
            suppressed_duplicate_representations=suppressed_duplicate_representations,
            notes=[
                "Coverage is measured against evidence already available to the writer after runtime normalization.",
                "External-web raw records are intentionally filtered; compact sources and confirmed facts are retained.",
                "This shadow packet is not included in any LLM prompt.",
                "Structured runtime serializations are retained only in typed materials, never promoted as writer facts.",
            ] + list(extra_notes or []),
        )
