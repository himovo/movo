from __future__ import annotations

import datetime
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import uuid

import yaml
from pydantic import BaseModel, Field, ValidationError

from app.core.tenant import add_main_scope, resolve_main_id
from app.core.db import get_db
from app.services.skill_assets.publish_channels import publish_channel_registry
from app.services.skill_assets.composite_task import parse_composite_skill
from app.services.llm import llm_service
from app.services.org_skill_adapter import _workflow_markdown, _workflow_nodes
from app.services.style_skill_locale import source_style_language, style_body_language_instruction, style_description_fallback
from app.utils.oss_uploader import AliyunOSSUploader


logger = logging.getLogger(__name__)


from app.services.skill_contracts import (
    UserSkill,
    SkillContractModel,
    _split_frontmatter,
    _slugify,
    _normalize_skill_role,
    _normalize_skill_type,
    _as_string_list,
    _normalize_token_inputs,
    _normalize_target_length,
    _normalize_section_structure,
    _flatten_section_titles,
    _render_section_structure_lines,
    _normalize_contract_json,
    _contract_json_from_markdown,
    _heuristic_enrich_contract,
    _render_skill_markdown_from_contract,
    _has_executable_workflow_steps,
    _workflow_markdown_from_config,
    _infer_role_from_fields,
    _split_list_tokens,
    _canonical_block_token,
    _compile_skill_contract,
)
from app.services.skill_template_generation import SkillTemplateGenerationMixin
from app.services.skill_style_generation import SkillStyleGenerationMixin

