from __future__ import annotations

import json
import re
from typing import Any, Dict, List
from urllib.parse import urlparse

from app.enterprise_capabilities.evidence.foundation.kb_document_sources import extract_kb_document_sources


def _source_type(item: Dict[str, Any]) -> str:
    tool = str(item.get("tool") or "").strip().lower()
    source = str(item.get("source_url") or item.get("source") or "").strip().lower()
    if "kb" in tool or "knowledge" in tool:
        return "kb"
    if source.startswith(("http://", "https://")):
        return "web"
    if any(token in tool for token in ("document", "file", "docx", "pdf", "xlsx")):
        return "document"
    if any(token in source for token in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", "文档", "文件")):
        return "document"
    return "internal"


def _source_name(item: Dict[str, Any]) -> str:
    source_url = str(item.get("source_url") or "").strip()
    source = str(item.get("source") or "").strip()
    candidate = source_url or source
    if candidate.startswith(("http://", "https://")):
        try:
            host = urlparse(candidate).netloc
            if host:
                return host.replace("www.", "")
        except Exception:
            pass
    return source[:120] if source else ""


def _json_text(value: str) -> str:
    text = str(value or "").strip()
    if not text or text[0] not in "[{":
        return ""
    try:
        parsed = json.loads(text)
    except Exception:
        return ""
    return json.dumps(parsed, ensure_ascii=False, indent=2)


def _empty_kb_result(value: str) -> bool:
    text = str(value or "").strip()
    if not text or text[0] not in "{[":
        return False
    try:
        parsed = json.loads(text)
    except Exception:
        return False
    if not isinstance(parsed, dict):
        return False
    provider = str(parsed.get("provider") or "").strip().lower()
    mode = str(parsed.get("mode") or "").strip().lower()
    used_count = int(parsed.get("usedCount") or parsed.get("used_count") or 0)
    retrieved_count = int(parsed.get("retrievedCount") or parsed.get("retrieved_count") or 0)
    sources = []
    evidence_bundle = parsed.get("evidenceBundle")
    if isinstance(evidence_bundle, dict):
        sources = list(evidence_bundle.get("sources") or [])
    return (
        mode == "qa"
        and "knowledge" in provider
        and used_count == 0
        and retrieved_count == 0
        and not sources
    )


def _looks_like_json_fragment(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    if text[0] in "{[}]":
        return True
    if text.startswith('",') or text.startswith('"}') or text.startswith('"]'):
        return True
    if text.count('":') >= 2:
        return True
    return False


def _digest_overview(text: str) -> str:
    body = str(text or "").split("### Sources", 1)[0]
    lines: List[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("### Deep Research Digest"):
            continue
        if line.startswith("**Queries:") or "Sources Analyzed:" in line:
            continue
        if line.startswith("#"):
            continue
        line = line.strip("- ").strip()
        if line:
            lines.append(line)
        if len(" ".join(lines)) > 280:
            break
    return " ".join(lines)[:360]


def _extract_digest_source_rows(text: str) -> List[Dict[str, str]]:
    raw = str(text or "")
    if "### Sources" not in raw:
        return []
    before, _, after = raw.partition("### Sources")
    fallback_summary = _digest_overview(before)
    rows: List[Dict[str, str]] = []
    lines = [line.strip() for line in after.splitlines() if line.strip()]
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        idx += 1
        if not line.startswith("["):
            continue
        # Real search usually uses:
        # [1] Title
        # https://example.com
        # or compactly: [1] Title https://example.com | quality_score=...
        match = re.match(r"^\[(\d+)\]\s+(.+?)\s+(https?://\S+)(?:\s+\|\s*(.*))?$", line)
        if match:
            rows.append(
                {
                    "title": match.group(2).strip(),
                    "source_url": match.group(3).strip(),
                    "snippet": fallback_summary,
                }
            )
            continue
        # Mock search: "[1] title" followed by "https://example.com".
        title = re.sub(r"^\[\d+\]\s*", "", line).strip()
        if idx < len(lines) and lines[idx].startswith(("http://", "https://")):
            url = lines[idx].strip()
            snippet = ""
            if idx + 2 < len(lines) and "quality_score=" in lines[idx + 1]:
                snippet = lines[idx + 2].strip()
            rows.append(
                {
                    "title": title,
                    "source_url": url,
                    "snippet": snippet or fallback_summary,
                }
            )
            idx += 1
    return rows


def _extract_raw_tool_digest_rows(bundle: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for record in list(bundle.get("raw_tool_results") or []):
        if not isinstance(record, dict):
            continue
        tool = str(record.get("tool") or "").strip().lower()
        if tool != "progressive_research":
            continue
        result = record.get("result")
        text = result if isinstance(result, str) else ""
        if not text and isinstance(result, dict):
            for key in ("content", "text", "result", "summary"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    text = value
                    break
        rows.extend(_extract_digest_source_rows(text))
    return rows


def _is_deep_research_digest(value: str) -> bool:
    text = str(value or "")
    return "### Deep Research Digest" in text or "Sources Analyzed:" in text


def _looks_like_non_user_fact(value: Any) -> bool:
    text = str(value or "").strip()
    if _looks_like_json_fragment(text):
        return True
    if _is_deep_research_digest(text):
        return True
    if text.startswith("#") or text.startswith("---"):
        return True
    if text.count("**") >= 4 and ("##" in text or "|" in text):
        return True
    return False


def build_user_evidence_payload(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Project a runtime evidence bundle into fields suitable for end users."""
    if not isinstance(bundle, dict):
        return {}
    sources: List[Dict[str, Any]] = []
    seen: set[str] = set()
    raw_digest_rows = _extract_raw_tool_digest_rows(bundle)
    has_search_digest = bool(raw_digest_rows)
    for digest_idx, digest_row in enumerate(raw_digest_rows, start=1):
        digest_url = str(digest_row.get("source_url") or "").strip()
        digest_title = str(digest_row.get("title") or "").strip()
        digest_key = digest_url or digest_title
        if digest_key and digest_key in seen:
            continue
        if digest_key:
            seen.add(digest_key)
        digest_source_name = _source_name({"source_url": digest_url})
        sources.append(
            {
                "id": f"ev_raw_{digest_idx}",
                "title": digest_title[:180] or digest_source_name or "网页资料",
                "source_name": digest_source_name,
                "snippet": str(digest_row.get("snippet") or "").strip()[:520],
                "source_type": "web",
                "source_url": digest_url[:800],
            }
        )
    for idx, item in enumerate(list(bundle.get("results") or [])[:20], start=1):
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool") or "").strip().lower()
        title = str(item.get("title") or "").strip()
        summary = str(item.get("summary") or item.get("content") or "").strip()
        content = str(item.get("content") or item.get("summary") or "").strip()
        if tool == "kb_search" and _empty_kb_result(content or summary):
            continue
        kb_document_sources = extract_kb_document_sources(item)
        if kb_document_sources:
            for source in kb_document_sources:
                key = f"doc:{source.get('document_id') or ''}:{source.get('chunk_id') or ''}"
                if key in seen:
                    continue
                seen.add(key)
                source = dict(source)
                source["id"] = str(source.get("id") or f"ev_{idx}_{len(sources) + 1}")
                sources.append(source)
            continue
        pretty_json = _json_text(content) or _json_text(summary)
        source_url = str(item.get("source_url") or "").strip()
        source_name = _source_name(item)
        if not title and not summary:
            continue
        is_search_digest = _is_deep_research_digest(content or summary)
        has_search_digest = has_search_digest or is_search_digest
        if is_search_digest and raw_digest_rows:
            continue
        digest_rows = _extract_digest_source_rows(content or summary)
        if digest_rows:
            for digest_idx, digest_row in enumerate(digest_rows, start=1):
                digest_url = str(digest_row.get("source_url") or "").strip()
                digest_title = str(digest_row.get("title") or "").strip()
                digest_key = digest_url or digest_title
                if digest_key and digest_key in seen:
                    continue
                if digest_key:
                    seen.add(digest_key)
                digest_source_name = _source_name({"source_url": digest_url})
                sources.append(
                    {
                        "id": f"ev_{idx}_{digest_idx}",
                        "title": digest_title[:180] or digest_source_name or "网页资料",
                        "source_name": digest_source_name,
                        "snippet": str(digest_row.get("snippet") or "").strip()[:520],
                        "source_type": "web",
                        "source_url": digest_url[:800],
                    }
                )
            continue
        if is_search_digest:
            continue
        key = (source_url or source_name or title or summary[:80]).strip()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        source_type = _source_type(item)
        row: Dict[str, Any] = {
            "id": f"ev_{idx}",
            "title": title[:180] or source_name or "资料来源",
            "source_name": source_name or ("内部知识库" if source_type in {"kb", "internal"} else ""),
            "snippet": (summary[:520] if not pretty_json else ""),
            "source_type": source_type,
        }
        if pretty_json:
            row["content_format"] = "json"
            row["content"] = pretty_json
        elif content:
            row["content"] = content[:8000]
        if source_url.startswith(("http://", "https://")):
            row["source_url"] = source_url[:800]
        sources.append(row)

    if not sources and not bundle.get("confirmed_facts"):
        return {}

    web_count = len([x for x in sources if x.get("source_type") == "web"])
    kb_count = len([x for x in sources if x.get("source_type") in {"kb", "internal"}])
    doc_count = len([x for x in sources if x.get("source_type") == "document"])
    parts: List[str] = []
    if web_count:
        parts.append(f"网页资料 {web_count} 条")
    if kb_count:
        parts.append(f"内部知识库 {kb_count} 条")
    if doc_count:
        parts.append(f"文档资料 {doc_count} 条")
    summary = f"本次生成参考了 {len(sources)} 条资料" if sources else "本次生成使用了已提取事实"
    if parts:
        summary += "，其中" + "，".join(parts)
    return {
        "summary": summary,
        "sources": sources[:12],
        "confirmed_facts": []
        if has_search_digest
        else [
            str(x).strip()[:320]
            for x in list(bundle.get("confirmed_facts") or [])
            if str(x).strip() and not _looks_like_non_user_fact(x)
        ][:12],
        "open_questions": [
            str(x).strip()[:260]
            for x in list(bundle.get("open_questions") or [])
            if str(x).strip()
        ][:8],
    }
