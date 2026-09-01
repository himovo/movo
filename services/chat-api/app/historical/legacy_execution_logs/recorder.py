"""Protocol-neutral buffered persistence for execution streams."""
from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.infrastructure.observability.config import log_print
from .store import ExecutionEventStore


# Keys that commonly carry base64-encoded image / binary blobs. These are
# externalised to OSS at flush time so the Mongo document stays small AND
# the screenshots survive for history replay.
_HEAVY_KEYS = {"screenshot", "image", "images"}
_HEAVY_MIN_LEN = 2000


def _strip_heavy_blobs(obj: Any) -> None:
    """Recursively replace heavy base64 values with a short placeholder.

    Fallback path for when OSS upload isn't possible (missing credentials,
    upload error). Browser-heavy tasks would otherwise blow past MongoDB's
    16MB document limit.
    """
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            v = obj[k]
            if k in _HEAVY_KEYS and isinstance(v, str) and len(v) > _HEAVY_MIN_LEN:
                obj[k] = f"<stripped:{len(v)}B>"
            elif isinstance(v, (dict, list)):
                _strip_heavy_blobs(v)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                _strip_heavy_blobs(item)


def _collect_heavy_blobs(obj: Any, out: List[Tuple[Any, Any, str]]) -> None:
    """Walk obj and collect (parent_container, key_or_index, base64_value).

    Only plucks str values under _HEAVY_KEYS whose length exceeds the
    threshold — small inline URLs or stripped placeholders are left alone.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _HEAVY_KEYS and isinstance(v, str) and len(v) > _HEAVY_MIN_LEN:
                out.append((obj, k, v))
            elif isinstance(v, (dict, list)):
                _collect_heavy_blobs(v, out)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            if isinstance(item, str) and len(item) > _HEAVY_MIN_LEN:
                # Rare: images field is sometimes a list of data URIs.
                out.append((obj, idx, item))
            elif isinstance(item, (dict, list)):
                _collect_heavy_blobs(item, out)


def _decode_base64_payload(value: str) -> Tuple[bytes, str]:
    """Return (raw_bytes, mime). Handles both ``data:image/png;base64,AAA``
    and bare base64 payloads. Falls back to image/png if mime is unknown."""
    mime = "image/png"
    payload = value
    if value.startswith("data:"):
        header, _, payload = value.partition(",")
        # header == "data:image/png;base64"
        spec = header[5:]
        if ";" in spec:
            spec = spec.split(";", 1)[0]
        if spec:
            mime = spec
    raw = base64.b64decode(payload, validate=False)
    return raw, mime


class BaseStreamRecorder:
    def __init__(
        self,
        store: ExecutionEventStore,
        session_id: str,
        message_id: str,
        *,
        user_id: Optional[str] = None,
        main_id: Optional[str] = None,
        batch_size: int = 25,
        flush_interval: float = 1.5,
        compact_fn: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
        summary_fn: Callable[[List[Dict[str, Any]]], Dict[str, Any]],
    ) -> None:
        self._store = store
        self._session_id = session_id
        self._message_id = message_id
        self._user_id = user_id
        self._main_id = main_id
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._compact_fn = compact_fn
        self._summary_fn = summary_fn
        self._buffer: List[Dict[str, Any]] = []
        self._last_flush = time.monotonic()
        self._lock = asyncio.Lock()
        self._closed = False
        self._flush_tasks: set[asyncio.Task[Any]] = set()
        # Lazy: constructed on first flush that actually has a heavy blob;
        # None while idle; False if construction fails (OSS not configured) —
        # avoids retrying per-batch.
        self._uploader: Any = None
        self._uploader_checked = False

    # -- ingest -------------------------------------------------------------
    def observe_line(self, line: str) -> None:
        """Best-effort parse + enqueue; never raises.

        Screenshots stay as base64 in the buffer and are externalised to
        OSS in the flush path so history replay can re-sign them. Live
        SSE preview is unaffected because this function runs AFTER the
        line has been yielded to the client.
        """
        try:
            data = json.loads(line)
            if isinstance(data, dict) and "type" in data:
                self._buffer.append(data)
        except Exception:
            return
        # Trigger an async flush if conditions met (fire-and-forget).
        if (
            len(self._buffer) >= self._batch_size
            or (time.monotonic() - self._last_flush) >= self._flush_interval
        ):
            task = asyncio.create_task(self._flush_if_needed())
            self._flush_tasks.add(task)
            task.add_done_callback(self._flush_tasks.discard)

    # -- internal flush -----------------------------------------------------
    def _get_uploader(self) -> Any:
        if self._uploader_checked:
            return self._uploader or None
        self._uploader_checked = True
        try:
            from app.utils.oss_uploader import AliyunOSSUploader

            self._uploader = AliyunOSSUploader()
        except Exception as exc:
            log_print(f"[recorder] OSS uploader unavailable: {exc}", flush=True)
            self._uploader = False
        return self._uploader or None

    async def _externalize_heavy_blobs(self, batch: List[Dict[str, Any]]) -> None:
        """Upload every large screenshot/image blob in the batch to OSS and
        replace the base64 string with ``{"_oss_object_path", "mime"}``.

        If OSS is unavailable or any single upload fails, fall back to the
        short placeholder so the Mongo write still succeeds within 16MB.
        """
        targets: List[Tuple[Any, Any, str]] = []
        for ev in batch:
            _collect_heavy_blobs(ev, targets)
        if not targets:
            return
        uploader = self._get_uploader()
        if uploader is None:
            for parent, key, value in targets:
                parent[key] = f"<stripped:{len(value)}B>"
            return
        loop = asyncio.get_running_loop()
        user_id = str(self._user_id or "anonymous")

        async def _one(parent: Any, key: Any, value: str) -> None:
            try:
                raw, mime = _decode_base64_payload(value)
                ext = (mime.split("/", 1)[-1] or "png").lower().split("+", 1)[0]
                file_name = f"screenshot_{uuid.uuid4().hex}.{ext}"
                _url, object_path = await loop.run_in_executor(
                    None,
                    uploader.upload_bytes_with_path,
                    raw,
                    user_id,
                    file_name,
                    mime,
                )
                parent[key] = {"_oss_object_path": object_path, "mime": mime}
            except Exception as exc:
                log_print(f"[recorder] screenshot upload failed: {exc}", flush=True)
                parent[key] = f"<stripped:{len(value)}B>"

        await asyncio.gather(*(_one(p, k, v) for p, k, v in targets))

    async def _flush_if_needed(self) -> None:
        if self._closed:
            return
        async with self._lock:
            if not self._buffer:
                return
            batch = self._buffer
            self._buffer = []
            self._last_flush = time.monotonic()
        try:
            await self._externalize_heavy_blobs(batch)
            await self._store.append_events(
                self._session_id,
                self._message_id,
                batch,
                user_id=self._user_id,
                main_id=self._main_id,
            )
        except Exception as exc:
            # Externalize fell back to placeholders on its own errors; this
            # only fires on a Mongo append failure.
            log_print(f"[recorder] flush failed: {exc}", flush=True)

    # -- finalize -----------------------------------------------------------
    async def finalize(self, *, status: str = "completed") -> None:
        if self._closed:
            return
        # Wait for fire-and-forget batch flushes before draining the tail, so
        # compaction cannot race with a late append.
        pending_flushes = list(self._flush_tasks)
        if pending_flushes:
            await asyncio.gather(*pending_flushes, return_exceptions=True)
        # Drain remaining buffer.
        await self._flush_if_needed()
        self._closed = True
        # Compact stored events: collapse text deltas into text.done.
        try:
            events = await self._store.get_events_for_message(self._message_id)
            if events:
                compacted = self._compact_fn(events)
                if len(compacted) != len(events):
                    await self._store.replace_events(self._message_id, compacted)
                summary = self._summary_fn(compacted)
            else:
                summary = self._summary_fn([])
            await self._store.finalize(self._message_id, summary=summary, status=status)
        except Exception as exc:
            log_print(f"[recorder] finalize failed: {exc}", flush=True)

    @property
    def message_id(self) -> str:
        return self._message_id
