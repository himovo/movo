"""Reference-counted task locks shared by execution and lifecycle operations."""
from contextlib import contextmanager
from threading import Lock, RLock


class TaskLocks:
    def __init__(self):
        self._guard = Lock()
        self._entries = {}

    @contextmanager
    def hold(self, key):
        with self._guard:
            lock, count = self._entries.get(key, (RLock(), 0))
            self._entries[key] = (lock, count + 1)
        try:
            with lock:
                yield
        finally:
            with self._guard:
                _, count = self._entries[key]
                if count == 1:
                    del self._entries[key]
                else:
                    self._entries[key] = (lock, count - 1)
