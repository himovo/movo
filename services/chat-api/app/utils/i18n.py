from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List


_BASE_DIR = Path(__file__).resolve().parent.parent
_I18N_PATH = _BASE_DIR / "i18n" / "strings.json"


@lru_cache(maxsize=1)
def _load() -> Dict[str, Dict[str, Any]]:
    if not _I18N_PATH.exists():
        return {"en": {}, "zh": {}}
    with _I18N_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return {"en": data.get("en", {}), "zh": data.get("zh", {})}


def get(key: str, language: str = "en", default: str | None = None) -> str:
    data = _load()
    lang = "zh" if language == "zh" else "en"
    return str(data.get(lang, {}).get(key, default if default is not None else key))


def get_list(key: str, language: str = "en") -> List[str]:
    data = _load()
    lang = "zh" if language == "zh" else "en"
    value = data.get(lang, {}).get(key, [])
    if isinstance(value, list):
        return [str(v) for v in value]
    if value is None:
        return []
    return [str(value)]


def get_dict(key: str, language: str = "en") -> Dict[str, Any]:
    data = _load()
    lang = "zh" if language == "zh" else "en"
    value = data.get(lang, {}).get(key, {})
    if isinstance(value, dict):
        return value
    return {}
