from __future__ import annotations

import json
from typing import Any, Dict, List

from app.llm.types import Message, Role
from pydantic import BaseModel, Field

from app.llm.factory import get_request_scoped_llm_client
from app.enterprise_capabilities.content.profile_presets.contracts import ComposeProfile, ProfilePreset


class _ConflictExtract(BaseModel):
    hard_conflicts: List[str] = Field(default_factory=list)
    soft_conflicts: List[str] = Field(default_factory=list)


class PresetConflictChecker:
    def __init__(self) -> None:
        self._llm = get_request_scoped_llm_client(streaming=False, stage="planning")

    async def check(self, *, compose_profile: ComposeProfile, preset: ProfilePreset) -> Dict[str, List[str]]:
        payload = {"compose_profile": compose_profile.model_dump(), "preset": preset.model_dump()}
        system = (
            "You are a preset conflict checker. Compare compose_profile and preset. "
            "Return strict JSON with hard_conflicts and soft_conflicts. "
            "Hard conflict means incompatible with user intent or hard constraints."
        )
        try:
            model = self._llm.with_structured_output(_ConflictExtract, method="function_calling")
            res = await model.ainvoke(
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False, default=str)),
                ]
            )
            if isinstance(res, _ConflictExtract):
                return {
                    "hard_conflicts": [str(x) for x in res.hard_conflicts if str(x).strip()],
                    "soft_conflicts": [str(x) for x in res.soft_conflicts if str(x).strip()],
                }
        except Exception:
            pass
        return {"hard_conflicts": [], "soft_conflicts": []}
