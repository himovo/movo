"""Select bounded retrieval results after relevance scoring is complete."""

from __future__ import annotations

from typing import Any


def distinct_chunks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate vector hits without discarding a document's other clauses."""
    seen: set[tuple[str, str]] = set()
    output: list[dict[str, Any]] = []
    for item in items:
        key = (str(item.get("documentId") or ""), str(item.get("chunkId") or ""))
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def fuse_candidate_sources(
    semantic: list[dict[str, Any]], lexical: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge incomparable search scores using ranks, preserving both sources."""
    items: dict[tuple[str, str], dict[str, Any]] = {}
    scores: dict[tuple[str, str], float] = {}
    for source in (semantic, lexical):
        for rank, item in enumerate(distinct_chunks(source), start=1):
            key = (str(item.get("documentId") or ""), str(item.get("chunkId") or ""))
            if key not in items:
                items[key] = dict(item)
            if source is lexical:
                items[key]["matchType"] = "exact_identifier"
            scores[key] = scores.get(key, 0.0) + 1.0 / (60 + rank)
    return [
        {**items[key], "fusionScore": scores[key]}
        for key in sorted(items, key=lambda key: scores[key], reverse=True)
    ]


def select_final_chunks(items: list[dict[str, Any]], *, top_n: int) -> list[dict[str, Any]]:
    """Bound the model context only after all retrieval sources are ranked."""
    return distinct_chunks(items)[:top_n]
