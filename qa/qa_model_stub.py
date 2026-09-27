#!/usr/bin/env python3
"""Credential-free OpenAI-compatible stub for the T12 QA stack.

Serves exactly the two routes the QA path needs:

* ``GET /healthz`` - 200 JSON. Polled by the pinned bounded wait loop.
* ``POST /v1/chat/completions`` - an SSE stream shaped for the OpenAI SDK
  (``openai==2.8.1`` in ``services/chat-api``): ``data:`` chunks each terminated
  by a blank line, every chunk carrying at least one non-empty ``choices``
  element, then a final ``data: [DONE]``.

``stream_options`` (the caller force-injects ``{"include_usage": true}``) and any
``tools`` / ``tool_choice`` body fields are tolerated and ignored. No network
access, no credentials, stdlib only.
"""

from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "0.0.0.0"
PORT = 8200
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
HEALTH_PATH = "/healthz"

# T12 lane B (disclosed minimal fix): the session-live endpoint polls every
# 1.0 s and only projects a turn while `active_run` exists, so an instant stub
# turn (<0.1 s) is invisible to every other member's stream. Pacing the content
# chunks keeps each turn ~4.5 s and makes the pinned step (9) proof reproducible.
# Wire contract unchanged: same chunks, blank-line boundaries, and [DONE].
SSE_CHUNK_DELAY_SECONDS = 1.5

# Every chunk carries a non-empty choices element. default_openai.py:191-197
# yields content only inside `if chunk.choices and len(chunk.choices) > 0`, so a
# chunk without choices would be silently dropped and the setup probe would
# "succeed" with no content (model_connectivity.py:60-68 falls back to a canned
# success message when response_text is empty).
SSE_CHUNKS: tuple[dict[str, object], ...] = (
    {"choices": [{"delta": {"role": "assistant", "content": "qa-stub "}}]},
    {"choices": [{"delta": {"content": "stream "}}]},
    {"choices": [{"delta": {"content": "ok"}}]},
)
DONE_EVENT = b"data: [DONE]\n\n"


class QAStubHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(f"qa-model-stub: {format % args}\n")

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == HEALTH_PATH:
            self._send_json(200, {"status": "ok", "service": "qa-model-stub"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != CHAT_COMPLETIONS_PATH:
            self._send_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            json.loads(raw or b"{}")
        except ValueError:
            self._send_json(400, {"error": "invalid json"})
            return
        self._stream_chat_completion()

    def _stream_chat_completion(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            for chunk in SSE_CHUNKS:
                event = json.dumps(chunk, separators=(",", ":")).encode("utf-8")
                self.wfile.write(b"data: " + event + b"\n\n")
                self.wfile.flush()
                time.sleep(SSE_CHUNK_DELAY_SECONDS)
            self.wfile.write(DONE_EVENT)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.log_message("client disconnected mid-stream")
        self.close_connection = True


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), QAStubHandler)
    print(f"qa-model-stub listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
