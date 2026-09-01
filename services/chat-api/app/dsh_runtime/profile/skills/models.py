"""Secret-free immutable Skill values embedded in a Runtime Profile."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DshSkillDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,126}[a-z0-9]$|^[a-z0-9]$")
    version: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=256)
    source_scope: Literal["personal", "organization"]
    kind: Literal["ordinary", "workflow"]
    description: str = Field(min_length=1, max_length=2000)
    when_to_use: str = Field(default="", max_length=4000)
    content: str = Field(min_length=1, max_length=100_000)
    capability_refs: tuple[str, ...] = ()


class WritingStyleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str = Field(pattern=r"^style-[0-9a-f]{24}$")
    version: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=256)
    source_scope: Literal["personal", "organization"]
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=2000)
    instructions: str = Field(min_length=1, max_length=50_000)


class CompiledSkillProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    skills: tuple[DshSkillDefinition, ...] = ()
    writing_styles: tuple[WritingStyleDefinition, ...] = ()

