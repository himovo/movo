"""Compile authorized ASKAI Skill rows into one immutable DSH Skill Profile."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.dsh_runtime.profile.tools import ToolProfileDefinition
from app.enterprise_capabilities.content.styles import is_writing_style

from .catalog import SkillCatalog
from .models import CompiledSkillProfile, DshSkillDefinition, WritingStyleDefinition
from .workflow import compile_workflow_body, workflow_nodes


class SkillProfileCompiler:
    def __init__(self, catalog: SkillCatalog) -> None:
        self._catalog = catalog

    async def compile(
        self, *, tenant_id: str, user_id: str, tools: tuple[ToolProfileDefinition, ...]
    ) -> CompiledSkillProfile:
        rows = await self._catalog.list_enabled(tenant_id, user_id)
        styles = tuple(self._compile_style(row) for row in rows if is_writing_style(row))
        style_refs = self._style_ref_aliases(styles)
        skills: list[DshSkillDefinition] = []
        for row in rows:
            if is_writing_style(row):
                continue
            skills.append(self._compile_skill(row, tools=tools, style_refs=style_refs))
        names = [item.name for item in skills]
        if len(names) != len(set(names)):
            raise ValueError("compiled Skill Profile contains duplicate names")
        return CompiledSkillProfile(
            skills=tuple(sorted(skills, key=lambda item: item.name)),
            writing_styles=tuple(sorted(styles, key=lambda item: item.ref)),
        )

    def _compile_style(self, row: dict[str, Any]) -> WritingStyleDefinition:
        source_id = self._source_id(row)
        source_scope = self._scope(row)
        name = str(row.get("name") or "Writing standard")[:256]
        description = str(row.get("description") or row.get("summary") or "")[:2000]
        instructions = str(row.get("skill_markdown") or "").strip()
        if not instructions:
            contract = row.get("contract_json") if isinstance(row.get("contract_json"), dict) else {}
            instructions = json.dumps(contract, ensure_ascii=False, sort_keys=True)
        if not instructions:
            raise ValueError(f"writing standard has no instructions: {row.get('name')}")
        payload = {
            "source_id": source_id,
            "source_scope": source_scope,
            "name": name,
            "description": description,
            "instructions": instructions,
        }
        digest = self._digest(payload)
        return WritingStyleDefinition(
            ref=f"style-{hashlib.sha256(source_id.encode()).hexdigest()[:24]}",
            version=f"style-v-{digest[:24]}",
            source_id=source_id,
            source_scope=source_scope,
            name=name,
            description=description,
            instructions=instructions[:50_000],
        )

    def _compile_skill(
        self,
        row: dict[str, Any],
        *,
        tools: tuple[ToolProfileDefinition, ...],
        style_refs: dict[str, str],
    ) -> DshSkillDefinition:
        source_id = self._source_id(row)
        workflow = bool(workflow_nodes(row)) or str(row.get("skill_type") or "") == "composite_task"
        if workflow:
            content, capability_refs = compile_workflow_body(row, tools=tools, style_refs=style_refs)
            kind = "workflow"
        else:
            content = str(row.get("skill_markdown") or "").strip()
            if not content:
                raise ValueError(f"Skill has no native instructions: {row.get('name')}")
            capability_refs = ()
            kind = "ordinary"
        description = str(row.get("description") or row.get("summary") or row.get("name") or "Skill").strip()[:2000]
        when_to_use = str(row.get("notes") or row.get("applicable_scenarios") or description)[:4000]
        source_scope = self._scope(row)
        native_name = self._native_name(str(row.get("name") or "skill"), source_id)
        payload = {
            "name": native_name,
            "source_id": source_id,
            "source_scope": source_scope,
            "kind": kind,
            "description": description,
            "when_to_use": when_to_use,
            "content": content,
            "capability_refs": capability_refs,
        }
        return DshSkillDefinition(
            name=native_name,
            version=f"skill-v-{self._digest(payload)[:24]}",
            source_id=source_id,
            source_scope=source_scope,
            kind=kind,
            description=description,
            when_to_use=when_to_use,
            content=content[:100_000],
            capability_refs=capability_refs,
        )

    @staticmethod
    def _native_name(label: str, source_id: str) -> str:
        ascii_label = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "askai-skill"
        digest = hashlib.sha256(source_id.encode()).hexdigest()[:10]
        return f"{ascii_label[:90].strip('-')}-{digest}"

    @staticmethod
    def _source_id(row: dict[str, Any]) -> str:
        value = str(row.get("id") or "").strip()
        if not value:
            raise ValueError("Skill source id is empty")
        return value

    @staticmethod
    def _scope(row: dict[str, Any]) -> str:
        return "organization" if str(row.get("visibility") or "").lower() == "organization" or str(row.get("source") or "") == "org_db" else "personal"

    @staticmethod
    def _digest(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    @staticmethod
    def _style_ref_aliases(styles: tuple[WritingStyleDefinition, ...]) -> dict[str, str]:
        """Accept the two IDs already used by the control plane for org Skills.

        The employee/runtime adapter exposes ``org_skill:<mongo-id>`` while an
        organization Workflow stores ``boundWritingSkillId`` as the raw Mongo
        ID.  Both identify the same authorized immutable style.  Ambiguous raw
        aliases are deliberately removed instead of selecting one silently.
        """
        aliases = {item.source_id: item.ref for item in styles}
        ambiguous: set[str] = set()
        for item in styles:
            if not item.source_id.startswith("org_skill:"):
                continue
            raw_id = item.source_id.removeprefix("org_skill:")
            existing = aliases.get(raw_id)
            if existing is not None and existing != item.ref:
                ambiguous.add(raw_id)
            else:
                aliases[raw_id] = item.ref
        for raw_id in ambiguous:
            aliases.pop(raw_id, None)
        return aliases
