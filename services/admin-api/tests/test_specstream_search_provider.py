from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import setup
from app.services import external_search_provider


def test_specstream_provider_test_posts_fast_search_and_parses_sources() -> None:
    received: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(length).decode("utf-8")
            received.append(
                {
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                    "content_type": self.headers.get("Content-Type"),
                    "body": json.loads(body),
                }
            )
            payload = {
                "data": {
                    "sources": [
                        {
                            "title": "MOVO Docs",
                            "url": "https://example.com/movo",
                            "snippet": "Enterprise agent platform.",
                        },
                        {
                            "title": "Second Result",
                            "url": "https://example.com/two",
                            "snippet": "Another snippet.",
                        },
                    ]
                }
            }
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}/v1/web-search"
        config = external_search_provider.normalized_config("specstream", api_key="test-secret", endpoint=endpoint)
        rows = asyncio.run(external_search_provider.test_provider("specstream", config, "MOVO"))
    finally:
        server.shutdown()
        server.server_close()

    assert len(received) == 1
    assert received[0]["path"] == "/v1/web-search"
    assert received[0]["authorization"] == "Bearer test-secret"
    assert received[0]["content_type"] == "application/json"
    assert received[0]["body"] == {"q": "MOVO", "num": 3, "speed": "fast"}
    assert rows == [
        {
            "title": "MOVO Docs",
            "url": "https://example.com/movo",
            "snippet": "Enterprise agent platform.",
        },
        {
            "title": "Second Result",
            "url": "https://example.com/two",
            "snippet": "Another snippet.",
        },
    ]


def test_setup_search_test_and_init_accept_specstream(monkeypatch) -> None:
    received = []

    async def ensure_open() -> None:
        pass

    async def fake_test_search(payload):
        received.append(payload)
        return [{"title": "Example", "url": "https://example.com", "snippet": "Snippet"}]

    monkeypatch.setattr(setup, "_ensure_setup_open", ensure_open)
    monkeypatch.setattr(setup, "test_setup_search", fake_test_search)

    app = FastAPI()
    app.include_router(setup.router, prefix="/setup")
    payload = {
        "provider": "specstream",
        "apiKey": "test-secret",
        "endpoint": "https://api.specstream.ai/v1/web-search",
        "query": "test",
    }
    with TestClient(app) as client:
        response = client.post("/setup/search/test", json=payload)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert received[0]["provider"] == "specstream"
    assert received[0]["endpoint"] == payload["endpoint"]

    init_request = setup.SetupInitRequest(
        orgName="Test Organization",
        adminUsername="admin",
        adminPassword="test-password-only",
        employeeUsername="employee",
        employeePassword="test-password-only",
        employeeName="Test User",
        orgTotalTokens=1000,
        defaultUserTokens=100,
        model={
            "providerId": "test",
            "displayName": "Test Model",
            "modelName": "test-model",
            "baseUrl": "https://example.com/v1",
            "apiKey": "test-secret",
        },
        externalSearch={"provider": "specstream", "apiKey": "test-secret"},
    )
    assert init_request.externalSearch is not None
    assert init_request.externalSearch.provider == "specstream"
