from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


TEXT_LIKE_TYPES = {
    "text",
    "paragraph",
    "section_header",
    "title",
    "subtitle",
    "list_item",
    "caption",
}
TABLE_TYPES = {"table", "table_cell", "table_row"}
IMAGE_TYPES = {"picture", "image", "figure"}


@dataclass(frozen=True)
class RagChunkOptions:
    min_tokens: int = 400
    target_tokens: int = 750
    max_tokens: int = 1000
    overlap_tokens: int = 80


def build_rag_chunks(raw_chunks: list[dict[str, Any]], options: RagChunkOptions | None = None) -> list[dict[str, Any]]:
    opts = options or RagChunkOptions()
    output: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    def flush_pending() -> None:
        nonlocal pending
        if not pending:
            return
        output.append(_make_rag_chunk(len(output), pending, opts))
        pending = []

    for raw in raw_chunks:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if _is_noise_text(text):
            continue
        content_type = _normalize_content_type(str(raw.get("contentType") or "text"))

        if content_type in TABLE_TYPES:
            flush_pending()
            output.extend(_table_to_rag_chunks(raw, len(output), opts))
            continue

        if content_type in IMAGE_TYPES:
            flush_pending()
            output.append(_make_rag_chunk(len(output), [raw], opts, forced_type="image"))
            continue

        if not pending:
            pending.append(raw)
            continue

        merged_text = _join_chunk_texts([*pending, raw])
        can_merge = _can_merge_text_chunks(pending[-1], raw) or _can_merge_short_text_chunks(pending, raw, merged_text, opts)
        if can_merge and _estimate_token_count(merged_text) <= opts.max_tokens:
            pending.append(raw)
            if _estimate_token_count(merged_text) >= opts.target_tokens:
                flush_pending()
            continue

        flush_pending()
        pending.append(raw)

    flush_pending()
    return output


def _make_rag_chunk(
    index: int,
    source_chunks: list[dict[str, Any]],
    options: RagChunkOptions,
    forced_type: str | None = None,
) -> dict[str, Any]:
    text = _join_chunk_texts(source_chunks)
    title_path = _common_title_path(source_chunks)
    page_no = _first_present(source_chunks, "pageNo")
    source_ids = [str(item.get("chunkId") or "") for item in source_chunks if str(item.get("chunkId") or "").strip()]
    content_types = [_normalize_content_type(str(item.get("contentType") or "text")) for item in source_chunks]
    source_metadata = [item.get("metadata") for item in source_chunks if isinstance(item.get("metadata"), dict)]
    source_parsers = sorted({str(item.get("parser") or "").strip() for item in source_metadata if str(item.get("parser") or "").strip()})
    source_kinds = sorted({str(item.get("sourceKind") or "").strip() for item in source_metadata if str(item.get("sourceKind") or "").strip()})
    content_type = forced_type or _merged_content_type(content_types)
    contextual_text = "\n".join([*title_path, text]).strip() if title_path else text
    metadata = {
        "parser": "docling",
        "chunker": "MOVO-RAG-Optimizer",
        "baseChunker": "HybridChunker",
        "sourceChunkIds": source_ids,
        "sourceChunkCount": len(source_ids),
        "sourceContentTypes": sorted(set(content_types)),
        "sourceParsers": source_parsers,
        "sourceKinds": source_kinds,
        "tokenEstimate": _estimate_token_count(text),
        "ragOptions": {
            "minTokens": options.min_tokens,
            "targetTokens": options.target_tokens,
            "maxTokens": options.max_tokens,
            "overlapTokens": options.overlap_tokens,
        },
    }
    source_anchor = _collect_source_anchor(source_chunks, page_no)
    if source_anchor:
        metadata["sourceAnchor"] = source_anchor
    if content_type == "image":
        metadata["imageContext"] = _collect_media_context(source_chunks)
    elif content_type in TABLE_TYPES:
        metadata["tableContext"] = _collect_table_context(source_chunks)
    return {
        "chunkId": f"chunk_{index + 1:06d}",
        "ordinal": index,
        "text": text,
        "contextualText": contextual_text,
        "titlePath": title_path,
        "pageNo": page_no,
        "contentType": content_type,
        "chunkStage": "rag",
        "sourceChunkIds": source_ids,
        "metadata": metadata,
    }


