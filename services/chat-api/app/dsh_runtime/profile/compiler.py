"""Deterministic compiler from mutable admin rows to an immutable profile."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .catalog import ModelCatalog
from .models import RuntimeProfileSnapshot
from .tools import ToolProfileCompiler
from .skills import SkillProfileCompiler
from .plugins import MongoPluginCatalog, plugin_versions


class ModelProfileCompiler:
    def __init__(
        self,
        catalog: ModelCatalog,
        tool_compiler: ToolProfileCompiler | None = None,
        skill_compiler: SkillProfileCompiler | None = None,
        model_access_policy: Any | None = None,
        plugin_catalog: MongoPluginCatalog | None = None,
        agent_presentation_resolver: Any | None = None,
    ) -> None:
        self._catalog = catalog
        self._tool_compiler = tool_compiler
        self._skill_compiler = skill_compiler
        self._model_access_policy = model_access_policy
        self._plugin_catalog = plugin_catalog
        self._agent_presentation_resolver = agent_presentation_resolver

    async def compile(
        self,
        *,
        tenant_id: str,
        user_id: str = "",
        model_instance_id: str | None = None,
    ) -> RuntimeProfileSnapshot:
        authorized_model_id = model_instance_id
        if self._model_access_policy is not None and user_id:
            authorized_model_id = await self._model_access_policy.resolve_model_id(
                main_id=tenant_id,
                user_id=user_id,
                model_id=model_instance_id,
                capability="chat",
            )
        instance, provider = await self._catalog.resolve(tenant_id, authorized_model_id)
        self._validate(instance, provider, tenant_id)
        raw_capabilities = instance.get("capabilities", [])
        if isinstance(raw_capabilities, str):
            raw_capabilities = [raw_capabilities]
        capabilities = tuple(sorted({str(value) for value in raw_capabilities if str(value)}))
        tools = await self._tool_compiler.compile(tenant_id=tenant_id, user_id=user_id) if self._tool_compiler else ()
        skill_profile = await self._skill_compiler.compile(
            tenant_id=tenant_id, user_id=user_id, tools=tools,
        ) if self._skill_compiler else None
        plugins = await self._plugin_catalog.list_enabled(tenant_id, user_id) if self._plugin_catalog else ()
        presentation = await self._agent_presentation_resolver(tenant_id) if self._agent_presentation_resolver else None
        payload: dict[str, Any] = {
            "schema_version": "askai.runtime-profile.v1",
            "tenant_id": tenant_id,
            "subject_user_id": user_id,
            "model_source_tenant_id": str(instance.get("main_id")),
            "model_instance_id": str(instance.get("_id")),
            "provider_id": str(provider.get("_id")),
            "provider_type": str(provider.get("provider_type") or "openai_compatible"),
            "provider_name": str(provider.get("name") or provider.get("code") or "model-provider"),
            "model_name": str(instance.get("model_name") or "").strip(),
            "display_name": str(instance.get("display_name") or instance.get("model_name") or "").strip(),
            "capabilities": capabilities,
            "context_window": int(instance.get("max_context_tokens") or 0),
            "max_output_tokens": int((instance.get("settings") or {}).get("max_output_tokens") or 0),
            "tool_versions": tuple(item.version for item in tools),
            "tools": tuple(item.model_dump(mode="json") for item in tools),
            "skills": tuple(item.model_dump(mode="json") for item in (skill_profile.skills if skill_profile else ())),
            "writing_styles": tuple(item.model_dump(mode="json") for item in (skill_profile.writing_styles if skill_profile else ())),
            "skill_versions": tuple(item.version for item in (skill_profile.skills if skill_profile else ())),
            "workflow_versions": tuple(
                item.version for item in (skill_profile.skills if skill_profile else ()) if item.kind == "workflow"
            ),
        }
        if plugins:
            payload["plugins"] = plugins
            payload["plugin_versions"] = plugin_versions(plugins)
        if presentation:
            agent_name = str(presentation.get("name") or "").strip()
            if agent_name:
                payload["agent_name"] = agent_name[:80]
        content_hash = self.content_hash(payload)
        return RuntimeProfileSnapshot(
            **payload,
            content_hash=content_hash,
            profile_version=f"rp-{content_hash[:24]}",
        )

    @staticmethod
    def content_hash(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate(instance: dict[str, Any], provider: dict[str, Any], tenant_id: str) -> None:
        if str(instance.get("main_id")) != tenant_id:
            raise ValueError("cross-tenant model access is forbidden")
        if instance.get("status") != "active":
            raise ValueError("model instance is disabled")
        if provider.get("status", "active") != "active":
            raise ValueError("model provider is disabled")
        raw_capabilities = instance.get("capabilities", [])
        if isinstance(raw_capabilities, str):
            raw_capabilities = [raw_capabilities]
        capabilities = {str(value) for value in raw_capabilities}
        if not capabilities.intersection({"chat", "text"}):
            raise ValueError("model instance has no chat capability")
        if not str(instance.get("model_name") or "").strip():
            raise ValueError("model name is empty")
