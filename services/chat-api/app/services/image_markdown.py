from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from app.llm.factory import get_llm_client
from app.llm.types import Message, Role


USER_EVIDENCE_IMAGE_SOURCES = {"embedded_docx_image", "user_upload"}
PLACEHOLDER_IMAGE_URL_PATTERN = (
    r"https?://(?:"
    r"via\.placeholder\.com"
    r"|dummyimage\.com"
    r"|placehold\.co"
    r"|placeholder\.com"
    r"|fake-mcp-image\.com"
    r")/[^\"'\s>)]+"
)


def merge_image_layout_hints(*hint_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for group in hint_groups:
        if not isinstance(group, list):
            continue
        for item in group:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            if not path:
                continue
            key = (
                str(item.get("image_id") or "").strip(),
                path,
                str(item.get("target_heading") or "").strip(),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _filter_existing_images(markdown: str, image_layout_hints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    content = str(markdown or "")
    if not content.strip():
        return []
    filtered: List[Dict[str, Any]] = []
    for item in image_layout_hints:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        if path in content:
            continue
        filtered.append(item)
    return filtered


def _hint_source(hint: Dict[str, Any]) -> str:
    return str(hint.get("asset_source") or hint.get("source") or "").strip()


def _user_evidence_hints(image_layout_hints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        dict(item)
        for item in image_layout_hints
        if isinstance(item, dict)
        and _hint_source(item) in USER_EVIDENCE_IMAGE_SOURCES
        and _sanitize_image_path(item.get("path"))
    ]


def _markdown_contains_hint(markdown: str, hint: Dict[str, Any]) -> bool:
    path = _sanitize_image_path(hint.get("path"))
    return bool(path and path in str(markdown or ""))


def _count_user_evidence_images(markdown: str, image_layout_hints: List[Dict[str, Any]]) -> int:
    seen = set()
    for hint in _user_evidence_hints(image_layout_hints):
        path = _sanitize_image_path(hint.get("path"))
        if path and path not in seen and path in str(markdown or ""):
            seen.add(path)
    return len(seen)


def _dynamic_user_image_target(markdown: str, image_layout_hints: List[Dict[str, Any]]) -> int:
    protected = _user_evidence_hints(image_layout_hints)
    if not protected:
        return 0
    content = str(markdown or "")
    heading_count = len(re.findall(r"(?m)^\s*#{1,3}\s+\S+", content))
    section_count = max(1, heading_count)
    by_structure = section_count * 4
    by_length = max(4, len(content) // 280)
    has_embedded_docx = any(_hint_source(item) == "embedded_docx_image" for item in protected)
    cap = 32 if has_embedded_docx else 16
    floor = 8 if has_embedded_docx and len(protected) >= 12 else 4
    target = max(floor, by_structure, by_length)
    return min(len(protected), cap, target)


def _ensure_user_evidence_coverage(
    *,
    markdown: str,
    image_layout_hints: List[Dict[str, Any]],
) -> str:
    protected = _user_evidence_hints(image_layout_hints)
    target = _dynamic_user_image_target(markdown, protected)
    if target <= 0:
        return str(markdown or "").strip()

    current_count = _count_user_evidence_images(markdown, protected)
    if current_count >= target:
        return str(markdown or "").strip()

    missing: List[Dict[str, Any]] = []
    for hint in protected:
        if _markdown_contains_hint(markdown, hint):
            continue
        missing.append(hint)
        if current_count + len(missing) >= target:
            break
    if not missing:
        return str(markdown or "").strip()
    return _inject_images_deterministically(markdown=markdown, image_layout_hints=missing)


def _normalize_heading_token(value: str) -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"^\d+(?:\.\d+)*\s*", "", raw)
    raw = re.sub(r"[^\w\u4e00-\u9fff]+", "", raw)
    return raw


def _tokenize_cues(values: List[Any]) -> List[str]:
    tokens: List[str] = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        candidates = re.findall(r"[\w\u4e00-\u9fff]{2,}", text)
        if not candidates and len(text) >= 2:
            candidates = [text]
        for token in candidates:
            normalized = _normalize_heading_token(token)
            if len(normalized) < 2 or normalized in seen:
                continue
            seen.add(normalized)
            tokens.append(normalized)
            if len(tokens) >= 28:
                return tokens
    return tokens


def _sanitize_image_caption(value: Any, *, fallback: str = "image") -> str:
    caption = str(value or "").strip()
    caption = re.sub(r"[\r\n\t]+", " ", caption)
    caption = re.sub(r"\s{2,}", " ", caption).strip()
    caption = caption.replace("[", "（").replace("]", "）")
    if not caption:
        caption = fallback
    return caption[:160]


def _sanitize_image_path(value: Any) -> str:
    path = str(value or "").strip()
    if path.startswith("<") and path.endswith(">"):
        path = path[1:-1].strip()
    return path


def _best_section_insert_at(*, lines: List[str], headings: List[tuple[int, str]], hint: Dict[str, Any]) -> int:
    if not headings:
        return len(lines)
    cues = _tokenize_cues(
        [
            hint.get("caption"),
            hint.get("target_heading"),
            hint.get("rationale"),
            *list(hint.get("semantic_cues") or []),
            *list(hint.get("status_tags") or []),
        ]
    )
    if not cues:
        return len(lines)
    best_score = 0
    best_insert_at = len(lines)
    for idx, (line_no, heading) in enumerate(headings):
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        section_text = "\n".join([heading] + lines[line_no + 1 : min(end, line_no + 18)])
        normalized_section = _normalize_heading_token(section_text)
        score = sum(1 for cue in cues if cue and cue in normalized_section)
        if score > best_score:
            best_score = score
            best_line_score = 0
            best_line_no = line_no
            for body_line_no in range(line_no + 1, end):
                line_text = str(lines[body_line_no] or "").strip()
                if not line_text or line_text.startswith("#") or line_text.startswith("!["):
                    continue
                normalized_line = _normalize_heading_token(line_text)
                line_score = sum(1 for cue in cues if cue and cue in normalized_line)
                if line_score > best_line_score:
                    best_line_score = line_score
                    best_line_no = body_line_no
            best_insert_at = min(end, best_line_no + 1)
    return best_insert_at if best_score > 0 else len(lines)


def _inject_images_deterministically(
    *,
    markdown: str,
    image_layout_hints: List[Dict[str, Any]],
) -> str:
    text = str(markdown or "").strip()
    if not text or not image_layout_hints:
        return text
    lines = text.splitlines()
    headings: List[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        stripped = str(line or "").strip()
        if not stripped.startswith("#"):
            continue
        title = re.sub(r"^\s*#{1,6}\s+", "", stripped).strip()
        if title:
            headings.append((idx, title))

    insertions: List[tuple[int, str]] = []
    for hint in image_layout_hints:
        path = _sanitize_image_path(hint.get("path"))
        if not path or path in text:
            continue
        caption = _sanitize_image_caption(hint.get("caption") or hint.get("image_id"), fallback="image")
        target_heading = _normalize_heading_token(str(hint.get("target_heading") or "").strip())
        insert_at = len(lines)
        if target_heading and headings:
            for line_no, heading in headings:
                heading_norm = _normalize_heading_token(heading)
                if heading_norm and (target_heading in heading_norm or heading_norm in target_heading):
                    insert_at = line_no + 1
                    break
        if insert_at == len(lines) and headings:
            insert_at = _best_section_insert_at(lines=lines, headings=headings, hint=hint)
        insertions.append((insert_at, f"\n![{caption}]({path})\n"))

    if not insertions:
        return text
    for line_no, snippet in sorted(insertions, key=lambda item: item[0], reverse=True):
        idx = max(0, min(int(line_no), len(lines)))
        lines.insert(idx, snippet)
    return "\n".join(lines).strip()


async def inject_images_inline(
    *,
    markdown: str,
    image_layout_hints: List[Dict[str, Any]],
) -> str:
    content = str(markdown or "").strip()
    if not content or not image_layout_hints:
        return content

    pending_hints = _filter_existing_images(content, image_layout_hints)
    if not pending_hints:
        return content

    llm = get_llm_client(streaming=False, stage="compose", intent="generation")
    prompt_payload = {
        "document_markdown": content,
        "image_layout_hints": pending_hints,
        "rules": [
            "Insert each image markdown marker near the most relevant section, not at the end as an appendix.",
            "If target_heading is provided, place that image inside the matching section whenever possible.",
            "Use exact marker format: ![caption](<path>) where caption prefers the provided caption field, otherwise image_id.",
            "Keep the original section structure and wording as much as possible.",
            "Do not remove existing text or existing images. Only add new inline image markdown blocks.",
            "If an image has no strong anchor, place it in the nearest related section.",
            "Do not output JSON or explanations.",
        ],
    }
    try:
        resp = await llm.ainvoke(
            [
                Message(
                    role=Role.SYSTEM,
                    content=(
                        "You are a document layout refiner in the final compose pass. "
                        "Place image markers inline in existing markdown using semantic relevance."
                    ),
                ),
                Message(role=Role.USER, content=json.dumps(prompt_payload, ensure_ascii=False, indent=2)),
            ]
        )
    except Exception:
        return content

    rewritten = str(getattr(resp, "content", "") or "").strip()
    if rewritten and "![" in rewritten:
        return _ensure_user_evidence_coverage(markdown=rewritten, image_layout_hints=pending_hints)
    deterministic = _inject_images_deterministically(markdown=content, image_layout_hints=pending_hints)
    return _ensure_user_evidence_coverage(markdown=deterministic, image_layout_hints=pending_hints)


def normalize_image_markdown(markdown: str) -> str:
    text = str(markdown or "")
    if not text:
        return text

    # Writer prompts sometimes emit external placeholder images before the
    # visual materializer inserts real generated assets. Those placeholders are
    # not deliverable content and often fail to load in the frontend.
    text = re.sub(
        rf"(?is)\n?\s*<img\b[^>]*\bsrc=[\"']{PLACEHOLDER_IMAGE_URL_PATTERN}[\"'][^>]*>\s*\n?",
        "\n",
        text,
    )
    text = re.sub(
        rf"(?m)^\s*!\[[^\]\n]*\]\({PLACEHOLDER_IMAGE_URL_PATTERN}(?:\s+\"[^\"]*\")?\)\s*$\n?",
        "",
        text,
    )

    def repl(match: re.Match[str]) -> str:
        caption = _sanitize_image_caption(match.group(1), fallback="image")
        path = _sanitize_image_path(match.group(2))
        return f"![{caption}]({path})"

    text = re.sub(r"!\[(.*?)\]\(<([^>]+)>\)", repl, text, flags=re.DOTALL)
    text = re.sub(r"!\[(.*?)\]\(([^)\r\n]+)\)", repl, text, flags=re.DOTALL)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
