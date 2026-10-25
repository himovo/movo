from __future__ import annotations

from app.services import exact_identifier_retrieval as retrieval


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def limit(self, count):
        return iter(self.rows[:count])


class _Collection:
    def __init__(self, rows):
        self.rows = rows
        self.query = None

    def find(self, query):
        self.query = query
        return _Cursor([
            row for row in self.rows
            if row["main_id"] == query["main_id"]
            and row["chunk_stage"] == query["chunk_stage"]
            and ("knowledge_base_id" not in query or row["knowledge_base_id"] == query["knowledge_base_id"])
            and any(value in row["search_identifiers"] for value in query["search_identifiers"]["$in"])
        ])


class _Db:
    def __init__(self, rows):
        self.knowledge_document_chunks = _Collection(rows)


def test_exact_store_code_row_is_recovered_and_permission_filtered(monkeypatch):
    rows = [
        {"main_id": "tenant", "knowledge_base_id": "kb", "document_id": "allowed", "chunk_id": "row-1", "chunk_stage": "rag", "search_identifiers": ["GR0010213"], "contextual_text": "门店编号：GR0010213；一月收入：17017.7619047619", "text": "门店编号：GR0010213；一月收入：17017.7619047619"},
        {"main_id": "tenant", "knowledge_base_id": "kb", "document_id": "forbidden", "chunk_id": "row-2", "chunk_stage": "rag", "search_identifiers": ["GR0010213"], "contextual_text": "门店编号：GR0010213；机密", "text": "机密"},
    ]
    db = _Db(rows)
    monkeypatch.setattr(retrieval, "get_db", lambda: db)
    monkeypatch.setattr(retrieval.knowledge_retrieval_access_policy, "filter_candidates", lambda items, **_: [item for item in items if item["documentId"] == "allowed"])
    result = retrieval.exact_identifier_candidates("GR0010213 一到三月收入？", main_id="tenant", user_id="user", knowledge_base_id="kb")
    assert [item["chunkId"] for item in result] == ["row-1"]
    assert result[0]["score"] == 1.0
    assert db.knowledge_document_chunks.query["knowledge_base_id"] == "kb"


def test_identifier_extraction_uses_exact_token_boundaries():
    from app.services.chunk_identifiers import extract_identifiers
    assert extract_identifiers("GR0010213、GR00102130 GR0010213") == ["GR0010213", "GR00102130"]
    assert extract_identifiers("订单 AB-123456 与项目 PX2024001") == ["AB-123456", "PX2024001"]
    assert extract_identifiers("订单 12345678 与流程 AB12") == ["12345678", "AB12"]


def test_rag_chunk_carries_search_identifier_for_persistence():
    from app.services.rag_chunk_optimizer import build_rag_chunks
    chunks = build_rag_chunks([{"chunkId": "raw_1", "text": "门店编号：GR0010213；一月收入：17017", "contentType": "table_row"}])
    assert "GR0010213" in chunks[0]["searchIdentifiers"]
    assert "17017" in chunks[0]["searchIdentifiers"]


def test_identifier_index_uses_chunk_content_not_repeated_document_title():
    from app.services.rag_chunk_optimizer import build_rag_chunks
    chunks = build_rag_chunks([{
        "chunkId": "raw_1", "text": "这里讨论一般的费用条款", "contentType": "table_row",
        "titlePath": ["项目 PX2024001"],
    }])
    assert chunks[0]["searchIdentifiers"] == []


def test_exact_identifier_row_joins_semantic_results_without_excluding_them(monkeypatch):
    from app.domain.jobs import RetrievalSearchRequest
    from app.services import retrieval_service

    monkeypatch.setattr(retrieval_service, "_effective_config", lambda _: {"retrieval": {"topN": 8}})
    monkeypatch.setattr(retrieval_service, "embed_query", lambda *_: [0.1])
    monkeypatch.setattr(retrieval_service, "get_vector_store", lambda *_: object())
    monkeypatch.setattr(retrieval_service, "_search_authorized_candidates", lambda **_: [{"documentId": "other", "chunkId": "semantic", "score": 0.9}])
    monkeypatch.setattr(retrieval_service, "exact_identifier_candidates", lambda *_, **__: [{"documentId": "store", "chunkId": "row", "score": 1.0}])
    request = RetrievalSearchRequest(query="GR0010213 收入", mainId="tenant", userId="user")
    result = retrieval_service.search_knowledge(request)
    assert {item["chunkId"] for item in result["items"]} == {"row", "semantic"}


def test_denied_rows_do_not_crowd_out_later_authorized_exact_row(monkeypatch):
    rows = [
        {"main_id": "tenant", "knowledge_base_id": "kb", "document_id": "denied", "chunk_id": str(index),
         "chunk_stage": "rag", "search_identifiers": ["PX2024001"], "text": "denied"}
        for index in range(55)
    ] + [{"main_id": "tenant", "knowledge_base_id": "kb", "document_id": "allowed", "chunk_id": "answer",
          "chunk_stage": "rag", "search_identifiers": ["PX2024001"], "text": "matching clause"}]
    monkeypatch.setattr(retrieval, "get_db", lambda: _Db(rows))
    monkeypatch.setattr(retrieval.knowledge_retrieval_access_policy, "filter_candidates", lambda items, **_: [
        item for item in items if item["documentId"] == "allowed"
    ])
    result = retrieval.exact_identifier_candidates("PX2024001", main_id="tenant", user_id="user", knowledge_base_id="kb", limit=1)
    assert [item["chunkId"] for item in result] == ["answer"]
