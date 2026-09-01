from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import yaml


@dataclass
class CatalogSkill:
    skill_id: str
    display_name: str
    aliases: List[str]
    default_mode: str


class SkillCatalog:
    def __init__(self, config_path: Path | None = None) -> None:
        path = config_path or (Path(__file__).resolve().parent / "config" / "skill_catalog.yaml")
        self._skills: List[CatalogSkill] = []
        self._load(path)

    def _load(self, path: Path) -> None:
        if not path.exists():
            self._skills = []
            return
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rows = list(raw.get("skills") or [])
        out: List[CatalogSkill] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("skill_id") or "").strip()
            if not sid:
                continue
            out.append(
                CatalogSkill(
                    skill_id=sid,
                    display_name=str(item.get("display_name") or sid),
                    aliases=[str(x).strip() for x in list(item.get("aliases") or []) if str(x).strip()],
                    default_mode=str(item.get("default_mode") or "report").strip().lower(),
                )
            )
        self._skills = out

    def retrieve_topk(self, text: str, k: int = 3) -> List[Tuple[CatalogSkill, float]]:
        q = str(text or "").lower()
        scored: List[Tuple[CatalogSkill, float]] = []
        for skill in self._skills:
            score = 0.0
            if skill.skill_id in q:
                score += 1.0
            for a in skill.aliases:
                low = a.lower()
                if low and low in q:
                    score += 1.2
            if skill.display_name.lower() in q:
                score += 0.8
            if score > 0:
                scored.append((skill, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[: max(1, int(k))]

