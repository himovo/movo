"""Compile ASKAI-managed HTTP and MCP tools into immutable DSH definitions."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.enterprise_capabilities.runtime import InternalCapabilityCatalog
from app.enterprise_capabilities.runtime.timeouts import MAX_CAPABILITY_EXECUTION_MS
from app.services.external_tools import external_tool_registry
from app.governance.position_policy import EmployeePolicyResolver


class ToolProfileDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,127}$")
    version: str = Field(min_length=1, max_length=128)
    source_type: str = Field(pattern=r"^(http|mcp|internal)$")
    capability_ref: str = Field(default="", max_length=256)
    external_tool_id: str = Field(min_length=1, max_length=256)
    mcp_tool_name: str = Field(default="", max_length=256)
    display_name: str = Field(default="", max_length=512)
    description: str = Field(min_length=1, max_length=4000)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    output_validation: str = Field(default="strict", pattern=r"^(none|strict)$")
    risk_level: str = Field(pattern=r"^(read|write|dangerous)$")
    approval_required: bool = False
    approval_argument: str = Field(default="", max_length=128)
    approval_values: tuple[str, ...] = ()
    required_scopes: tuple[str, ...] = ()
    timeout_ms: int = Field(default=15_000, ge=100, le=MAX_CAPABILITY_EXECUTION_MS)
    timeout_mode: Literal["fixed", "activity"] = "fixed"
    inactivity_timeout_ms: int = Field(default=0, ge=0, le=MAX_CAPABILITY_EXECUTION_MS)
    cancellable: bool = True
    idempotent: bool = True
    delivery_mode: Literal["model_synthesized", "authoritative_markdown"] = "model_synthesized"
    consumes_execution_evidence: bool = False

    @model_validator(mode="before")
    @classmethod
    def migrate_content_delivery_mode(cls, value: Any) -> Any:
        """Keep already-published content profiles safe after this contract upgrade."""
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        capability_ref = str(value.get("capability_ref") or "")
        if "delivery_mode" not in migrated and capability_ref == "content.produce@v1":
            migrated["delivery_mode"] = "authoritative_markdown"
        if "consumes_execution_evidence" not in migrated and capability_ref in {
            "content.produce@v1", "presentation.create@v1",
        }:
            migrated["consumes_execution_evidence"] = True
        return migrated


class ToolCatalog(Protocol):
    async def list_enabled(self, tenant_id: str, user_id: str) -> list[dict[str, Any]]: ...


class MongoToolCatalog:
    async def list_enabled(self, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        return await external_tool_registry.list_enabled_descriptors(tenant_id, user_id=user_id)


class ToolProfileCompiler:
    def __init__(self, catalog: ToolCatalog, internal_catalog: InternalCapabilityCatalog | None = None, policy_resolver: EmployeePolicyResolver | None = None) -> None:
        self._catalog = catalog
        self._internal_catalog = internal_catalog
        self._policy_resolver = policy_resolver

    async def compile(self, *, tenant_id: str, user_id: str) -> tuple[ToolProfileDefinition, ...]:
        rows = await self._catalog.list_enabled(tenant_id, user_id)
        policy = await self._policy_resolver.resolve(tenant_id, user_id) if self._policy_resolver else None
        if policy is not None:
            rows = [row for row in rows if policy.allows_external_tool(str(row.get("id") or ""))]
        definitions: list[ToolProfileDefinition] = []
        for row in rows:
            if str(row.get("type")) == "mcp":
                definitions.extend(self._compile_mcp(row))
            else:
                definitions.append(self._compile_http(row))
        if self._internal_catalog is not None:
            for capability in await self._internal_catalog.list_enabled(tenant_id, user_id):
                if policy is not None and not policy.allows_internal(capability.capability_ref):
                    continue
                definitions.append(ToolProfileDefinition(
                    name=capability.tool_name,
                    version=capability.version,
                    source_type="internal",
                    capability_ref=capability.capability_ref,
                    external_tool_id=capability.capability_ref,
                    display_name=capability.display_name,
                    description=capability.description,
                    input_schema=capability.input_schema,
                    output_schema=capability.output_schema,
                    output_validation=capability.output_validation,
                    risk_level=capability.risk_level,
                    approval_required=capability.approval_required,
                    approval_argument=capability.approval_argument,
                    approval_values=capability.approval_values,
                    required_scopes=capability.required_scopes,
                    timeout_ms=capability.timeout_ms,
                    timeout_mode=capability.timeout_mode,
                    inactivity_timeout_ms=capability.inactivity_timeout_ms,
                    cancellable=capability.cancellable,
                    idempotent=capability.idempotent,
                    delivery_mode=capability.delivery_mode,
                    consumes_execution_evidence=capability.consumes_execution_evidence,
                ))
        names = [item.name for item in definitions]
        if len(names) != len(set(names)):
            raise ValueError("compiled Tool Profile contains duplicate names")
        return tuple(sorted(definitions, key=lambda item: item.name))

    def _compile_http(self, row: dict[str, Any]) -> ToolProfileDefinition:
        config = self._dict(row.get("config"))
        method = str(config.get("method") or "GET").upper()
        explicit_risk = str(config.get("riskLevel") or config.get("risk_level") or "").lower()
        risk = explicit_risk if explicit_risk in {"read", "write", "dangerous"} else (
            "read" if method in {"GET", "HEAD", "OPTIONS"} else "write"
        )
        approval = bool(config.get("approvalRequired", config.get("approval_required", risk != "read")))
        tool_id = str(row.get("id") or "")
        payload = {
            "source_type": "http",
            "external_tool_id": tool_id,
            "mcp_tool_name": "",
            "display_name": str(row.get("name") or "HTTP Tool")[:512],
            "description": self._description(row),
            "input_schema": self._admin_schema(row.get("inputSchema")),
            "output_schema": self._admin_schema(row.get("outputSchema"), output=True),
            # Admin HTTP output nodes describe projection/presentation. They
            # were never a strict wire contract in the legacy runtime. Only an
            # explicit opt-in may make DSH reject a successful HTTP response.
            "output_validation": "strict" if bool(config.get("strictOutputValidation")) else "none",
            "risk_level": risk,
            "approval_required": approval,
            "required_scopes": ("tools:read",) if risk == "read" else ("tools:write",),
            "timeout_ms": self._timeout_ms(config),
        }
        return ToolProfileDefinition(
            name=self._name("http", tool_id, str(row.get("name") or "tool")),
            version=self._version(payload),
            **payload,
        )

    def _compile_mcp(self, row: dict[str, Any]) -> list[ToolProfileDefinition]:
        config = self._dict(row.get("config"))
        tool_id = str(row.get("id") or "")
        result: list[ToolProfileDefinition] = []
        for discovered in self._list(row.get("discoveredTools")):
            if not isinstance(discovered, dict):
                continue
            native_name = str(discovered.get("name") or "").strip()
            if not native_name:
                continue
            annotations = self._dict(discovered.get("annotations"))
            read_only = annotations.get("readOnlyHint") is True
            destructive = annotations.get("destructiveHint") is True
            risk = "dangerous" if destructive else ("read" if read_only else "write")
            approval = bool(config.get("approvalRequired", config.get("approval_required", risk != "read")))
            payload = {
                "source_type": "mcp",
                "external_tool_id": tool_id,
                "mcp_tool_name": native_name,
                "display_name": str(row.get("name") or "MCP")[:512],
                "description": str(discovered.get("description") or self._description(row))[:4000],
                "input_schema": self._json_schema(discovered.get("inputSchema"), object_root=True),
                "output_schema": self._json_schema(discovered.get("outputSchema"), object_root=False),
                # MCP outputSchema is a protocol-authored JSON Schema contract.
                "output_validation": "strict",
                "risk_level": risk,
                "approval_required": approval,
                "required_scopes": ("tools:read",) if risk == "read" else ("tools:write",),
                "timeout_ms": self._timeout_ms(config),
            }
            result.append(ToolProfileDefinition(
                name=self._name("mcp", tool_id, native_name),
                version=self._version(payload),
                **payload,
            ))
        return result

    @staticmethod
    def _name(kind: str, tool_id: str, label: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_]+", "_", label).strip("_").lower() or "tool"
        digest = hashlib.sha256(f"{kind}:{tool_id}:{label}".encode()).hexdigest()[:10]
        return f"askai_{kind}_{safe[:80]}_{digest}"

    @staticmethod
    def _version(payload: dict[str, Any]) -> str:
        value = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"tool-{hashlib.sha256(value.encode()).hexdigest()[:24]}"

    @classmethod
    def _admin_schema(cls, value: Any, *, output: bool = False) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for item in cls._list(value):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name or name == "[Array Item]":
                continue
            is_required = bool(item.get("required", item.get("require", False)))
            node = cls._admin_node(item, output=output)
            properties[name] = cls._nullable(node) if output and not is_required else node
            if is_required:
                required.append(name)
        schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": not bool(properties)}
        if required:
            schema["required"] = required
        return schema

    @classmethod
    def _admin_node(cls, item: dict[str, Any], *, output: bool = False) -> dict[str, Any]:
        raw_type = str(item.get("type") or "String")
        mapping = {
            "String": "string", "Integer": "integer", "Number": "number",
            "Boolean": "boolean", "Object": "object", "Array": "array", "ArrayObject": "array",
        }
        node: dict[str, Any] = {"type": mapping.get(raw_type, "string")}
        description = str(item.get("description") or item.get("desc") or "").strip()
        if description:
            node["description"] = description
        children = cls._list(item.get("children"))
        if node["type"] == "object":
            child_schema = cls._admin_schema(children, output=output)
            node.update({"properties": child_schema["properties"], "additionalProperties": child_schema["additionalProperties"]})
            if child_schema.get("required"):
                node["required"] = child_schema["required"]
        elif node["type"] == "array":
            valid_children = [child for child in children if isinstance(child, dict)]
            item_marker = next(
                (child for child in valid_children if str(child.get("name") or "").strip() == "[Array Item]"),
                None,
            )
            if item_marker is not None:
                node["items"] = cls._admin_node(item_marker, output=output)
            elif valid_children:
                # The admin UI represents an array of objects by placing the
                # object's fields directly under the Array node.
                node["items"] = cls._admin_schema(valid_children, output=output)
            else:
                node["items"] = {}
        return node

    @staticmethod
    def _nullable(node: dict[str, Any]) -> dict[str, Any]:
        if node.get("type") == "null":
            return node
        return {"anyOf": [node, {"type": "null"}]}

    @staticmethod
    def _json_schema(value: Any, *, object_root: bool) -> dict[str, Any]:
        if isinstance(value, dict) and value:
            return json.loads(json.dumps(value, ensure_ascii=False, default=str))
        return {"type": "object", "properties": {}, "additionalProperties": True} if object_root else {}

    @staticmethod
    def _description(row: dict[str, Any]) -> str:
        return str(row.get("description") or row.get("usageHint") or row.get("name") or "MOVO enterprise tool")[:4000]

    @staticmethod
    def _timeout_ms(config: dict[str, Any]) -> int:
        return max(100, min(300_000, int(float(config.get("timeoutSeconds") or 15) * 1000)))

    @staticmethod
    def _dict(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _list(value: Any) -> list[Any]:
        return list(value) if isinstance(value, list) else []
