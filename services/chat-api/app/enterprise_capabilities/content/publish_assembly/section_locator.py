from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class LocatedSection:
    section_id: str
    title: str
    start_line: int
    end_line: int
    purpose: str = ""

    def as_range(self, *, index: int) -> Dict[str, Any]:
        return {
            "index": index,
            "title": self.title,
            "title_token": normalize_heading_token(self.title),
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


def normalize_heading_token(value: str) -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"^\d+(?:\.\d+)*\s*", "", raw)
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", raw)


def locate_final_body_sections(markdown: str, *, max_sections: int = 24) -> List[LocatedSection]:
    text = str(markdown or "")
    lines = text.splitlines()
    if not lines:
        return []

    heading_candidates: List[Dict[str, Any]] = []
    for idx, line in enumerate(lines):
        title = _heading_title_for_line(lines=lines, idx=idx)
        if title:
            heading_candidates.append({"line_idx": idx, "title": title, "kind": _heading_kind(line)})

    heading_candidates = _drop_document_title_heading(candidates=heading_candidates)
    sections = _sections_from_heading_candidates(lines=lines, candidates=heading_candidates)
    if sections:
        return sections[:max_sections]
    return _paragraph_chunk_sections(lines=lines, max_sections=max_sections)


def final_markdown_section_ranges(markdown: str) -> List[Dict[str, Any]]:
    return [section.as_range(index=idx) for idx, section in enumerate(locate_final_body_sections(markdown))]


def _heading_kind(line: str) -> str:
    stripped = str(line or "").strip()
    if re.match(r"^#{1,6}\s+", stripped):
        return "markdown"
    if re.match(r"^\*\*[^*\n]{2,80}\*\*\s*$", stripped):
        return "bold"
    if re.match(r"^(?:第?[一二三四五六七八九十百千万]+[章节部分篇、.．]|[一二三四五六七八九十]+[、.．]|\d+(?:\.\d+)*[、.．])\s*", stripped):
        return "numbered"
    return "plain"


def _heading_title_for_line(*, lines: List[str], idx: int) -> str:
    raw = str(lines[idx] or "")
    stripped = raw.strip()
    if not stripped or _inside_fenced_code(lines=lines, idx=idx):
        return ""
    if stripped.startswith((">", "|")) or re.match(r"^[-*+]\s+", stripped):
        return ""

    markdown_match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", stripped)
    if markdown_match:
        return _clean_title(markdown_match.group(1))

    bold_match = re.match(r"^\*\*([^*\n]{2,80})\*\*\s*$", stripped)
    if bold_match and _has_block_boundary(lines=lines, idx=idx):
        title = _clean_title(bold_match.group(1))
        if _looks_like_title_text(title):
            return title

    numbered_match = re.match(
        r"^((?:第?[一二三四五六七八九十百千万]+[章节部分篇、.．]|[一二三四五六七八九十]+[、.．]|\d+(?:\.\d+)*[、.．])\s*[^。！？!?；;：:\n]{2,80})$",
        stripped,
    )
    if numbered_match and _has_block_boundary(lines=lines, idx=idx):
        return _clean_title(numbered_match.group(1))

    if _has_block_boundary(lines=lines, idx=idx) and _looks_like_title_text(stripped):
        return _clean_title(stripped)
    return ""


def _clean_title(value: str) -> str:
    title = str(value or "").strip()
    title = re.sub(r"^\*\*|\*\*$", "", title).strip()
    title = re.sub(r"\s+", " ", title)
    return title.strip(" ：:")


def _looks_like_title_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if len(text) > 32:
        return False
    if re.search(r"[。！？!?；;]$", text):
        return False
    if re.search(r"[，,].{6,}", text):
        return False
    if re.match(r"^\d+[).)]\s+", text):
        return False
    if len(re.findall(r"[\u4e00-\u9fff]", text)) >= 2:
        return True
    return bool(re.search(r"[A-Za-z]{3,}", text)) and len(text.split()) <= 8


def _has_block_boundary(*, lines: List[str], idx: int) -> bool:
    prev_blank = idx == 0 or not str(lines[idx - 1] or "").strip()
    next_blank = idx + 1 >= len(lines) or not str(lines[idx + 1] or "").strip()
    if prev_blank and next_blank:
        return True
    if prev_blank:
        return True
    return False


def _inside_fenced_code(*, lines: List[str], idx: int) -> bool:
    open_fence = False
    for pos, line in enumerate(lines[: idx + 1]):
        if re.match(r"^\s*(```|~~~)", str(line or "")):
            if pos == idx:
                return True
            open_fence = not open_fence
    return open_fence


def _drop_document_title_heading(*, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(candidates) <= 1:
        return candidates
    first = candidates[0]
    second = candidates[1]
    # A leading Markdown heading is a document title only when the body uses a
    # different heading convention (for example bold article section names).
    # In a normal ``# title`` -> ``## section`` hierarchy the H1 still owns the
    # preamble and must remain addressable for final-body visual placement.
    if (
        str(first.get("kind") or "") == "markdown"
        and str(second.get("kind") or "") != "markdown"
        and int(first.get("line_idx") or 0) < int(second.get("line_idx") or 0)
    ):
        return candidates[1:]
    return candidates


def _sections_from_heading_candidates(*, lines: List[str], candidates: List[Dict[str, Any]]) -> List[LocatedSection]:
    if not candidates:
        return []
    sections: List[LocatedSection] = []
    total_lines = len(lines)
    for idx, candidate in enumerate(candidates):
        start_idx = int(candidate.get("line_idx") or 0)
        end_idx = int(candidates[idx + 1].get("line_idx") or total_lines) - 1 if idx + 1 < len(candidates) else total_lines - 1
        if end_idx < start_idx:
            end_idx = start_idx
        excerpt = _excerpt(lines=lines, start_idx=start_idx + 1, end_idx=end_idx)
        sections.append(
            LocatedSection(
                section_id=f"final_s{len(sections) + 1}",
                title=str(candidate.get("title") or f"正文 {len(sections) + 1}").strip(),
                start_line=start_idx + 1,
                end_line=end_idx + 1,
                purpose=excerpt,
            )
        )
    return sections


def _paragraph_chunk_sections(*, lines: List[str], max_sections: int) -> List[LocatedSection]:
    paragraphs: List[tuple[int, int]] = []
    start: int | None = None
    for idx, line in enumerate(lines):
        if _inside_fenced_code(lines=lines, idx=idx):
            continue
        if str(line or "").strip():
            if start is None:
                start = idx
            continue
        if start is not None:
            paragraphs.append((start, idx - 1))
            start = None
    if start is not None:
        paragraphs.append((start, len(lines) - 1))
    if not paragraphs:
        return []

    sections: List[LocatedSection] = []
    chunk_size = 3
    for chunk_start in range(0, len(paragraphs), chunk_size):
        chunk = paragraphs[chunk_start: chunk_start + chunk_size]
        start_idx = chunk[0][0]
        end_idx = chunk[-1][1]
        sections.append(
            LocatedSection(
                section_id=f"final_s{len(sections) + 1}",
                title=f"正文 {len(sections) + 1}",
                start_line=start_idx + 1,
                end_line=end_idx + 1,
                purpose=_excerpt(lines=lines, start_idx=start_idx, end_idx=end_idx),
            )
        )
        if len(sections) >= max_sections:
            break
    return sections


def _excerpt(*, lines: List[str], start_idx: int, end_idx: int) -> str:
    if end_idx < start_idx:
        return ""
    return re.sub(r"\s+", " ", "\n".join(lines[start_idx: end_idx + 1])).strip()[:500]
