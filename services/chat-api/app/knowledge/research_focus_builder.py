from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


class ResearchFocusBuilder:
    def __init__(self, config_path: Path | None = None) -> None:
        path = config_path or (Path(__file__).resolve().parent / "config" / "modes.yaml")
        self._modes: Dict[str, Dict[str, Any]] = {}
        self._load(path)

    def _load(self, path: Path) -> None:
        if not path.exists():
            self._modes = {}
            return
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        self._modes = dict(raw.get("modes") or {})

    def build(
        self,
        *,
        selected_mode: str,
        evidence_mode: str,
        hard_constraints: Dict[str, Any] | None = None,
        topic: str = "",
    ) -> Dict[str, Any]:
        mode = str(selected_mode or "report").strip().lower()
        conf = dict(self._modes.get(mode) or self._modes.get("report") or {})
        templates = [str(x) for x in list(conf.get("query_templates") or []) if str(x)]
        q = [t.replace("{topic}", topic or "") for t in templates]
        if evidence_mode == "none":
            q = []
        return {
            "mode": mode,
            "evidence_mode": evidence_mode,
            "query_templates": q,
            "source_priority": list(conf.get("source_priority") or []),
            "evidence_schema": list(conf.get("evidence_schema") or []),
            "hard_constraints": dict(hard_constraints or {}),
        }

