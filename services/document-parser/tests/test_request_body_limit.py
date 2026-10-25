from __future__ import annotations

import asyncio
from unittest import TestCase

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.request_body_limit import RequestBodyLimitMiddleware


class RequestBodyLimitTests(TestCase):
    def test_accepts_body_within_limit(self) -> None:
        app = FastAPI()
        app.add_middleware(RequestBodyLimitMiddleware, max_bytes=4)

        @app.post("/echo")
        async def echo(payload: dict) -> dict:
            return payload

        with TestClient(app) as client:
            response = client.post("/echo", content=b"{}", headers={"content-type": "application/json"})
        self.assertEqual(200, response.status_code)
        self.assertEqual({}, response.json())

    def test_rejects_declared_oversize_body_before_app_runs(self) -> None:
        calls = 0

        async def app(scope, receive, send) -> None:
            nonlocal calls
            calls += 1

        middleware = RequestBodyLimitMiddleware(app, max_bytes=4)
        messages: list[dict] = []

        async def receive() -> dict:
            raise AssertionError("oversize body should not be read")

        async def send(message: dict) -> None:
            messages.append(message)

        asyncio.run(
            middleware(
                {"type": "http", "headers": [(b"content-length", b"5")]},
                receive,
                send,
            )
        )
        self.assertEqual(0, calls)
        self.assertEqual(413, messages[0]["status"])

    def test_fastapi_rejects_oversize_stream_without_content_length(self) -> None:
        app = FastAPI()
        app.add_middleware(RequestBodyLimitMiddleware, max_bytes=4)

        @app.post("/echo")
        async def echo(payload: dict) -> dict:
            return payload

        with TestClient(app) as client:
            response = client.post(
                "/echo",
                content=(chunk for chunk in (b"123", b"45")),
                headers={"transfer-encoding": "chunked", "content-type": "application/json"},
            )
        self.assertEqual(413, response.status_code)

    def test_rejects_chunked_body_without_content_length(self) -> None:
        async def app(scope, receive, send) -> None:
            while True:
                message = await receive()
                if not message.get("more_body", False):
                    break
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        chunks = iter(
            [
                {"type": "http.request", "body": b"123", "more_body": True},
                {"type": "http.request", "body": b"45", "more_body": False},
            ]
        )
        messages: list[dict] = []

        async def receive() -> dict:
            return next(chunks)

        async def send(message: dict) -> None:
            messages.append(message)

        asyncio.run(
            RequestBodyLimitMiddleware(app, max_bytes=4)(
                {"type": "http", "headers": []}, receive, send
            )
        )
        self.assertEqual(413, messages[0]["status"])

    def test_chunked_body_is_accepted_at_limit(self) -> None:
        async def app(scope, receive, send) -> None:
            while True:
                message = await receive()
                if not message.get("more_body", False):
                    break
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        chunks = iter(
            [
                {"type": "http.request", "body": b"12", "more_body": True},
                {"type": "http.request", "body": b"34", "more_body": False},
            ]
        )
        messages: list[dict] = []

        async def receive() -> dict:
            return next(chunks)

        async def send(message: dict) -> None:
            messages.append(message)

        asyncio.run(
            RequestBodyLimitMiddleware(app, max_bytes=4)(
                {"type": "http", "headers": []}, receive, send
            )
        )
        self.assertEqual(200, messages[0]["status"])
