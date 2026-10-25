from __future__ import annotations

from app.services import retrieval_access_policy as policy_module
from app.services.retrieval_access_policy import OpenSourceKnowledgeRetrievalAccessPolicy


def _matches(row, query):
    for key, expected in query.items():
        value = row.get(key)
        if isinstance(expected, dict) and "$in" in expected:
            if value not in expected["$in"]:
                return False
        elif value != expected:
            return False
    return True


class _Collection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, _projection):
        return [row for row in self.rows if _matches(row, query)]


class _Db:
    def __init__(self, *, documents, resources=(), grants=()):
        self.collections = {
            "knowledge_documents": _Collection(documents),
            "knowledge_resources": _Collection(resources),
            "resource_grants": _Collection(grants),
        }

    def __getitem__(self, name):
        return self.collections[name]


def _items(*document_ids):
    return [{"documentId": document_id} for document_id in document_ids]


def test_allows_existing_admin_knowledge_and_owned_personal_knowledge(monkeypatch):
    db = _Db(
        documents=[
            {"_id": "org", "main_id": "tenant", "scope": "organization", "name": "员工手册", "deleted_at": None},
            {"_id": "legacy", "main_id": "tenant", "original_filename": "legacy.pdf", "deleted_at": None},
            {"_id": "personal", "main_id": "tenant", "scope": "personal", "name": "项目笔记", "resource_id": "resource", "owner_user_id": "owner", "deleted_at": None},
        ],
        resources=[
            {"_id": "resource", "main_id": "tenant", "owner_user_id": "owner", "deleted_at": None},
        ],
    )
    monkeypatch.setattr(policy_module, "get_db", lambda: db)

    result = OpenSourceKnowledgeRetrievalAccessPolicy().filter_candidates(
        _items("org", "legacy", "personal"), main_id="tenant", user_id="owner",
    )

    assert [item["documentId"] for item in result] == ["org", "legacy", "personal"]
    assert result[0]["metadata"] == {
        "document_title": "员工手册",
        "knowledge_scope": "organization",
        "knowledge_label": "企业知识",
    }
    assert result[1]["metadata"]["document_title"] == "legacy.pdf"
    assert result[2]["metadata"] == {
        "document_title": "项目笔记",
        "knowledge_scope": "personal",
        "knowledge_label": "个人知识",
    }


def test_allows_active_share_but_rejects_revoked_share_and_outsider(monkeypatch):
    documents = [
        {"_id": "personal", "main_id": "tenant", "scope": "personal", "resource_id": "resource", "owner_user_id": "owner", "deleted_at": None},
    ]
    resources = [
        {"_id": "resource", "main_id": "tenant", "owner_user_id": "owner", "deleted_at": None},
    ]
    grants = [
        {"main_id": "tenant", "resource_type": "personal_knowledge", "resource_id": "resource", "recipient_user_id": "shared", "status": "active"},
        {"main_id": "tenant", "resource_type": "personal_knowledge", "resource_id": "resource", "recipient_user_id": "revoked", "status": "revoked"},
    ]
    monkeypatch.setattr(policy_module, "get_db", lambda: _Db(
        documents=documents, resources=resources, grants=grants,
    ))
    policy = OpenSourceKnowledgeRetrievalAccessPolicy()

    assert policy.filter_candidates(_items("personal"), main_id="tenant", user_id="shared")
    assert not policy.filter_candidates(_items("personal"), main_id="tenant", user_id="revoked")
    assert not policy.filter_candidates(_items("personal"), main_id="tenant", user_id="outsider")


def test_anonymous_retrieval_never_returns_personal_knowledge(monkeypatch):
    monkeypatch.setattr(policy_module, "get_db", lambda: _Db(documents=[
        {"_id": "org", "main_id": "tenant", "scope": "organization", "deleted_at": None},
        {"_id": "personal", "main_id": "tenant", "scope": "personal", "resource_id": "resource", "deleted_at": None},
    ]))

    result = OpenSourceKnowledgeRetrievalAccessPolicy().filter_candidates(
        _items("org", "personal"), main_id="tenant", user_id="",
    )

    assert [item["documentId"] for item in result] == ["org"]


def test_same_named_documents_keep_original_extension_in_citations(monkeypatch):
    monkeypatch.setattr(policy_module, "get_db", lambda: _Db(documents=[
        {"_id": "pdf", "main_id": "tenant", "name": "李煜最著名的十首词", "original_filename": "李煜最著名的十首词.pdf", "deleted_at": None},
        {"_id": "docx", "main_id": "tenant", "name": "李煜最著名的十首词", "original_filename": "李煜最著名的十首词.docx", "deleted_at": None},
    ]))
    result = OpenSourceKnowledgeRetrievalAccessPolicy().filter_candidates(
        _items("pdf", "docx"), main_id="tenant", user_id="",
    )
    assert [item["metadata"]["document_title"] for item in result] == [
        "李煜最著名的十首词.pdf", "李煜最著名的十首词.docx",
    ]