def _table_to_rag_chunks(raw: dict[str, Any], start_index: int, options: RagChunkOptions) -> list[dict[str, Any]]:
    text = str(raw.get("text") or "").strip()
    content_type = _normalize_content_type(str(raw.get("contentType") or "table"))
    if content_type == "table_row":
        return [_make_rag_chunk(start_index, [raw], options, forced_type="table_row")]
    if _estimate_token_count(text) <= options.max_tokens:
        return [_make_rag_chunk(start_index, [raw], options, forced_type=content_type)]

    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    header: list[str] = []
    body = lines
    if len(lines) >= 2 and "|" in lines[0] and re.fullmatch(r"[\s|:\-]+", lines[1] or ""):
        header = lines[:2]
        body = lines[2:]

    rows: list[dict[str, Any]] = []
    current: list[str] = list(header)
    for line in body:
        candidate = "\n".join([*current, line])
        if len(current) > len(header) and _estimate_token_count(candidate) > options.max_tokens:
            rows.append(_make_table_part(raw, start_index + len(rows), current, options))
            current = [*header, line] if header else [line]
        else:
            current.append(line)
    if current:
        rows.append(_make_table_part(raw, start_index + len(rows), current, options))
    return rows


def _make_table_part(raw: dict[str, Any], index: int, lines: list[str], options: RagChunkOptions) -> dict[str, Any]:
    part = dict(raw)
    part["text"] = "\n".join(lines).strip()
    part["contentType"] = "table"
    result = _make_rag_chunk(index, [part], options, forced_type="table")
    result["metadata"]["tableContext"]["splitFromSourceChunkId"] = str(raw.get("chunkId") or "")
    return result


