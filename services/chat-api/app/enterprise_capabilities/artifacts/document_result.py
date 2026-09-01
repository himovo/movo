"""Stable public result contract for parsed enterprise documents."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_INTERNAL_DOCUMENT_FIELDS = {"structured_content"}


def _public_document(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return {
        key: deepcopy(nested)
        for key, nested in value.items()
        if key not in _INTERNAL_DOCUMENT_FIELDS
    }


def public_document_parse_result(result: dict[str, Any]) -> dict[str, Any]:
    """Remove parser implementation trees while preserving usable content.

    Markdown, profiles, parse quality and stable artifact references remain in
    the DSH-facing contract. Docling's internal tree is intentionally private:
    it is large and contains JSON-reference keys such as ``$ref``.
    """
    projected = {
        key: deepcopy(nested)
        for key, nested in result.items()
        if key not in {"parsed_documents", "documents"}
    }
    parsed = [_public_document(item) for item in list(result.get("parsed_documents") or [])]
    projected["parsed_documents"] = parsed
    raw_documents = result.get("documents")
    documents = (
        {
            key: deepcopy(nested)
            for key, nested in raw_documents.items()
            if key not in {"parsed_documents", "active_document_markdown"}
        }
        if isinstance(raw_documents, dict)
        else None
    )
    if isinstance(documents, dict):
        # The full parsed documents already exist once at the top level. This
        # nested value is a legacy runtime duplicate and would triple large
        # Markdown payloads in the DSH tool result.
        projected["documents"] = documents
    return projected


__all__ = ["public_document_parse_result"]
