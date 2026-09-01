"""Secret-free immutable Runtime Profile values."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .tools import ToolProfileDefinition
from .skills.models import DshSkillDefinition, WritingStyleDefinition


class RuntimeProfileSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["askai.runtime-profile.v1"] = "askai.runtime-profile.v1"
    profile_version: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    tenant_id: str = Field(min_length=1, max_length=256)
    subject_user_id: str = Field(default="", max_length=256)
    model_source_tenant_id: str = Field(min_length=1, max_length=256)
    model_instance_id: str = Field(min_length=1, max_length=256)
    provider_id: str = Field(min_length=1, max_length=256)
    provider_type: str = Field(min_length=1, max_length=128)
    provider_name: str = Field(min_length=1, max_length=256)
    model_name: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=256)
    capabilities: tuple[str, ...]
    context_window: int = Field(default=0, ge=0)
    max_output_tokens: int = Field(default=0, ge=0)
    tool_versions: tuple[str, ...] = ()
    tools: tuple[ToolProfileDefinition, ...] = ()
    skills: tuple[DshSkillDefinition, ...] = ()
    writing_styles: tuple[WritingStyleDefinition, ...] = ()
    skill_versions: tuple[str, ...] = ()
    workflow_versions: tuple[str, ...] = ()
    plugin_versions: tuple[str, ...] = ()

    def host_payload(
        self,
        *,
        gateway_url: str,
        access_token: str,
        tool_gateway_url: str = "",
        tool_access_token: str = "",
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "profileVersion": self.profile_version,
            "modelInstanceId": self.model_instance_id,
            "modelName": self.model_name,
            "displayName": self.display_name,
            "contextWindow": self.context_window,
            "maxOutputTokens": self.max_output_tokens,
            "gatewayUrl": gateway_url,
            "accessToken": access_token,
        }
        if self.tools:
            native_replacements = [
                tool.name for tool in self.tools if tool.name == "external_search"
            ]
            payload["toolProfile"] = {
                "gatewayUrl": tool_gateway_url,
                "accessToken": tool_access_token,
                "tools": [tool.model_dump(mode="json") for tool in self.tools],
                "nativeReplacements": native_replacements,
            }
        if self.skills or self.writing_styles:
            payload["skillProfile"] = {
                "skills": [skill.model_dump(mode="json") for skill in self.skills],
                "writingStyles": [style.model_dump(mode="json") for style in self.writing_styles],
            }
        return payload
