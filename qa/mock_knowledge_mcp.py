"""Local MCP fixture for manually exercising external knowledge configuration.

Run: python3 qa/mock_knowledge_mcp.py
Use ``MOCK_KNOWLEDGE_ANSWER_FIELD=result`` to verify custom answer-field mapping.
Endpoint: http://127.0.0.1:8765/mcp
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
from urllib.parse import parse_qs, urlsplit


DOCUMENTS = {
    "/documents/leave": ("员工休假制度", "年假按员工司龄计算。"),
    "/documents/hr-update": ("人事政策补充说明", "未休年假依照补充政策办理。"),
}
BASE_URL = "http://127.0.0.1:8765"
ANSWER_FIELD = os.getenv("MOCK_KNOWLEDGE_ANSWER_FIELD", "answer")


def mock_answer(question: str) -> str:
    if "年假" in question or "休假" in question:
        return "[模拟数据] 年假按员工司龄计算，未休年假依照补充政策办理。示例文档没有提供天数档位，无法计算具体天数。"
    return "[模拟数据] 当前只有员工休假制度和人事政策补充说明两份示例文档，无法根据它们回答该问题。"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/marker":
            marker = parse_qs(parsed.query).get("marker", [""])[0]
            self._reply({"marker": marker, "length": len(marker), "source": "local-read-only-fixture"})
            return
        document = DOCUMENTS.get(self.path.split("?", 1)[0])
        if document is None:
            self.send_error(404)
            return
        title, excerpt = document
        body = (
            '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            f"<title>{escape(title)}</title><main><h1>{escape(title)}</h1>"
            f'<section id="annual"><h2>相关条款</h2><p>{escape(excerpt)}</p></section></main>'
            '</html>'
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/mcp":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        request = json.loads(self.rfile.read(length) or b"{}")
        method = request.get("method")
        if method == "initialize":
            # The MOVO client accepts a legacy stateless MCP endpoint.
            self._reply({"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32601, "message": "not implemented"}})
            return
        if method == "tools/list":
            result = {"tools": [{
                "name": "search_documents",
                "description": "Search the mock enterprise knowledge base",
                "inputSchema": {"type": "object", "properties": {
                    "query": {"type": "string", "description": "Search query"},
                }, "required": ["query"]},
                "outputSchema": {"type": "object", "properties": {
                    ANSWER_FIELD: {"type": "string"},
                    "summary": {"type": "string"},
                    "references": {"type": "array", "items": {"type": "object", "properties": {
                        "title": {"type": "string"}, "snippet": {"type": "string"},
                        "documentUrl": {"type": "string"},
                    }}},
                }},
                "annotations": {"readOnlyHint": True},
            }]}
        elif method == "tools/call":
            params = request.get("params") or {}
            arguments = params.get("arguments") or {}
            question = str(arguments.get("question") or arguments.get("query") or "")
            result = {"structuredContent": {
                ANSWER_FIELD: mock_answer(question),
                "summary": "示例资料：员工休假制度、人事政策补充说明。",
                "references": [
                    {"title": "员工休假制度", "snippet": "年假按员工司龄计算。", "documentUrl": f"{BASE_URL}/documents/leave"},
                    {"title": "人事政策补充说明", "snippet": "未休年假依照补充政策办理。", "documentUrl": f"{BASE_URL}/documents/hr-update"},
                ],
            }}
        else:
            self._reply({"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32601, "message": "unknown method"}})
            return
        self._reply({"jsonrpc": "2.0", "id": request.get("id"), "result": result})

    def _reply(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
