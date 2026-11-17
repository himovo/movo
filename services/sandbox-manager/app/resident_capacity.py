"""Shared resident accounting, independent of active execution permits."""
from threading import RLock


class ResidentCapacity:
    def __init__(self, limit):
        if limit < 1:
            raise ValueError('Resident container limit must be positive')
        self.limit = limit
        self._keys = set()
        self._lock = RLock()

    def available(self, key):
        with self._lock:
            return key in self._keys or len(self._keys) < self.limit

    def claim(self, key, *, restoring=False):
        with self._lock:
            if not restoring and key not in self._keys and len(self._keys) >= self.limit:
                raise RuntimeError('Resident container capacity is full')
            self._keys.add(key)

    def release(self, key):
        with self._lock:
            self._keys.discard(key)

    def status(self):
        with self._lock:
            return {'resident_capacity': self.limit, 'resident_containers': len(self._keys)}
