from __future__ import annotations

import asyncio
import base64
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict

import httpx

LogHook = Callable[[str, Dict[str, Any]], None]


@dataclass(frozen=True)
class AzureGptImageGenerationResult:
    endpoint: str
    response: Dict[str, Any]
    image_bytes: bytes


@dataclass(frozen=True)
class AzureGptImageConfig:
    endpoint: str
    api_key: str
    deployment: str
    api_version: str = "2024-02-01"
    size: str = "1536x864"
    quality: str = "low"
    api_style: str = "v1"
    include_api_version: bool = False
    max_retries: int = 3
    retry_base_seconds: float = 1.5
    retry_max_seconds: float = 30.0
    connect_timeout: float = 30.0
    read_timeout: float = 600.0
    write_timeout: float = 600.0
    pool_timeout: float = 30.0
    keepalive_connections: int = 0
    max_connections: int = 2


class AzureGptImageClient:
    """Shared Azure GPT Image client.

    Generation request shape is intentionally aligned with the proven
    `tests/ppt_image_edit_poc/run_poc.py` A-image path.
    """

    def __init__(self, config: AzureGptImageConfig) -> None:
        self._config = config

    async def generate_image_async(
        self,
        prompt: str,
        *,
        log_hook: LogHook | None = None,
    ) -> AzureGptImageGenerationResult:
        return await asyncio.to_thread(self.generate_image, prompt, log_hook=log_hook)

    def generate_image(
        self,
        prompt: str,
        *,
        log_hook: LogHook | None = None,
    ) -> AzureGptImageGenerationResult:
        api_key = self._config.api_key.strip()
        if not api_key:
            raise RuntimeError("Azure image model API key is not configured")

        endpoint = self.image_generation_endpoint("generations")
        deployment = self._config.deployment.strip()
        if not deployment:
            raise RuntimeError("Azure image model deployment is not configured")
        size = self._config.size
        self.validate_image_size(size, deployment)

        payload = {
            "model": deployment,
            "prompt": prompt,
            "size": size,
            "n": 1,
            "quality": self._config.quality,
            "output_format": "png",
        }
        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
            "Connection": "close",
        }

        self._emit_log(
            log_hook,
            "image_generation_request",
            endpoint=endpoint,
            payload={
                "size": payload["size"],
                "n": payload["n"],
                "model": payload["model"],
                "quality": payload["quality"],
                "output_format": payload["output_format"],
                "prompt_chars": len(prompt),
                "prompt_preview": prompt[:500],
            },
        )
        self._emit_log(
            log_hook,
            "image_generation_http_config",
            timeout={
                "connect": self._config.connect_timeout,
                "read": self._config.read_timeout,
                "write": self._config.write_timeout,
                "pool": self._config.pool_timeout,
            },
            keepalive=self._config.keepalive_connections,
        )

        started = time.monotonic()
        try:
            resp = self._post_with_retry(
                endpoint,
                headers=headers,
                request_tag="image_generation",
                log_hook=log_hook,
                json_payload=payload,
            )
        except Exception as exc:
            self._emit_log(
                log_hook,
                "image_generation_exception",
                endpoint=endpoint,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                exception_type=type(exc).__name__,
                error=str(exc),
            )
            raise

        self._emit_log(
            log_hook,
            "image_generation_response",
            endpoint=endpoint,
            status_code=resp.status_code,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            content_type=resp.headers.get("content-type", ""),
            request_id=resp.headers.get("x-ms-request-id", "") or resp.headers.get("apim-request-id", ""),
            response_preview=(resp.text or "")[:1200],
        )

        if resp.status_code >= 400:
            raise RuntimeError(f"generation http_{resp.status_code}: {resp.text[:1200]}")

        data = resp.json()
        image_bytes = self._decode_image_response(data, log_hook=log_hook)
        return AzureGptImageGenerationResult(
            endpoint=endpoint,
            response=self.compact_response(data),
            image_bytes=image_bytes,
        )

    def image_generation_endpoint(self, path: str) -> str:
        endpoint = self._config.endpoint.strip().rstrip("/")
        if not endpoint:
            raise RuntimeError("Azure image model endpoint is not configured")
        deployment = self._config.deployment.strip()
        if not deployment:
            raise RuntimeError("Azure image model deployment is not configured")
        include_version_in_v1 = self._config.include_api_version
        style = self._config.api_style.strip().lower() or "v1"
        api_version = self._config.api_version
        if style == "v1":
            if include_version_in_v1:
                return f"{endpoint}/openai/v1/images/{path}?api-version={api_version}"
            return f"{endpoint}/openai/v1/images/{path}"
        return f"{endpoint}/openai/deployments/{deployment}/images/{path}?api-version={api_version}"

    @staticmethod
    def compact_response(data: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(data)
        items = []
        for item in out.get("data") or []:
            compact = dict(item)
            if compact.get("b64_json"):
                compact["b64_json"] = f"<base64:{len(compact['b64_json'])} chars>"
            if compact.get("url"):
                compact["url"] = str(compact["url"])[:240]
            items.append(compact)
        if items:
            out["data"] = items
        return out

    @staticmethod
    def validate_image_size(size: str, deployment: str) -> None:
        raw = str(size or "").strip().lower()
        if raw == "auto":
            return
        if not re.fullmatch(r"\d+x\d+", raw):
            raise ValueError(f"invalid image size '{size}', expected WIDTHxHEIGHT or auto")
        w, h = [int(x) for x in raw.split("x", 1)]
        model = str(deployment or "").lower()
        if "gpt-image-2" in model:
            pixels = w * h
            if w % 16 != 0 or h % 16 != 0:
                raise ValueError(f"gpt-image-2 size '{size}' must have width and height divisible by 16")
            if pixels < 65_536 or pixels > 4_194_304:
                raise ValueError(f"gpt-image-2 size '{size}' must be between 65,536 and 4,194,304 pixels")
            ratio = w / h
            if ratio < 0.5 or ratio > 2.0:
                raise ValueError(f"gpt-image-2 size '{size}' aspect ratio must be between 1:2 and 2:1")
            return
        allowed = {"1024x1024", "1024x1536", "1536x1024"}
        if raw not in allowed:
            raise ValueError(
                f"image size '{size}' is not in the common Azure GPT Image size set {sorted(allowed)} "
                f"for deployment '{deployment}'"
            )

    def _decode_image_response(
        self,
        data: Dict[str, Any],
        *,
        log_hook: LogHook | None = None,
    ) -> bytes:
        items = data.get("data") or []
        if not items:
            raise RuntimeError(f"image response has no data: {str(data)[:800]}")
        first = items[0]
        if first.get("b64_json"):
            image_bytes = base64.b64decode(first["b64_json"])
            self._emit_log(log_hook, "image_decode_b64_done", bytes=len(image_bytes))
            return image_bytes
        url = str(first.get("url") or "").strip()
        if not url:
            raise RuntimeError(f"image response has no b64_json/url: {str(data)[:800]}")
        started = time.monotonic()
        self._emit_log(log_hook, "image_download_start", url=url[:260])
        with httpx.Client(timeout=90, follow_redirects=True) as client:
            resp = client.get(url)
            self._emit_log(
                log_hook,
                "image_download_response",
                status_code=resp.status_code,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                content_type=resp.headers.get("content-type", ""),
                bytes=len(resp.content or b""),
            )
            resp.raise_for_status()
            return bytes(resp.content)

    def _post_with_retry(
        self,
        endpoint: str,
        *,
        headers: Dict[str, str],
        request_tag: str,
        log_hook: LogHook | None = None,
        json_payload: Dict[str, Any] | None = None,
    ) -> httpx.Response:
        max_retries = max(0, self._config.max_retries)
        max_attempts = max_retries + 1
        base_delay = max(0.2, self._config.retry_base_seconds)
        cap_delay = max(base_delay, self._config.retry_max_seconds)
        last_exc: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            started = time.monotonic()
            try:
                with httpx.Client(
                    timeout=self._image_http_timeout(),
                    limits=self._image_http_limits(),
                    follow_redirects=True,
                    http2=False,
                ) as client:
                    resp = client.post(endpoint, headers=headers, json=json_payload)
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError, httpx.TimeoutException) as exc:
                last_exc = exc
                retryable = attempt < max_attempts
                self._emit_log(
                    log_hook,
                    f"{request_tag}_transport_error",
                    endpoint=endpoint,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                    exception_type=type(exc).__name__,
                    error=str(exc),
                    retryable=retryable,
                )
                if not retryable:
                    raise
                delay = min(cap_delay, base_delay * (2 ** (attempt - 1)))
                delay = min(cap_delay, delay + random.uniform(0, delay * 0.25))
                self._emit_log(
                    log_hook,
                    f"{request_tag}_retry_sleep",
                    endpoint=endpoint,
                    attempt=attempt,
                    sleep_seconds=round(delay, 3),
                    reason="transport_error",
                )
                time.sleep(delay)
                continue

            if resp.status_code < 400:
                return resp
            if not self._should_retry_status(resp.status_code) or attempt >= max_attempts:
                return resp
            retry_after = self._parse_retry_after_seconds(resp)
            delay = retry_after if retry_after is not None else min(cap_delay, base_delay * (2 ** (attempt - 1)))
            delay = min(cap_delay, delay + random.uniform(0, max(0.05, delay * 0.25)))
            self._emit_log(
                log_hook,
                f"{request_tag}_retryable_status",
                endpoint=endpoint,
                attempt=attempt,
                max_attempts=max_attempts,
                status_code=resp.status_code,
                retry_after_seconds=retry_after,
                sleep_seconds=round(delay, 3),
                response_preview=(resp.text or "")[:500],
            )
            time.sleep(delay)

        if last_exc:
            raise last_exc
        raise RuntimeError(f"{request_tag} failed without response")

    def _image_http_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self._config.connect_timeout,
            read=self._config.read_timeout,
            write=self._config.write_timeout,
            pool=self._config.pool_timeout,
        )

    def _image_http_limits(self) -> httpx.Limits:
        keepalive = max(0, self._config.keepalive_connections)
        connections = max(1, self._config.max_connections)
        return httpx.Limits(max_keepalive_connections=keepalive, max_connections=connections)

    @staticmethod
    def _parse_retry_after_seconds(resp: httpx.Response) -> float | None:
        for key in ("retry-after-ms", "x-ms-retry-after-ms"):
            raw_ms = str(resp.headers.get(key, "")).strip()
            if raw_ms:
                try:
                    return max(0.0, float(raw_ms) / 1000.0)
                except Exception:
                    pass
        raw = str(resp.headers.get("retry-after", "")).strip()
        if not raw:
            return None
        try:
            return max(0.0, float(raw))
        except Exception:
            return None

    @staticmethod
    def _should_retry_status(code: int) -> bool:
        return code in {408, 409, 425, 429, 500, 502, 503, 504}

    @staticmethod
    def _emit_log(log_hook: LogHook | None, event: str, **payload: Any) -> None:
        if log_hook:
            log_hook(event, payload)