def _can_merge_text_chunks(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_type = _normalize_content_type(str(left.get("contentType") or "text"))
    right_type = _normalize_content_type(str(right.get("contentType") or "text"))
    if left_type not in TEXT_LIKE_TYPES or right_type not in TEXT_LIKE_TYPES:
        return False
    left_title = [str(item) for item in left.get("titlePath") or []]
    right_title = [str(item) for item in right.get("titlePath") or []]
    if not left_title or not right_title:
        return left_title == right_title
    if left_title == right_title:
        return True
    if len(left_title) >= 2 and len(right_title) >= 2 and left_title[:-1] == right_title[:-1]:
        return True
    return False


def _can_merge_short_text_chunks(
    pending: list[dict[str, Any]],
    right: dict[str, Any],
    merged_text: str,
    options: RagChunkOptions,
) -> bool:
    if not pending:
        return False
    right_type = _normalize_content_type(str(right.get("contentType") or "text"))
    if right_type not in TEXT_LIKE_TYPES:
        return False
    pending_types = [_normalize_content_type(str(item.get("contentType") or "text")) for item in pending]
    if any(item_type not in TEXT_LIKE_TYPES for item_type in pending_types):
        return False
    pending_text = _join_chunk_texts(pending)
    if _estimate_token_count(pending_text) >= options.min_tokens:
        return False
    if _estimate_token_count(merged_text) > options.max_tokens:
        return False
    pending_page = _first_present(pending, "pageNo")
    right_page = right.get("pageNo")
    if pending_page is None or right_page is None:
        return pending_page == right_page
    return pending_page == right_page


def _join_chunk_texts(chunks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for item in chunks:
        text = str(item.get("text") or "").strip()
        if not text or text in seen or _is_noise_text(text):
            continue
        seen.add(text)
        parts.append(text)
    return "\n\n".join(parts).strip()


def _common_title_path(chunks: list[dict[str, Any]]) -> list[str]:
    paths = [[str(part).strip() for part in item.get("titlePath") or [] if str(part).strip()] for item in chunks]
    paths = [path for path in paths if path]
    if not paths:
        return []
    common: list[str] = []
    for index, value in enumerate(paths[0]):
        if all(len(path) > index and path[index] == value for path in paths):
            common.append(value)
        else:
            break
    return common


def _first_present(chunks: list[dict[str, Any]], key: str) -> Any:
    for item in chunks:
        value = item.get(key)
        if value is not None and value != "":
            return value
    return None


def _merged_content_type(content_types: list[str]) -> str:
    unique = set(content_types)
    if "table_row" in unique:
        return "table_row"
    if unique & TABLE_TYPES:
        return "table"
    if unique & IMAGE_TYPES:
        return "image"
    if "list_item" in unique:
        return "text"
    return "text"


def _normalize_content_type(value: str) -> str:
    text = value.strip().lower()
    if text in {"document_index", "page_header", "page_footer"}:
        return "text"
    return text or "text"


def _collect_media_context(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sourceChunkIds": [str(item.get("chunkId") or "") for item in chunks if str(item.get("chunkId") or "").strip()],
        "pages": [item.get("pageNo") for item in chunks if item.get("pageNo") is not None],
    }


def _collect_table_context(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    context = {
        "sourceChunkIds": [str(item.get("chunkId") or "") for item in chunks if str(item.get("chunkId") or "").strip()],
        "pages": [item.get("pageNo") for item in chunks if item.get("pageNo") is not None],
        "repeatHeader": True,
    }
    for item in chunks:
        metadata = item.get("metadata") or {}
        if isinstance(metadata, dict) and isinstance(metadata.get("tableContext"), dict):
            context.update(metadata["tableContext"])
            break
    return context


def _collect_source_anchor(chunks: list[dict[str, Any]], fallback_page_no: Any = None) -> dict[str, Any]:
    bboxes: list[dict[str, Any]] = []
    page_no = fallback_page_no
    source_chunk_ids: list[str] = []
    table_context: dict[str, Any] | None = None
    for item in chunks:
        chunk_id = str(item.get("chunkId") or "").strip()
        if chunk_id:
            source_chunk_ids.append(chunk_id)
        metadata = item.get("metadata") or {}
        if not isinstance(metadata, dict):
            continue
        if table_context is None and isinstance(metadata.get("tableContext"), dict):
            table_context = dict(metadata["tableContext"])
        anchor = metadata.get("sourceAnchor")
        if not isinstance(anchor, dict):
            continue
        if table_context is None and isinstance(anchor.get("tableContext"), dict):
            table_context = dict(anchor["tableContext"])
        if page_no is None and anchor.get("pageNo") is not None:
            page_no = anchor.get("pageNo")
        raw_bboxes = anchor.get("bboxes")
        if not isinstance(raw_bboxes, list):
            raw_bboxes = [anchor.get("bbox")] if isinstance(anchor.get("bbox"), dict) else []
        for bbox in raw_bboxes:
            normalized = _normalize_anchor_bbox(bbox)
            if normalized:
                bboxes.append(normalized)
    deduped = _dedupe_bboxes(bboxes)
    output: dict[str, Any] = {}
    if page_no is not None:
        output["pageNo"] = page_no
    if source_chunk_ids:
        output["sourceChunkIds"] = source_chunk_ids
    if deduped:
        output["bboxes"] = deduped
        if len(deduped) == 1:
            output["bbox"] = deduped[0]
    if table_context:
        output["tableContext"] = table_context
    return output


def _normalize_anchor_bbox(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        left = float(raw.get("l"))
        top = float(raw.get("t"))
        right = float(raw.get("r"))
        bottom = float(raw.get("b"))
    except (TypeError, ValueError):
        return None
    if right <= left or bottom == top:
        return None
    return {
        "l": left,
        "t": top,
        "r": right,
        "b": bottom,
        "coordOrigin": str(raw.get("coordOrigin") or raw.get("coord_origin") or "TOPLEFT").upper(),
    }


def _dedupe_bboxes(bboxes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen = set()
    for bbox in bboxes:
        key = (
            round(float(bbox["l"]), 3),
            round(float(bbox["t"]), 3),
            round(float(bbox["r"]), 3),
            round(float(bbox["b"]), 3),
            str(bbox.get("coordOrigin") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(bbox)
    return output


def _estimate_token_count(text: str) -> int:
    if not text:
        return 0
    cjk_chars = len(re.findall(r"[\u3400-\u9fff]", text))
    words = len(re.findall(r"[A-Za-z0-9_]+", text))
    other_chars = len(re.sub(r"[\u3400-\u9fffA-Za-z0-9_\s]", "", text))
    return max(1, cjk_chars + words + max(1, other_chars // 2))


def _is_noise_text(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return True
    if len(compact) <= 3:
        return True
    return bool(re.fullmatch(r"[_\-—=~·.。…、|/\\]+", compact))
