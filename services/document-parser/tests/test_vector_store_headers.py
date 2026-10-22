from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import TestCase, mock

from app.services.vector_store import WeaviateVectorStore


class _RecordingHandler(BaseHTTPRequestHandler):
    seen_headers: list[dict[str, str]] = []

    def do_GET(self) -> None:  # noqa: N802
        type(self).seen_headers.append(dict(self.headers))
        body = json.dumps({"class": "AskAIKnowledgeChunks"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        pass


class WeaviateIntegrationHeaderTests(TestCase):
    def setUp(self) -> None:
        _RecordingHandler.seen_headers = []
        self.server = HTTPServer(("127.0.0.1", 0), _RecordingHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _sent_headers(self, api_key: str = "") -> dict[str, str]:
        WeaviateVectorStore({"endpoint": self.endpoint, "apiKey": api_key}).ensure_schema()
        return _RecordingHandler.seen_headers[-1]

    def test_sends_release_version(self) -> None:
        with mock.patch.dict(os.environ, {"MOVO_VERSION": "v0.1.15"}):
            headers = self._sent_headers()
        self.assertEqual(headers["X-Weaviate-Client-Integration"], "movo/v0.1.15")

    def test_falls_back_to_unknown_version(self) -> None:
        with mock.patch.dict(os.environ, {"MOVO_VERSION": ""}):
            headers = self._sent_headers()
        self.assertEqual(headers["X-Weaviate-Client-Integration"], "movo/unknown")

    def test_keeps_authorization_header(self) -> None:
        headers = self._sent_headers(api_key="secret")
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertIn("X-Weaviate-Client-Integration", headers)