class UserSkillService(SkillTemplateGenerationMixin, SkillStyleGenerationMixin):
    async def enrich_skill_contract_draft(
        self,
        *,
        input_profile: Dict[str, Any],
        description: str = "",
    ) -> Dict[str, Any]:
        normalized_input = _normalize_contract_json(
            input_profile or {},
            skill_type=str((input_profile or {}).get("skill_type") or "style"),
            name=str((input_profile or {}).get("name") or "Untitled Skill"),
            description=description,
            summary=str((input_profile or {}).get("summary") or description or ""),
            notes=str((input_profile or {}).get("notes") or ""),
        )
        heuristic_input = _heuristic_enrich_contract(normalized_input)
        system = (
            "You enrich structured AI skill contracts for a writing/runtime system.\n"
            "Return JSON only with keys: skill_type,name,summary,applicable_scenarios,publish_channel,"
            "content_form,target_audience,preferred_style,target_length,section_structure,required_sections,required_elements,forbidden_elements,reference_materials,notes.\n"
            "Rules:\n"
            "- Preserve user intent exactly; enrich clarity, not scope.\n"
            "- Keep skill_type unchanged.\n"
            "- publish_channel/content_form/target_audience/preferred_style are arrays.\n"
            "- target_length is an object like {\"min\":3500,\"max\":4500,\"unit\":\"chinese_chars\"}; preserve it if provided, otherwise leave it empty.\n"
            "- section_structure is an ordered tree of section objects with title, must_include, avoid, notes, children; preserve it if provided and do not invent extra sections.\n"
            "- required_sections is an ordered array of final reader-facing section titles only. Leave empty if the user did not provide a fixed section structure.\n"
            "- required_elements is a must-cover checklist, not a section list.\n"
            "- forbidden_elements should be concise actionable items.\n"
            "- notes should become a compact operator-facing instruction block.\n"
            "- Do not invent permissions, tools, or execution claims.\n"
            "- Output valid JSON only."
        )
        try:
            resp = await llm_service.chat_complete(
                [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "description": description,
                                "input_profile": heuristic_input,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                temperature=0.2,
            )
            cleaned = resp.replace("```json", "").replace("```", "").strip()
            enriched = json.loads(cleaned)
            if isinstance(enriched, dict):
                enriched = {**heuristic_input, **enriched}
                if not list(enriched.get("section_structure") or []) and list(heuristic_input.get("section_structure") or []):
                    enriched["section_structure"] = list(heuristic_input.get("section_structure") or [])
                if not list(enriched.get("required_sections") or []) and list(heuristic_input.get("required_sections") or []):
                    enriched["required_sections"] = list(heuristic_input.get("required_sections") or [])
                contract_json = _normalize_contract_json(
                    enriched,
                    skill_type=str(heuristic_input.get("skill_type") or "style"),
                    name=str(heuristic_input.get("name") or "Untitled Skill"),
                    description=description,
                    summary=str(heuristic_input.get("summary") or description or ""),
                    notes=str(heuristic_input.get("notes") or ""),
                )
                contract_json = _heuristic_enrich_contract(contract_json)
                markdown = _render_skill_markdown_from_contract(
                    contract_json,
                    name=str(contract_json.get("name") or heuristic_input.get("name") or "Untitled Skill"),
                    description=description or str(contract_json.get("summary") or ""),
                )
                return {
                    "input_profile": heuristic_input,
                    "contract_json": contract_json,
                    "skill_markdown": markdown,
                }
        except Exception:
            pass

        fallback_markdown = _render_skill_markdown_from_contract(
            heuristic_input,
            name=str(heuristic_input.get("name") or "Untitled Skill"),
            description=description or str(heuristic_input.get("summary") or ""),
        )
        return {
            "input_profile": heuristic_input,
            "contract_json": heuristic_input,
            "skill_markdown": fallback_markdown,
        }

    async def list_skills(self, user_id: str, main_id: str = "default", *, include_package_files: bool = True) -> List[Dict[str, Any]]:
        db = get_db()
        projection = None if include_package_files else {"package_files": 0}
        cursor = db.user_skills.find(add_main_scope({"user_id": str(user_id)}, main_id), projection).sort([("created_at", -1), ("_id", 1)])
        skills = []
        async for doc in cursor:
            skills.append(self._serialize(doc))
        return skills

    async def get_skill(self, user_id: str, skill_id: str, main_id: str = "default") -> Optional[Dict[str, Any]]:
        db = get_db()
        doc = await db.user_skills.find_one(add_main_scope({"_id": skill_id, "user_id": str(user_id)}, main_id))
        if not doc:
            return None
        return self._serialize(doc)

    async def update_skill(self, user_id: str, skill_id: str, updates: Dict[str, Any], main_id: str = "default") -> Optional[Dict[str, Any]]:
        db = get_db()
        current = await db.user_skills.find_one(add_main_scope({"_id": skill_id, "user_id": str(user_id)}, main_id))
        if not current:
            return None

        merged_name = str(updates.get("name", current.get("name", "")) or "")
        merged_description = str(updates.get("description", current.get("description", "")) or "")
        merged_summary = str(updates.get("summary", current.get("summary", "")) or "")
        merged_category = str(updates.get("category", current.get("category", "")) or "")
        merged_formats = list(updates.get("formats", current.get("formats", [])) or [])
        merged_notes = str(updates.get("notes", current.get("notes", "")) or "")
        merged_role = _normalize_skill_role(updates.get("role")) or _normalize_skill_role(current.get("role"))
        merged_skill_type = _normalize_skill_type(updates.get("skill_type"), role=merged_role or current.get("role"))
        merged_contract_json = _normalize_contract_json(
            updates.get("contract_json", current.get("contract_json", {})),
            skill_type=merged_skill_type,
            name=merged_name,
            description=merged_description,
            summary=merged_summary,
            notes=merged_notes,
        )
        merged_config = updates.get("config", current.get("config") or {})
        if not isinstance(merged_config, dict):
            merged_config = {}
        merged_markdown = str(updates.get("skill_markdown", "") or "").strip()
        merged_markdown = _workflow_markdown_from_config(
            config=merged_config,
            name=merged_name,
            description=merged_description,
            scenario=str(updates.get("scenario", current.get("scenario", "")) or ""),
            type_value=updates.get("type", current.get("type")),
            skill_type_value=merged_skill_type,
            current_markdown=merged_markdown,
        )
        if not merged_markdown:
            merged_markdown = _render_skill_markdown_from_contract(
                merged_contract_json,
                name=merged_name,
                description=merged_description,
            )

        contract = _compile_skill_contract(
            name=merged_name,
            description=merged_description,
            category=merged_category,
            formats=merged_formats,
            skill_markdown=merged_markdown,
            skill_type=merged_skill_type,
            contract_json=merged_contract_json,
        )
        normalized_role = _normalize_skill_role(updates.get("role"))
        effective_role = normalized_role or str(contract.get("role") or "")
        if effective_role:
            updates["role"] = effective_role
            contract["role"] = effective_role
        updates["skill_type"] = _normalize_skill_type(merged_skill_type, role=effective_role)
        updates["config"] = merged_config
        updates["contract_json"] = dict(contract.get("contract_json") or merged_contract_json)
        updates["input_profile"] = dict(updates.get("input_profile") or current.get("input_profile") or {})
        updates["skill_markdown"] = merged_markdown
        updates["execution_plane"] = str(contract.get("execution_plane") or "runtime")
        updates["skill_contract"] = contract
        updates["skill_contract_version"] = str(contract.get("version") or "v1")
        updates["skill_lint_warnings"] = list(contract.get("lint_warnings") or [])
        if str((current.get("package_source") or {}).get("kind") or "") == "movo_share":
            updates["locally_modified"] = True
        updates["updated_at"] = datetime.datetime.utcnow()
        await db.user_skills.update_one(
            add_main_scope({"_id": skill_id, "user_id": str(user_id)}, main_id),
            {"$set": updates},
        )
        doc = await db.user_skills.find_one(add_main_scope({"_id": skill_id, "user_id": str(user_id)}, main_id))
        if not doc:
            return None
        return self._serialize(doc)

    async def delete_skill(self, user_id: str, skill_id: str, main_id: str = "default") -> bool:
        db = get_db()
        current = await db.user_skills.find_one(
            add_main_scope({"_id": skill_id, "user_id": str(user_id)}, main_id),
            {"package_id": 1, "previous_package_ids": 1},
        )
        result = await db.user_skills.delete_one(add_main_scope({"_id": skill_id, "user_id": str(user_id)}, main_id))
        if result.deleted_count and current:
            package_ids = [str(current.get("package_id") or ""), *[str(item) for item in current.get("previous_package_ids") or []]]
            await db.skill_packages.delete_many({"_id": {"$in": [item for item in package_ids if item]}})
        return result.deleted_count > 0

    async def set_skill_enabled(self, user_id: str, skill_id: str, enabled: bool, main_id: str = "default") -> Optional[Dict[str, Any]]:
        db = get_db()
        query = add_main_scope({"_id": skill_id, "user_id": str(user_id)}, main_id)
        result = await db.user_skills.update_one(query, {"$set": {
            "enabled": bool(enabled), "is_active": bool(enabled), "updated_at": datetime.datetime.utcnow(),
        }})
        if not result.matched_count:
            return None
        doc = await db.user_skills.find_one(query)
        return self._serialize(doc) if doc else None

    async def create_skill(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        db = get_db()
        now = datetime.datetime.utcnow()
        main_id = resolve_main_id(payload.get("main_id") or payload.get("mainId"))
        explicit_role = _normalize_skill_role(payload.get("role"))
        skill_type = _normalize_skill_type(payload.get("skill_type"), role=explicit_role)
        contract_json = _normalize_contract_json(
            payload.get("contract_json"),
            skill_type=skill_type,
            name=str(payload.get("name", "") or ""),
            description=str(payload.get("description", "") or ""),
            summary=str(payload.get("summary", "") or ""),
            notes=str(payload.get("notes", "") or ""),
        )
        skill_markdown = str(payload.get("skill_markdown", "") or "").strip()
        payload_config = payload.get("config") or {}
        if not isinstance(payload_config, dict):
            payload_config = {}
        skill_markdown = _workflow_markdown_from_config(
            config=payload_config,
            name=str(payload.get("name", "") or ""),
            description=str(payload.get("description", "") or ""),
            scenario=str(payload.get("scenario", "") or ""),
            type_value=payload.get("type"),
            skill_type_value=skill_type,
            current_markdown=skill_markdown,
        )
        if not skill_markdown:
            skill_markdown = _render_skill_markdown_from_contract(
                contract_json,
                name=str(payload.get("name", "") or ""),
                description=str(payload.get("description", "") or ""),
            )
        contract = _compile_skill_contract(
            name=str(payload.get("name", "") or ""),
            description=str(payload.get("description", "") or ""),
            category=str(payload.get("category", "") or ""),
            formats=list(payload.get("formats") or []),
            skill_markdown=skill_markdown,
            skill_type=skill_type,
            contract_json=contract_json,
        )
        role = explicit_role or str(contract.get("role") or "")
        if role:
            contract["role"] = role
        skill_doc = {
            "_id": payload.get("id") or uuid.uuid4().hex,
            "user_id": str(user_id),
            "main_id": main_id,
            "name": payload.get("name", "Untitled Skill"),
            "description": payload.get("description", ""),
            "scenario": payload.get("scenario", ""),
            "summary": payload.get("summary", ""),
            "category": payload.get("category", ""),
            "role": role,
            "skill_type": _normalize_skill_type(skill_type, role=role),
            "type": payload.get("type", ""),
            "config": payload_config,
            "enabled": bool(payload.get("enabled", payload.get("is_active", False))),
            "tags": payload.get("tags") or [],
            "visibility": payload.get("visibility", "private"),
            "formats": payload.get("formats") or [],
            "input_profile": payload.get("input_profile") or {},
            "contract_json": dict(contract.get("contract_json") or contract_json),
            "skill_markdown": skill_markdown,
            "skill_object_path": payload.get("skill_object_path", ""),
            "sources": payload.get("sources") or [],
            "resources": payload.get("resources") or {},
            "advanced": payload.get("advanced") or {},
            "notes": payload.get("notes", ""),
            "execution_plane": str(contract.get("execution_plane") or "runtime"),
            "skill_contract_version": str(contract.get("version") or "v1"),
            "skill_contract": contract,
            "skill_lint_warnings": list(contract.get("lint_warnings") or []),
            "created_at": now,
            "updated_at": now,
            "is_active": bool(payload.get("is_active", True)),
        }
        await db.user_skills.insert_one(skill_doc)
        return self._serialize(skill_doc)

    async def select_skill(
        self,
        user_id: str,
        user_text: str,
        intent: str,
        formats: List[str],
        main_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        skills = await self.list_skills(user_id, main_id=main_id)
        if not skills:
            return None
        candidates = []
        for skill in skills:
            if not skill.get("is_active"):
                continue
            skill_formats = skill.get("formats") or []
            # Allow 'markdown' skills as candidates for almost any text-related request,
            # as they are the foundation for PDF/Docx/PPTX exports.
            if not skill_formats or any(fmt in skill_formats for fmt in formats) or "markdown" in skill_formats:
                candidates.append(skill)
        if not candidates:
            return None

        prompt = {
            "intent": intent,
            "formats": formats,
            "user_request": user_text,
            "skills": [
                {
                    "name": s["name"],
                    "description": s.get("description", ""),
                    "formats": s.get("formats") or [],
                }
                for s in candidates
            ],
        }
        system = (
            "You are a skill selector. Choose the best matching user skill for the request. "
            "Return JSON: {\"skill_name\": \"...\"} or {\"skill_name\": null}."
        )
        response = await llm_service.chat_complete(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            temperature=0.1,
        )
        try:
            cleaned = response.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)
            chosen = data.get("skill_name")
        except Exception:
            chosen = None
        if not chosen:
            return None
        for skill in candidates:
            if skill["name"] == chosen:
                return skill
        return None

    async def build_skill_markdown(
        self,
        name: str,
        description: str,
        formats: List[str],
        sources_text: str,
        notes: str,
    ) -> str:
        safe_name = _slugify(name) or "user-skill"
        system = (
            "You are an expert skill author. Create a SKILL.md file with valid YAML frontmatter "
            "and clear step-by-step instructions. The skill is for document generation and formatting. "
            "Follow the Agent Skills SKILL.md conventions."
        )
        user = {
            "name": safe_name,
            "description": description,
            "formats": formats,
            "notes": notes,
            "reference": sources_text,
        }
        # Fixed temperature for build_skill_markdown as well if it uses the same model validation logic,
        # but previously it was 0.2. I'll keep it 0.2 unless it errors, but wait, the previous error was in generate_skill_from_template.
        # SAFE OPTION: Use 1.0 here too if it fails, but let's stick to what worked before for this method.
        # Actually, let's play it safe and use 1.0 for all if they share the model config.
        # But for now, I will revert to 0.2 for this one as it wasn't the one failing in my test.
        response = await llm_service.chat_complete(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.2, 
        )
        content = response.strip()
        if not content.startswith("---"):
            front = (
                "---\n"
                f"name: {safe_name}\n"
                f"description: {description or 'User skill for document generation'}\n"
                "---\n\n"
            )
            content = front + content
        return content

    async def persist_skill_markdown(self, user_id: str, name: str, content: str) -> tuple[str, str]:
        uploader = AliyunOSSUploader()
        filename = f"{_slugify(name) or 'user-skill'}.md"
        url, object_path = uploader.upload_bytes_with_path(
            content.encode("utf-8"),
            user_id=str(user_id),
            file_name=filename,
            content_type="text/markdown",
        )
        return url, object_path

    def _serialize(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        config = doc.get("config") or {}
        if not isinstance(config, dict):
            config = {}
        skill_markdown = _workflow_markdown_from_config(
            config=config,
            name=str(doc.get("name", "") or ""),
            description=str(doc.get("description", "") or ""),
            scenario=str(doc.get("scenario", "") or ""),
            type_value=doc.get("type"),
            skill_type_value=doc.get("skill_type"),
            current_markdown=str(doc.get("skill_markdown", "") or ""),
        )
        existing_contract = doc.get("skill_contract")
        if isinstance(existing_contract, dict):
            contract = existing_contract
        else:
            contract = _compile_skill_contract(
                name=str(doc.get("name", "") or ""),
                description=str(doc.get("description", "") or ""),
                category=str(doc.get("category", "") or ""),
                formats=list(doc.get("formats") or []),
                skill_markdown=skill_markdown,
                skill_type=str(doc.get("skill_type") or ""),
                contract_json=doc.get("contract_json") if isinstance(doc.get("contract_json"), dict) else {},
            )
        role = _normalize_skill_role(doc.get("role")) or _normalize_skill_role(contract.get("role")) or _infer_role_from_fields(
            category=str(doc.get("category", "") or ""),
            name=str(doc.get("name", "") or ""),
            description=str(doc.get("description", "") or ""),
            skill_markdown=skill_markdown,
            formats=list(doc.get("formats") or []),
        )
        skill_type = _normalize_skill_type(doc.get("skill_type"), role=role)
        return {
            "id": str(doc.get("_id")),
            "user_id": str(doc.get("user_id")),
            "main_id": resolve_main_id(doc.get("main_id")),
            "name": doc.get("name"),
            "description": doc.get("description", ""),
            "scenario": doc.get("scenario", ""),
            "summary": doc.get("summary", ""),
            "category": doc.get("category", ""),
            "role": role,
            "skill_type": skill_type,
            "type": doc.get("type", ""),
            "config": config,
            "enabled": doc.get("enabled", doc.get("is_active", True)),
            "tags": doc.get("tags") or [],
            "visibility": doc.get("visibility", "private"),
            "formats": doc.get("formats") or [],
            "input_profile": doc.get("input_profile") or {},
            "contract_json": doc.get("contract_json") or contract.get("contract_json") or {},
            "skill_markdown": skill_markdown,
            "skill_object_path": doc.get("skill_object_path", ""),
            "sources": doc.get("sources") or [],
            "resources": doc.get("resources") or {},
            "advanced": doc.get("advanced") or {},
            "notes": doc.get("notes", ""),
            "execution_plane": str(doc.get("execution_plane") or contract.get("execution_plane") or "runtime"),
            "skill_contract_version": str(doc.get("skill_contract_version") or contract.get("version") or "v1"),
            "skill_contract": contract,
            "skill_lint_warnings": list(doc.get("skill_lint_warnings") or contract.get("lint_warnings") or []),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
            "is_active": doc.get("is_active", True),
            "package_id": str(doc.get("package_id") or ""),
            "package_slug": str(doc.get("package_slug") or ""),
            "package_version": str(doc.get("package_version") or ""),
            "package_digest": str(doc.get("package_digest") or ""),
            **({"pending_package": dict(doc["pending_package"])} if isinstance(doc.get("pending_package"), dict) else {}),
            **({"package_requires_environment": bool(doc["package_requires_environment"])} if "package_requires_environment" in doc else {}),
            **({"package_requires_execution": bool(doc["package_requires_execution"])} if "package_requires_execution" in doc else {}),
            "package_files": list(doc.get("package_files") or []),
            "package_warnings": list(doc.get("package_warnings") or []),
            "package_kind": str(doc.get("package_kind") or "ordinary"),
            "package_children": list(doc.get("package_children") or []),
            "package_source": dict(doc.get("package_source") or {}),
            "distribution_id": str(doc.get("distribution_id") or ""),
            "locally_modified": bool(doc.get("locally_modified", False)),
            "draft": dict(doc.get("draft") or {}),
            "authoring_mode": str(doc.get("authoring_mode") or ""),
            "publication_status": str(doc.get("publication_status") or ""),
            "published_version": str(doc.get("published_version") or ""),
            "published_digest": str(doc.get("published_digest") or ""),
            "published_release_id": str(doc.get("published_release_id") or ""),
            "published_at": doc.get("published_at"),
            "draft_revision": int(doc.get("draft_revision") or 0),
            "draft_updated_at": doc.get("draft_updated_at"),
            "has_unpublished_changes": bool(doc.get("has_unpublished_changes", False)),
            "model_invocable": bool(doc.get("model_invocable", True)),
            "user_invocable": bool(doc.get("user_invocable", True)),
        }


user_skill_service = UserSkillService()
