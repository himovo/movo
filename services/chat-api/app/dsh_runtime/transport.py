"""HTTP transport used by ASKAI to call the Node DSH Runtime Host."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
import json as jsonlib
from typing import Any, Protocol

import httpx

from .errors import DshProtocolError, DshTransportError


class KernelHostTransport(Protocol):
    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def stream(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]: ...


class HttpKernelHostTransport:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 10.0,
        access_token: str = "",
    ) -> None:
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else None
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            headers=headers,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path, json=json, params=params)
        except httpx.HTTPError as exc:
            raise DshTransportError(f"DSH Runtime Host is unavailable: {exc}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise DshProtocolError("DSH Runtime Host returned non-JSON data") from exc
        if not isinstance(payload, dict):
            raise DshProtocolError("DSH Runtime Host returned a non-object response")
        if response.is_error:
            error = payload.get("error")
            message = error.get("message") if isinstance(error, dict) else response.reason_phrase
            raise DshTransportError(f"DSH Runtime Host rejected the request: {message}")
        return payload

    async def stream(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        try:
            async with self._client.stream(method, path, params=params) as response:
                if response.is_error:
                    body = await response.aread()
                    try:
                        payload = jsonlib.loads(body)
                    except (TypeError, ValueError):
                        payload = {}
                    error = payload.get("error") if isinstance(payload, dict) else None
                    message = error.get("message") if isinstance(error, dict) else response.reason_phrase
                    raise DshTransportError(f"DSH Runtime Host rejected the stream: {message}")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        payload = jsonlib.loads(line)
                    except ValueError as exc:
                        raise DshProtocolError("DSH Runtime Host returned malformed stream data") from exc
                    if not isinstance(payload, dict):
                        raise DshProtocolError("DSH Runtime Host streamed a non-object event")
                    yield payload
        except DshProtocolError:
            raise
        except DshTransportError:
            raise
        except httpx.HTTPError as exc:
            raise DshTransportError(f"DSH Runtime Host stream is unavailable: {exc}") from exc

    async def close(self) -> None:
        await self._client.aclose()
