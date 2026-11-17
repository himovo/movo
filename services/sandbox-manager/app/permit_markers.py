"""Durable owner markers let restart recovery stop unknown in-flight work."""
import json
import os
from pathlib import Path
from uuid import uuid4


class PermitMarkers:
    def __init__(self, root: Path):
        self.root = root / 'execution-permits'

    def add(self, token, owner):
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / f'.{uuid4().hex}.tmp'
        try:
            with temporary.open('x', encoding='utf-8') as stream:
                os.chmod(temporary, 0o600)
                json.dump({'owner': owner}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.root / token)
        finally:
            temporary.unlink(missing_ok=True)

    def remove(self, token):
        (self.root / token).unlink(missing_ok=True)

    def recover(self, stop_owner):
        if not self.root.exists():
            return
        owners = {}
        for path in self.root.iterdir():
            if path.name.startswith('.'):
                continue
            owners.setdefault(json.loads(path.read_text())['owner'], []).append(path)
        errors = []
        for owner, paths in owners.items():
            try:
                stop_owner(owner)
            except Exception as exc:
                errors.append(exc)
                continue
            for path in paths:
                path.unlink(missing_ok=True)
        if errors:
            raise RuntimeError("Interrupted execution recovery failed") from errors[0]
