from __future__ import annotations

from typing import Any, Dict, Tuple

import yaml


def parse_skill_md(markdown: str) -> Dict[str, Any]:
    meta, body = split_frontmatter(markdown)
    out: Dict[str, Any] = {
        "skill_id": str(meta.get("skill_id") or meta.get("name") or "").strip(),
        "version": str(meta.get("version") or "1.0.0"),
        "default_mode": str(meta.get("default_mode") or "report").strip().lower(),
        "required_sections": list(meta.get("required_sections") or []),
        "evidence_policy": dict(meta.get("evidence_policy") or {}),
        "output_policy": dict(meta.get("output_policy") or {}),
        "validator_rules": dict(meta.get("validator_rules") or {}),
        "raw_body": body,
    }
    if not out["skill_id"]:
        out["skill_id"] = "unknown_skill"
    return out


def split_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    text = str(content or "")
    if not text.startswith("---"):
        return {}, text
    parts = text.split("\n")
    end_idx = None
    for i in range(1, len(parts)):
        if parts[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, text
    front = "\n".join(parts[1:end_idx])
    body = "\n".join(parts[end_idx + 1 :]).lstrip()
    try:
        meta = yaml.safe_load(front) or {}
        if not isinstance(meta, dict):
            meta = {}
    except Exception:
        meta = {}
    return meta, body

