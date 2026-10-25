from __future__ import annotations

import asyncio

from app.knowledge.retrieval import retrieval_client as module


def test_cross_knowledge_base_merge_uses_relevance_not_match_type(monkeypatch):
    class Response:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def post(self, _url, *, json, **_kwargs):
            if json["knowledgeBaseId"] == "first":
                return Response({"items": [{"documentId": "semantic", "chunkId": "a", "score": 9.0}]})
            return Response({"items": [{"documentId": "exact", "chunkId": "b", "score": 1.0,
                                        "matchType": "exact_identifier"}]})

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **_: Client())
    client = object.__new__(module.KnowledgeRetrievalClient)
    client.base_url = "http://test"
    client.service_token = "token"
    client.timeout = 1
    result = asyncio.run(client.search(query="PX2024001", main_id="tenant", knowledge_base_ids=["first", "second"], top_n=1))
    assert [item.chunkId for item in result.items] == ["a"]


def test_retrieval_mode_is_controlled_by_processing_service_config(monkeypatch):
    seen = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"retrievalMode": "hybrid", "items": []}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def post(self, _url, *, json, **_kwargs):
            seen.append(json)
            return Response()

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **_: Client())
    client = object.__new__(module.KnowledgeRetrievalClient)
    client.base_url = "http://test"
    client.service_token = "token"
    client.timeout = 1
    result = asyncio.run(client.search(query="考勤职责", main_id="tenant", knowledge_base_ids=["kb"]))
    assert seen[0]["retrievalMode"] is None
    assert result.retrievalMode == "hybrid"
