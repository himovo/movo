"""Open-source knowledge authorization for retrieval candidates.

Enterprise editions can provide another implementation of the policy contract
without adding organization/role ACL concepts to the open-source data model.
"""

from __future__ import annotations

from functools import lru_cache
import importlib
import os
from typing import Any, Protocol

from app.core.db import get_db


DOCUMENT_COLLECTION = "knowledge_documents"
RESOURCE_COLLECTION = "knowledge_resources"
GRANT_COLLECTION = "resource_grants"


class KnowledgeRetrievalAccessPolicy(Protocol):
    def filter_candidates(
        self,
        items: list[dict[str, Any]],
        *,
        main_id: str,
        user_id: str,
    ) -> list[dict[str, Any]]: ...


class OpenSourceKnowledgeRetrievalAccessPolicy:
    """Allow existing shared admin knowledge plus owned/shared personal knowledge."""

    def filter_candidates(
        self,
        items: list[dict[str, Any]],
        *,
        main_id: str,
        user_id: str,
    ) -> list[dict[str, Any]]:
        document_ids = sorted({
            str(item.get("documentId") or "")
            for item in items
            if str(item.get("documentId") or "")
        })
        if not document_ids:
            return []

        db = get_db()
        documents = list(db[DOCUMENT_COLLECTION].find(
            {"_id": {"$in": document_ids}, "main_id": main_id, "deleted_at": None},
            {
                "_id": 1,
                "scope": 1,
                "owner_user_id": 1,
                "resource_id": 1,
                "name": 1,
                "original_filename": 1,
            },
        ))
        documents_by_id = {
            str(document.get("_id") or ""): document
            for document in documents
            if str(document.get("_id") or "")
        }
        allowed_document_ids = {
            str(document.get("_id") or "")
            for document in documents
            if str(document.get("scope") or "organization") != "personal"
        }
        if not user_id:
            return _keep_documents(items, allowed_document_ids, documents_by_id)

        personal = [
            document for document in documents
            if str(document.get("scope") or "organization") == "personal"
        ]
        resource_ids = sorted({
            str(document.get("resource_id") or "")
            for document in personal
            if str(document.get("resource_id") or "")
        })
        owned_resource_ids = {
            str(resource.get("_id") or "")
            for resource in db[RESOURCE_COLLECTION].find(
                {
                    "_id": {"$in": resource_ids},
                    "main_id": main_id,
                    "owner_user_id": user_id,
                    "deleted_at": None,
                },
                {"_id": 1},
            )
        } if resource_ids else set()
        shared_resource_ids = {
            str(grant.get("resource_id") or "")
            for grant in db[GRANT_COLLECTION].find(
                {
                    "main_id": main_id,
                    "resource_type": "personal_knowledge",
                    "resource_id": {"$in": resource_ids},
                    "recipient_user_id": user_id,
                    "status": "active",
                },
                {"resource_id": 1},
            )
        } if resource_ids else set()

        allowed_resource_ids = owned_resource_ids | shared_resource_ids
        allowed_document_ids.update(
            str(document.get("_id") or "")
            for document in personal
            if str(document.get("resource_id") or "") in allowed_resource_ids
        )
        return _keep_documents(items, allowed_document_ids, documents_by_id)


def _keep_documents(
    items: list[dict[str, Any]],
    allowed_document_ids: set[str],
    documents_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in items:
        document_id = str(item.get("documentId") or "")
        if document_id not in allowed_document_ids:
            continue
        document = documents_by_id.get(document_id) or {}
        scope = str(document.get("scope") or "organization")
        metadata = {
            **dict(item.get("metadata") or {}),
            "document_title": str(
                document.get("original_filename") or document.get("name") or ""
            ).strip(),
            "knowledge_scope": scope,
            "knowledge_label": "个人知识" if scope == "personal" else "企业知识",
        }
        output.append({**item, "metadata": metadata})
    return output


@lru_cache(maxsize=1)
def get_knowledge_retrieval_access_policy() -> KnowledgeRetrievalAccessPolicy:
    """Load a distribution-owned policy when installed; default to community behavior."""
    module_name = os.getenv("MOVO_DOC_PROCESSING_RETRIEVAL_POLICY_MODULE", "").strip()
    if not module_name:
        return OpenSourceKnowledgeRetrievalAccessPolicy()
    module = importlib.import_module(module_name)
    factory = getattr(module, "create_retrieval_access_policy", None)
    if not callable(factory):
        raise RuntimeError(
            f"Retrieval policy module {module_name!r} must export create_retrieval_access_policy()"
        )
    return factory()


knowledge_retrieval_access_policy: KnowledgeRetrievalAccessPolicy = (
    get_knowledge_retrieval_access_policy()
)
