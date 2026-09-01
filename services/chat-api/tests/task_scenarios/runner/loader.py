from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ScenarioCase:
    scenario_id: str
    prompt: str
    output_spec: dict[str, Any] = field(default_factory=dict)
    fixtures: dict[str, Any] = field(default_factory=dict)
    expect: dict[str, Any] = field(default_factory=dict)


def load_scenario(path: str | Path) -> ScenarioCase:
    scenario_path = Path(path)
    payload = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"scenario must be a mapping: {scenario_path}")

    scenario_id = str(payload.get("id") or "").strip()
    prompt = str(payload.get("prompt") or "").strip()
    if not scenario_id:
        raise ValueError(f"scenario id is required: {scenario_path}")
    if not prompt:
        raise ValueError(f"scenario prompt is required: {scenario_path}")

    return ScenarioCase(
        scenario_id=scenario_id,
        prompt=prompt,
        output_spec=dict(payload.get("output_spec") or {}),
        fixtures=dict(payload.get("fixtures") or {}),
        expect=dict(payload.get("expect") or {}),
    )
