from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


def _clean_text(value: Any, *, limit: int = 0) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if limit and len(text) > limit:
        return text[:limit].rstrip()
    return text


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _first_text(item: Dict[str, Any], keys: Iterable[str], *, limit: int = 0) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return _clean_text(value, limit=limit)
    return ""


def _push_unique(target: List[str], value: Any, *, limit: int, item_limit: int) -> None:
    token = _clean_text(value, limit=item_limit)
    if not token:
        return
    seen = {str(item).strip() for item in target if str(item).strip()}
    if token in seen:
        return
    target.append(token)
    if len(target) > limit:
        del target[limit:]


def _source_url(item: Dict[str, Any], meta: Dict[str, Any]) -> str:
    return _clean_text(
        item.get("url")
        or item.get("source_url")
        or item.get("link")
        or item.get("source")
        or meta.get("url")
        or meta.get("source_url")
        or meta.get("source")
        or "",
        limit=500,
    )


def _split_fact_candidates(text: str, *, limit: int = 6) -> List[str]:
    source = _clean_text(text, limit=6000)
    if not source:
        return []
    parts = re.split(r"(?<=[。！？；;!?])\s*|(?<=[.!?])\s+|\n+|(?<=\))\s*(?=[A-Z]\.)", source)
    out: List[str] = []
    for part in parts:
        token = _clean_text(part, limit=500)
        if len(token) < 12:
            continue
        out.append(token)
        if len(out) >= limit:
            break
    if not out and source:
        out.append(_clean_text(source, limit=500))
    return out


class EvidenceNormalizer:
    """Normalize heterogeneous runtime evidence into the existing evidence_bundle contract."""

    @classmethod
    def normalize_bundle(cls, bundle: Dict[str, Any] | None) -> Dict[str, Any]:
        base = dict(bundle or {}) if isinstance(bundle, dict) else {}
        results = cls.normalize_results(base.get("results") or [])
        confirmed_facts = cls.normalize_confirmed_facts(
            existing=base.get("confirmed_facts") or [],
            results=results,
            limit=72,
        )
        base["results"] = results
        base["confirmed_facts"] = confirmed_facts
        base["open_questions"] = [
            _clean_text(item, limit=300)
            for item in list(base.get("open_questions") or [])
            if _clean_text(item)
        ][:16]
        return base

    @classmethod
    def build_research_bundle(
        cls,
        *,
        query: str,
        tools_used: List[str],
        results: List[Dict[str, Any]],
        raw_tool_results: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        bundle = {
            "query": _clean_text(query, limit=500),
            "tools_used": [_clean_text(tool, limit=80) for tool in list(tools_used or []) if _clean_text(tool)],
            "results": list(results or []),
            "raw_tool_results": list(raw_tool_results or []),
            "evidence_count": len([item for item in list(results or []) if isinstance(item, dict)]),
        }
        normalized = cls.normalize_bundle(bundle)
        normalized["evidence_count"] = len([item for item in list(normalized.get("results") or []) if isinstance(item, dict)])
        return normalized

    @classmethod
    def normalize_results(cls, results: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for idx, raw in enumerate(list(results or []), start=1):
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            meta = _as_dict(item.get("meta"))
            nested = _as_dict(item.get("result"))
            if nested and not _first_text(item, ("content", "summary", "snippet", "text")):
                nested_text = _first_text(nested, ("content", "summary", "snippet", "text", "result"), limit=6000)
                if nested_text:
                    item["content"] = nested_text

            content = _first_text(item, ("content", "text", "snippet", "summary", "digest", "abstract"), limit=6000)
            summary = _first_text(item, ("summary", "digest", "abstract", "snippet", "content", "text"), limit=1200)
            if not content and summary:
                content = summary
            if not summary and content:
                summary = content
            if not content and not summary:
                continue

            normalized = dict(item)
            normalized["tool"] = _clean_text(item.get("tool") or nested.get("tool") or "", limit=80)
            normalized["title"] = _clean_text(
                item.get("title") or item.get("name") or item.get("source_title") or nested.get("title") or f"evidence_{idx}",
                limit=220,
            )
            normalized["source"] = _clean_text(
                item.get("source") or item.get("domain") or item.get("publisher") or nested.get("source") or "",
                limit=500,
            )
            normalized["source_url"] = _source_url(item, meta)
            normalized["content"] = content
            normalized["summary"] = summary
            if item.get("score") is not None:
                normalized["score"] = item.get("score")
            if meta:
                normalized["meta"] = meta
            out.append(normalized)
        return out

    @classmethod
    def normalize_confirmed_facts(
        cls,
        *,
        existing: Any,
        results: List[Dict[str, Any]],
        limit: int = 48,
    ) -> List[str]:
        facts: List[str] = []
        for item in list(existing or []):
            _push_unique(facts, item, limit=limit, item_limit=360)
        for result in list(results or []):
            if not isinstance(result, dict):
                continue
            for key in ("summary", "content"):
                text = str(result.get(key) or "").strip()
                for fact in _split_fact_candidates(text, limit=4 if key == "summary" else 8):
                    _push_unique(facts, fact, limit=limit, item_limit=360)
                    if len(facts) >= limit:
                        return facts
        return facts


def normalize_evidence_bundle(bundle: Dict[str, Any] | None) -> Dict[str, Any]:
    return EvidenceNormalizer.normalize_bundle(bundle)
