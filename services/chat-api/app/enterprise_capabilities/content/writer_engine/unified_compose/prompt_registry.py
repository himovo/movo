from __future__ import annotations

from pathlib import Path
from typing import Dict

import yaml


class PromptRegistry:
    def __init__(self) -> None:
        self._root = Path(__file__).resolve().parents[3] / "runtime" / "prompts" / "unified_compose"
        self._cache: Dict[str, str] = {}

    def get(self, name: str, **kwargs: str) -> str:
        template = self._cache.get(name)
        if template is None:
            path = self._root / f"{name}.yaml"
            if not path.exists():
                raise FileNotFoundError(f"Prompt template not found: {path}")
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            template = str(data.get("system") or "").strip()
            self._cache[name] = template
        return template.format(**kwargs)
