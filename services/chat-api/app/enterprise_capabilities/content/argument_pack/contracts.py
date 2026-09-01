from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ArgumentItem(BaseModel):
    label: str = ""
    summary: str = ""
    sources: List[str] = Field(default_factory=list)


class ArgumentPackSpec(BaseModel):
    definitions: List[ArgumentItem] = Field(default_factory=list)
    boundaries: List[ArgumentItem] = Field(default_factory=list)
    use_cases: List[ArgumentItem] = Field(default_factory=list)
    relationships: List[ArgumentItem] = Field(default_factory=list)
    references: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
