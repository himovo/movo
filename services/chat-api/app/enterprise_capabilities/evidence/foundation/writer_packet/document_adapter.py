from __future__ import annotations

from typing import Any, Dict, List

from .common import text


_SOURCE_DOCUMENT_MARKERS = (
    "[文档Markdown]",
    "[文档语义摘要]",
    "[上传文档]",
    "[SOURCE_DOCUMENT]",
    "<SOURCE_DOCUMENT>",
)


def build_user_source_section_excerpt(user_query: str) -> Dict[str, Any]:
    source = str(user_query or "")
    starts = [source.find(marker) for marker in _SOURCE_DOCUMENT_MARKERS if source.find(marker) >= 0]
    if not starts:
        return {}
    content = source[min(starts) :].strip()
    if not content:
        return {}
    return {
        "source_type": "document",
        "kind": "user_source_section",
        "title": "用户提供原文",
        "content": content,
    }


def build_special_document_excerpts(evidence_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    excerpts: List[Dict[str, Any]] = []
    agreement = text(evidence_bundle.get("agreement_template_markdown"))
    if agreement:
        excerpts.append(
            {
                "source_type": "document",
                "kind": "agreement_template",
                "title": "协议底稿",
                "content": agreement,
            }
        )
    translation = text(evidence_bundle.get("translation_source_markdown"))
    if translation:
        excerpts.append(
            {
                "source_type": "document",
                "kind": "translation_source",
                "title": text(evidence_bundle.get("translation_source_filename")) or "翻译源文档",
                "content": translation,
                "source_url": text(evidence_bundle.get("translation_source_url")),
                "object_path": text(evidence_bundle.get("translation_source_object_path")),
            }
        )
    return excerpts
