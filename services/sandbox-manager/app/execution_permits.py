"""Opaque, heartbeat-backed leases for execution in remote DSH processes."""
from __future__ import annotations

from secrets import token_hex
from threading import Event, RLock
from time import monotonic


class ExecutionPermits:
    def __init__(self, scheduler, ttl=60, markers=None):
        self.scheduler = scheduler
        self.ttl = ttl
        self.markers = markers
        self._lock = RLock()
        self._entries = {}
        self._pending = {}
        self._cancelled = {}

    def acquire(self, owner: str, key: str, parent: str = '', *, ready=None, reserve=None) -> dict:
        identity = (owner, key)
        with self._lock:
            if identity in self._pending or any(entry['owner'] == owner and entry['key'] == f'native:{owner}:{key}' for entry in self._entries.values()):
                raise ValueError('Execution admission is already pending or active')
            if identity in self._cancelled:
                raise RuntimeError('Execution admission cancelled')
            cancel = Event()
            self._pending[identity] = cancel
        try:
            parent_key = self.parent_key(parent, owner) if parent else None
            context = self.scheduler.slot(f'native:{owner}:{key}', parent=parent_key, cancelled=cancel, ready=ready, reserve=reserve)
            context.__enter__()
            token = token_hex(32)
            with self._lock:
                if cancel.is_set():
                    context.__exit__(None, None, None)
                    raise RuntimeError('Execution admission cancelled')
                if self.markers:
                    try:
                        self.markers.add(token, owner)
                    except Exception:
                        context.__exit__(None, None, None)
                        raise
                self._entries[token] = dict(owner=owner, key=f'native:{owner}:{key}',
                                            context=context, touched=monotonic())
            return {'token': token, 'ttl_seconds': self.ttl}
        finally:
            with self._lock:
                self._pending.pop(identity, None)

    def cancel(self, owner: str, key: str):
        with self._lock:
            self._cancelled[(owner, key)] = monotonic()
            event = self._pending.get((owner, key))
            if event:
                event.set()
            tokens = [token for token, entry in self._entries.items()
                      if entry['owner'] == owner and entry['key'] == f'native:{owner}:{key}']
        self.scheduler.wake()
        for token in tokens:
            self.release(token, owner)

    def parent_key(self, token: str, owner: str | None = None) -> str:
        with self._lock:
            entry = self._entries.get(token)
            if entry is None or (owner is not None and entry['owner'] != owner):
                raise ValueError('Invalid execution permit')
            entry['touched'] = monotonic()
            return entry['key']

    def heartbeat(self, token: str, owner: str) -> dict:
        self.parent_key(token, owner)
        return {'ok': True}

    def release(self, token: str, owner: str | None = None):
        with self._lock:
            entry = self._entries.get(token)
            if entry is None:
                return
            if owner is not None and entry['owner'] != owner:
                raise ValueError('Invalid execution permit owner')
            if self.markers:
                self.markers.remove(token)
            self._entries.pop(token)
        entry['context'].__exit__(None, None, None)

    def release_owner(self, owner):
        with self._lock:
            tokens = [token for token, entry in self._entries.items() if entry['owner'] == owner]
        for token in tokens:
            self.release(token)

    def expire(self, on_expire=None):
        with self._lock:
            self._cancelled = {key: stamp for key, stamp in self._cancelled.items()
                               if monotonic() - stamp < self.ttl}
            tokens = [token for token, entry in self._entries.items()
                      if monotonic() - entry['touched'] >= self.ttl]
        for token in tokens:
            with self._lock:
                entry = self._entries.get(token)
            if entry is None:
                continue
            try:
                if on_expire:
                    on_expire(entry['owner'])
                self.release(token)
            except Exception:
                # Fail closed: keep capacity charged if the owner cannot be stopped.
                continue
