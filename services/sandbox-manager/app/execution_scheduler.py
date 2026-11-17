"""One admission budget shared by isolated startup and execution work."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Condition
from time import monotonic
from typing import Callable

from .settings_store import SettingsStore


@dataclass(eq=False)
class Admission:
    key: str
    parent: str | None
    ready: Callable[[set[str]], bool] | None
    reserve: Callable[[], None] | None


class ExecutionScheduler:
    def __init__(self, capacity: int, max_pending: int, store: SettingsStore):
        self._condition = Condition()
        self._store = store
        self._capacity = store.capacity(capacity)
        self._max_pending = store.max_pending(max_pending)
        self._active: set[str] = set()
        self._delegated: dict[str, str] = {}
        self._waiting: list[Admission] = []

    def _running(self):
        return len(self._active) - len(self._delegated)

    def status(self) -> dict:
        with self._condition:
            return dict(running=self._running(), pending=len(self._waiting),
                        capacity=self._capacity, max_pending=self._max_pending)

    def configure(self, *, capacity: int | None = None, max_pending: int | None = None) -> dict:
        if capacity is not None and (type(capacity) is not int or not 1 <= capacity <= 100):
            raise ValueError("Concurrency limit must be between 1 and 100")
        if max_pending is not None and (type(max_pending) is not int or not 0 <= max_pending <= 100):
            raise ValueError("Pending queue limit must be between 0 and 100")
        with self._condition:
            values = dict(capacity=self._capacity if capacity is None else capacity,
                          max_pending=self._max_pending if max_pending is None else max_pending)
            self._store.save(values)
            self._capacity, self._max_pending = values['capacity'], values['max_pending']
            self._condition.notify_all()
            return self.status()

    def wake(self):
        with self._condition:
            self._condition.notify_all()

    def _credit(self, entry):
        return entry.parent in self._active and entry.parent not in self._delegated.values()

    def _eligible(self, entry):
        return (entry.key not in self._active
                and (entry.parent is None or entry.parent in self._active)
                and (self._running() < self._capacity or self._credit(entry))
                and (entry.ready is None or entry.ready(set(self._active))))

    def _admit(self, entry):
        if entry.reserve:
            entry.reserve()
        if self._credit(entry):
            self._delegated[entry.key] = entry.parent
        self._active.add(entry.key)

    @contextmanager
    def slot(self, key: str, timeout: float = 20, *, parent: str | None = None,
             ready: Callable[[set[str]], bool] | None = None, cancelled=None, reserve=None):
        entry = Admission(key, parent, ready, reserve)
        started = monotonic()
        deadline = started + timeout
        with self._condition:
            if cancelled is not None and cancelled.is_set():
                raise RuntimeError("Execution admission cancelled")
            if parent is not None and parent not in self._active:
                raise RuntimeError("Execution delegation has expired")
            if not any(self._eligible(item) for item in self._waiting) and self._eligible(entry):
                self._admit(entry)
            else:
                if len(self._waiting) >= self._max_pending:
                    raise RuntimeError("Sandbox queue is full")
                self._waiting.append(entry)
                try:
                    while True:
                        if cancelled is not None and cancelled.is_set():
                            raise RuntimeError("Execution admission cancelled")
                        if parent is not None and parent not in self._active:
                            raise RuntimeError("Execution delegation has expired")
                        first = next((item for item in self._waiting if self._eligible(item)), None)
                        if first is entry:
                            self._waiting.remove(entry)
                            self._admit(entry)
                            self._condition.notify_all()
                            break
                        remaining = deadline - monotonic()
                        if remaining <= 0:
                            reason = "Resident capacity is full" if entry.ready and not entry.ready(set(self._active)) else "Sandbox queue wait timed out"
                            raise RuntimeError(reason)
                        self._condition.wait(remaining)
                except BaseException:
                    if entry in self._waiting:
                        self._waiting.remove(entry)
                    self._condition.notify_all()
                    raise
        admitted = monotonic()
        try:
            yield
        finally:
            with self._condition:
                self._active.remove(key)
                self._delegated.pop(key, None)
                # A cancelled parent must not make its still-running children free.
                for child, owner in list(self._delegated.items()):
                    if owner == key:
                        self._delegated.pop(child)
                self._condition.notify_all()
            logging.getLogger('uvicorn.error').info(
                'Sandbox admission wait_ms=%d occupied_ms=%d',
                int((admitted - started) * 1000), int((monotonic() - admitted) * 1000))
