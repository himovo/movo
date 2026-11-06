from __future__ import annotations
from app.infrastructure.observability.config import log_print

import ast
import asyncio
import json
import os
import re
import tempfile
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query, Header
from pydantic import AliasChoices, BaseModel, Field

from app.api.time_utils import utc_iso
from app.services.skill_assets.trajectory_distiller import distill_trajectory, refine_steps
from app.services.skills import user_skill_service
from app.services.skill_packages.readiness import attach_environment_status, environment_status
from app.services.org_skill_adapter import _workflow_markdown, _workflow_nodes, organization_skill_adapter
from app.services.personal_knowledge.document_selection import validate_personal_workflow_documents
from app.core.config import get_settings
from app.llm.factory import get_llm_client
from app.llm.types import Message, Role
from app.utils.oss_uploader import AliyunOSSUploader
from app.utils.uploads import read_upload_with_limit
from app.product.resource_access import filter_allowed_resource_ids
from app.api.principal import require_api_principal
from app.api.workflow_messages import localized_workflow_message
from app.api.script_validation_messages import localize_script_check
from app.api.workflow_check_messages import workflow_check_fallback, workflow_check_language_instruction

import yaml as _yaml


from .skill_support.models import (
    AdminShapeSkillPayload,
    ApiResponse,
    RecordingEditModel,
    RecordingEventModel,
    ScriptPluginCheckRequest,
    ScriptPluginFixRequest,
    ScriptPluginGenerateRequest,
    SkillEnabledPayload,
    SkillEnrichRequest,
    SkillFromRecordingRequest,
    SkillGenerateRequest,
    SkillListRequest,
    SkillUpdateRequest,
    WorkflowLogicCheckRequest,
    WorkflowNodePolishRequest,
    WorkflowNodesGenerateRequest,
    WorkflowStepsGenerateRequest,
    _encode_composite_yaml,
)
from .skill_support.documents import _download_object, _extract_text_from_object, _extract_text_sync, _truncate
from .skill_support.workflow import (
    _NODE_TYPE_ALIASES,
    _WORKFLOW_NODE_TYPES,
    _admin_shape_payload_to_user_payload,
    _admin_shape_skill,
    _cursor_offset,
    _estimate_workflow_step_count,
    _extract_json_object,
    _extract_workflow_nodes_from_text,
    _extract_workflow_steps_from_text,
    _matches_skill_keyword,
    _normalize_bool,
    _normalize_workflow_check_result,
    _normalize_workflow_node,
    _normalize_workflow_node_catalog,
    _normalize_workflow_node_type,
    _resolved_workflow_node_count,
    _resolved_workflow_step_count,
    _safe_bool,
    _safe_dict,
    _selectable_skill_item,
    _selectable_skill_type,
    _skill_source_scope,
    _time_text,
    _workflow_text_steps,
)
from .skill_support.scripts import (
    _SCRIPT_PLUGIN_ALLOWED_IMPORT_MODULES,
    _SCRIPT_PLUGIN_ALLOWED_IMPORT_ROOTS,
    _SCRIPT_PLUGIN_CODE_MAX_BYTES,
    _SCRIPT_PLUGIN_DENIED_CALLS,
    _SCRIPT_PLUGIN_DENIED_FULL_CALLS,
    _SCRIPT_PLUGIN_DENIED_IMPORT_ROOTS,
    _SCRIPT_PLUGIN_WRITE_FUNCS,
    _assign_target_names,
    _call_name,
    _collect_output_path_names,
    _fix_script_plugin_with_llm,
    _generate_script_plugin_with_llm,
    _generated_code_hardcode_warnings,
    _is_allowed_script_import,
    _is_import_only_try,
    _literal_string,
    _looks_like_output_dir_expr,
    _normalize_script_llm_review,
    _review_script_plugin_with_llm,
    _script_issue,
    _validate_script_plugin_static,
)
from .skill_support.generation import (
    _check_workflow_logic_with_llm,
    _generate_workflow_nodes_with_llm,
    _generate_workflow_steps_with_llm,
    _polish_workflow_node_with_llm,
)

router = APIRouter(dependencies=[Depends(require_api_principal)])


@router.post("/skills/upload", response_model=ApiResponse)
async def upload_skill_source(
    user_id: str = Form(...),
    file: UploadFile = File(...),
) -> ApiResponse:
    settings = get_settings()
    uploader = AliyunOSSUploader()
    content = await read_upload_with_limit(
        file,
        max_bytes=settings.MAX_UPLOAD_SKILL_SOURCE_BYTES,
        label="Skill source upload",
    )
    url, object_path = uploader.upload_bytes_with_path(
        content,
        user_id=str(user_id),
        file_name=file.filename or "skill_source.bin",
        content_type=file.content_type,
    )
    return ApiResponse(
        code=0,
        message="success",
        data={
            "object_path": object_path,
            "url": url,
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(content),
        },
    )


@router.post("/skills/analyze_template", response_model=ApiResponse)
async def analyze_template(
    file: UploadFile = File(...),
) -> ApiResponse:
    try:
        settings = get_settings()
        content = await read_upload_with_limit(
            file,
            max_bytes=settings.MAX_UPLOAD_TEMPLATE_BYTES,
            label="Template upload",
        )
        filename = file.filename or "unknown.txt"
        data = await user_skill_service.generate_style_skill_from_document(filename, content)
        return ApiResponse(code=0, message="success", data=data)
    except ValueError as e:
        import traceback
        with open("/tmp/askai_backend_error.log", "a") as f:
            f.write(f"Analyze template error (ValueError): {str(e)}\n")
            f.write(traceback.format_exc())
            f.write("\n")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log_print(f"Analyze template error: {e}")
        import traceback
        with open("/tmp/askai_backend_error.log", "a") as f:
            f.write(f"Analyze template error: {str(e)}\n")
            f.write(traceback.format_exc())
            f.write("\n")
        raise HTTPException(status_code=500, detail="Failed to analyze template")


@router.post("/skills/generate", response_model=ApiResponse)
async def generate_skill(payload: SkillGenerateRequest) -> ApiResponse:
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Skill name is required")

    skill_md = (payload.skill_markdown or "").strip()
    if not skill_md and payload.sources:
        sources_text = []
        for obj in payload.sources:
            try:
                text = await _extract_text_from_object(obj)
                if text:
                    sources_text.append(text)
            except Exception:
                continue
        combined = _truncate("\n\n".join(sources_text))
        skill_md = await user_skill_service.build_skill_markdown(
            payload.name,
            payload.description or "",
            payload.formats or [],
            combined,
            payload.notes or "",
        )
    
    if not skill_md and not payload.contract_json:
        skill_md = (
            "# Purpose\n\n"
            "# When to use\n- \n\n"
            "# Inputs\n- \n\n"
            "# Workflow\n1. \n2. \n\n"
            "# Output format\n- \n\n"
            "# Examples\n## Input\n\n## Output\n\n"
            "# Rules\n- \n\n"
            "# Failure handling\n- \n"
        )
    skill_object_path = ""
    try:
        _, skill_object_path = await user_skill_service.persist_skill_markdown(
            payload.user_id,
            payload.name,
            skill_md,
        )
    except Exception as exc:
        # Do not block creation if OSS is unavailable
        skill_object_path = ""
        log_print(f"[skills] persist_skill_markdown failed: {exc}", flush=True)
    skill_id = uuid.uuid4().hex
    created = await user_skill_service.create_skill(
        payload.user_id,
        {
            "id": skill_id,
            "main_id": payload.main_id,
            "name": payload.name,
            "description": payload.description,
            "summary": payload.summary,
            "category": payload.category,
            "role": payload.role,
            "skill_type": payload.skill_type,
            "tags": payload.tags,
            "visibility": payload.visibility,
            "formats": payload.formats,
            "input_profile": payload.input_profile or {},
            "contract_json": payload.contract_json or {},
            "skill_markdown": skill_md,
            "skill_object_path": skill_object_path,
            "sources": [{"object_path": p} for p in payload.sources],
            "resources": payload.resources or {},
            "advanced": payload.advanced or {},
            "notes": payload.notes,
            "is_active": bool(payload.is_active),
        },
    )
    return ApiResponse(code=0, message="success", data=created)


@router.post("/skills/from_recording", response_model=ApiResponse)
async def skill_from_recording(payload: SkillFromRecordingRequest) -> ApiResponse:
    """Persist a recorded browser trajectory as a composite_task skill.

    The agent's recorder emits semantic events while the user walks
    through the real flow; this endpoint converts them into the same
    CompositeStep YAML shape the manual editor produces, so downstream
    consumers (parser, runtime, UI) stay on a single code path."""
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Skill name is required")
    raw_events = [e.model_dump() for e in payload.events]
    steps = distill_trajectory(
        raw_events,
        site_profile_id=str(payload.site_profile_id or ""),
        variables=dict(payload.variables or {}),
    )
    if payload.edits:
        steps = refine_steps(steps, edits=[e.model_dump() for e in payload.edits])
    if not steps:
        raise HTTPException(status_code=400, detail="No usable events in recording")

    skill_markdown = _encode_composite_yaml(
        name=payload.name.strip(),
        description=str(payload.description or "").strip(),
        triggers=list(payload.triggers or []),
        steps=steps,
    )

    skill_object_path = ""
    try:
        _, skill_object_path = await user_skill_service.persist_skill_markdown(
            payload.user_id, payload.name, skill_markdown,
        )
    except Exception as exc:
        log_print(f"[skills] persist_skill_markdown failed: {exc}", flush=True)

    skill_id = uuid.uuid4().hex
    created = await user_skill_service.create_skill(
        payload.user_id,
        {
            "id": skill_id,
            "main_id": payload.main_id,
            "name": payload.name,
            "description": payload.description or "",
            "summary": payload.description or "",
            "category": "Browser Automation",
            "skill_type": "composite_task",
            "tags": ["composite_task", "recorded"],
            "visibility": payload.visibility or "private",
            "formats": ["markdown"],
            "input_profile": {},
            "contract_json": {},
            "skill_markdown": skill_markdown,
            "skill_object_path": skill_object_path,
            "sources": [],
            "resources": {},
            "advanced": {},
            "notes": "",
            "is_active": bool(payload.is_active),
        },
    )
    return ApiResponse(code=0, message="success", data=created)


@router.post("/skills/enrich_draft", response_model=ApiResponse)
async def enrich_skill_draft(payload: SkillEnrichRequest) -> ApiResponse:
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Skill name is required")
    enriched = await user_skill_service.enrich_skill_contract_draft(
        input_profile={
            **(payload.input_profile or {}),
            "name": payload.name,
            "skill_type": payload.skill_type or "style",
        },
        description=payload.description or "",
    )
    return ApiResponse(code=0, message="success", data=enriched)


@router.post("/skills/enrich-writing-style", response_model=ApiResponse)
async def enrich_writing_style(
    payload: Dict[str, Any],
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill name is required")
    draft = _safe_dict(payload.get("draft"))
    input_profile = {
        "skill_type": "style",
        "name": name,
        "summary": str(payload.get("description") or "").strip(),
        "applicable_scenarios": str(payload.get("scenario") or "").strip(),
        "publish_channel": draft.get("publishChannel") or [],
        "content_form": draft.get("contentForm") or [],
        "target_audience": draft.get("targetAudience") or [],
        "preferred_style": draft.get("preferredStyle") or [],
        "target_length": draft.get("targetLength") or {},
        "section_structure": draft.get("sectionStructure") or [],
        "required_sections": draft.get("requiredSections") or [],
        "required_elements": draft.get("requiredElements") or [],
        "forbidden_elements": draft.get("forbiddenElements") or [],
        "notes": str(draft.get("notes") or "").strip(),
        "main_id": main_id_snake or main_id,
        "user_id": user_id,
    }
    enriched = await user_skill_service.enrich_skill_contract_draft(
        input_profile=input_profile,
        description=str(payload.get("description") or "").strip(),
    )
    data = _safe_dict(enriched)
    return ApiResponse(
        code=0,
        message="success",
        data={
            "inputProfile": _safe_dict(data.get("input_profile")),
            "contractJson": _safe_dict(data.get("contract_json")),
            "skillMarkdown": str(data.get("skill_markdown") or ""),
        },
    )


@router.post("/skills/generate-workflow-steps", response_model=ApiResponse)
async def generate_workflow_steps(payload: WorkflowStepsGenerateRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill name is required")
    max_steps = _resolved_workflow_step_count(payload)
    source = "llm"
    message = "success"
    try:
        steps = await _generate_workflow_steps_with_llm(payload)
    except Exception as exc:
        log_print(f"[skills] generate_workflow_steps failed: {exc}", flush=True)
        steps = []
        source = "error"
        message = str(exc) or "生成失败"
    if not steps and source != "error":
        source = "empty"
        message = "模型未返回可用步骤"
    message = localized_workflow_message(message, accept_language, "Workflow generation failed")
    return ApiResponse(
        code=0,
        message=message,
        data={
            "steps": [{"id": f"step_{idx + 1}", "text": text} for idx, text in enumerate(steps[:max_steps])],
            "source": source,
            "message": message,
        },
    )


@router.post("/skills/generate-workflow-nodes", response_model=ApiResponse)
async def generate_workflow_nodes(payload: WorkflowNodesGenerateRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill name is required")
    max_nodes = _resolved_workflow_node_count(payload)
    source = "llm"
    message = "success"
    try:
        nodes = await _generate_workflow_nodes_with_llm(payload)
    except Exception as exc:
        log_print(f"[skills] generate_workflow_nodes failed: {exc}", flush=True)
        nodes = []
        source = "error"
        message = str(exc) or "生成失败"
    if not nodes and source != "error":
        source = "empty"
        message = "模型未返回可用节点"
    message = localized_workflow_message(message, accept_language, "Workflow generation failed")
    return ApiResponse(
        code=0,
        message=message,
        data={
            "nodes": nodes[:max_nodes],
            "source": source,
            "message": message,
        },
    )


@router.post("/skills/polish-workflow-node", response_model=ApiResponse)
async def polish_workflow_node(payload: WorkflowNodePolishRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill name is required")
    source = "llm"
    message = "success"
    try:
        text = await _polish_workflow_node_with_llm(payload)
    except Exception as exc:
        log_print(f"[skills] polish_workflow_node failed: {exc}", flush=True)
        text = ""
        source = "error"
        message = str(exc) or "润色失败"
    if not text and source != "error":
        source = "empty"
        message = "模型未返回可用节点要求"
    message = localized_workflow_message(message, accept_language, "Failed to refine the node requirement")
    return ApiResponse(
        code=0,
        message=message,
        data={
            "text": text,
            "source": source,
            "message": message,
        },
    )


@router.post("/skills/check-workflow-logic", response_model=ApiResponse)
async def check_workflow_logic(payload: WorkflowLogicCheckRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill name is required")
    source = "llm"
    message = "success"
    try:
        result = await _check_workflow_logic_with_llm(payload, accept_language)
    except Exception as exc:
        log_print(f"[skills] check_workflow_logic failed: {exc}", flush=True)
        result = {}
        source = "error"
        message = str(exc) or "检查失败"
    message = localized_workflow_message(message, accept_language, "Workflow check failed")
    return ApiResponse(
        code=0,
        message=message,
        data={
            **result,
            "source": source,
            "message": message,
        },
    )


@router.post("/skills/check-workflow-nodes", response_model=ApiResponse)
async def check_workflow_nodes(payload: WorkflowLogicCheckRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill name is required")
    source = "llm"
    message = "success"
    try:
        normalized_nodes = [
            node for idx, raw in enumerate(list(payload.nodes or []))
            for node in [_normalize_workflow_node(raw, idx)]
            if node
        ]
        node_steps = [
            "：".join([str(node.get("title") or "").strip(), str(node.get("description") or "").strip()]).strip("：")
            for node in normalized_nodes
        ]
        enriched_payload = payload.model_copy(update={
            "nodes": normalized_nodes,
            "steps": [str(item or "").strip() for item in (payload.steps or node_steps) if str(item or "").strip()],
        })
        result = await _check_workflow_logic_with_llm(enriched_payload, accept_language)
    except Exception as exc:
        log_print(f"[skills] check_workflow_nodes failed: {exc}", flush=True)
        result = {}
        source = "error"
        message = str(exc) or "检查失败"
    message = localized_workflow_message(message, accept_language, "Workflow check failed")
    return ApiResponse(
        code=0,
        message=message,
        data={
            **result,
            "source": source,
            "message": message,
        },
    )


@router.post("/skills/check-script-plugin", response_model=ApiResponse)
async def check_script_plugin(payload: ScriptPluginCheckRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    static_result = _validate_script_plugin_static(payload.code)
    source = "rules"
    message = "success"
    llm_result = None
    if static_result.get("rulePass"):
        source = "rules+llm"
        try:
            llm_result = await _review_script_plugin_with_llm(payload, static_result, accept_language)
        except Exception as exc:
            log_print(f"[skills] check_script_plugin llm review failed: {exc}", flush=True)
            source = "rules"
            message = "规则检测通过，LLM 审查暂不可用"
            llm_result = {
                "pass": True,
                "level": "warning",
                "summary": "规则检测已通过，但 LLM 审查暂不可用。",
                "risks": [],
                "suggestions": [],
            }
    else:
        message = "规则检测未通过"
    message = localized_workflow_message(message, accept_language, "Script validation failed")
    if llm_result is not None and source == "rules":
        llm_result["summary"] = localized_workflow_message(
            str(llm_result.get("summary") or ""), accept_language, "LLM review is unavailable"
        )
    return ApiResponse(
        code=0,
        message=message,
        data={
            **localize_script_check(static_result, accept_language),
            "pass": bool(static_result.get("rulePass")),
            "llm": llm_result,
            "source": source,
            "message": message,
        },
    )


@router.post("/skills/fix-script-plugin", response_model=ApiResponse)
async def fix_script_plugin(payload: ScriptPluginFixRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    static_result = _validate_script_plugin_static(payload.code)
    try:
        fixed = await _fix_script_plugin_with_llm(payload, static_result)
    except Exception as exc:
        log_print(f"[skills] fix_script_plugin failed: {exc}", flush=True)
        raise HTTPException(status_code=500, detail=str(exc) or "修复失败")
    fixed_code = str(fixed.get("code") or "").strip()
    if not fixed_code:
        raise HTTPException(status_code=500, detail="模型未返回可用代码")
    recheck = _validate_script_plugin_static(fixed_code)
    return ApiResponse(
        code=0,
        message="success",
        data={
            "code": fixed_code,
            "notes": fixed.get("notes") or [],
            "check": localize_script_check(recheck, accept_language),
        },
    )


@router.post("/skills/generate-script-plugin", response_model=ApiResponse)
async def generate_script_plugin(payload: ScriptPluginGenerateRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    try:
        generated = await _generate_script_plugin_with_llm(payload)
    except Exception as exc:
        log_print(f"[skills] generate_script_plugin failed: {exc}", flush=True)
        raise HTTPException(status_code=500, detail=str(exc) or "生成失败")
    code = str(generated.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=500, detail="模型未返回可用代码")
    check = _validate_script_plugin_static(code)
    hardcode_warnings = _generated_code_hardcode_warnings(code, payload.processing_instruction)
    if hardcode_warnings:
        check["warnings"] = [*(check.get("warnings") or []), *hardcode_warnings][:50]
    return ApiResponse(
        code=0,
        message="success",
        data={
            "code": code,
            "notes": generated.get("notes") or [],
            "check": localize_script_check(check, accept_language),
        },
    )


@router.get("/skills", response_model=ApiResponse)
async def list_skills(
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    main_id = main_id_snake or main_id
    from app.services.skill_sharing.legacy_migration import legacy_skill_share_migration
    await legacy_skill_share_migration.migrate_owned(main_id=main_id, owner_user_id=user_id)
    await legacy_skill_share_migration.migrate_installed(main_id=main_id, recipient_user_id=user_id)
    skills = await user_skill_service.list_skills(user_id, main_id=main_id)
    await attach_environment_status(skills)
    from app.services.resource_feedback.summary import skill_feedback_summary_service
    await skill_feedback_summary_service.attach(main_id=main_id, user_id=user_id, skills=skills)
    return ApiResponse(code=0, message="success", data=[_admin_shape_skill(item) for item in skills])


@router.get("/skills/selectable", response_model=ApiResponse)
async def list_selectable_skills(
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
    scope: str = Query("all"),
    keyword: str = Query(""),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
) -> ApiResponse:
    resolved_main_id = main_id_snake or main_id
    source_scope = str(scope or "all").strip().lower()
    if source_scope not in {"all", "user", "organization"}:
        source_scope = "all"
    try:
        user_skills = await user_skill_service.list_skills(user_id, main_id=resolved_main_id)
    except Exception:
        user_skills = []
    try:
        org_skills = await organization_skill_adapter.list_runtime_skills(main_id=resolved_main_id)
    except Exception:
        org_skills = []
    organization_ids = [
        str(skill.get("id") or skill.get("_id") or "").strip()
        for skill in org_skills or []
        if isinstance(skill, dict)
    ]
    allowed_organization_ids = await filter_allowed_resource_ids(
        "skill",
        main_id=resolved_main_id,
        user_id=user_id,
        resource_ids=organization_ids,
    )

    from app.dsh_runtime.profile.skills.execution_access import skill_execution_is_allowed

    items: List[Dict[str, Any]] = []
    await attach_environment_status(list(user_skills or []) + list(org_skills or []))
    seen: set[str] = set()
    for skill in list(user_skills or []) + list(org_skills or []):
        if not isinstance(skill, dict):
            continue
        if not _safe_bool(skill.get("enabled"), _safe_bool(skill.get("is_active"), True)):
            continue
        skill_id = str(skill.get("id") or skill.get("_id") or "").strip()
        if _skill_source_scope(skill) == "organization" and skill_id not in allowed_organization_ids:
            continue
        if not skill_id or skill_id in seen:
            continue
        current_scope = _skill_source_scope(skill)
        if source_scope != "all" and current_scope != source_scope:
            continue
        if not _matches_skill_keyword(skill, keyword):
            continue
        seen.add(skill_id)
        execution_allowed = await skill_execution_is_allowed(
            row=skill, tenant_id=resolved_main_id, user_id=user_id,
        )
        environment_status_value = str(skill.get("environment_status") or "")
        environment_ready = environment_status_value in {"", "ready"} or bool(skill.get("pending_package"))
        available = execution_allowed and environment_ready
        items.append({
            **_selectable_skill_item(skill),
            "available": available,
            "unavailableReason": (
                "execution_access" if not execution_allowed else
                f"environment_{environment_status_value}" if not environment_ready else ""
            ),
        })

    offset = _cursor_offset(cursor)
    page = items[offset:offset + limit]
    next_offset = offset + len(page)
    has_more = next_offset < len(items)
    return ApiResponse(
        code=0,
        message="success",
        data={
            "items": page,
            "nextCursor": str(next_offset) if has_more else "",
            "hasMore": has_more,
        },
    )


async def _validate_personal_workflow_documents(
    payload: AdminShapeSkillPayload, *, main_id: str, user_id: str,
) -> None:
    if payload.type != "workflow":
        return
    try:
        await validate_personal_workflow_documents(
            main_id=main_id, user_id=user_id, nodes=_workflow_nodes(payload.config),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="无权使用所选知识文档，请重新选择") from exc
    except LookupError as exc:
        raise HTTPException(status_code=409, detail="所选知识文档已删除或尚未解析，请重新选择") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="请先选择要读取的知识文档") from exc


@router.post("/skills", response_model=ApiResponse)
async def create_admin_shape_skill(
    payload: AdminShapeSkillPayload,
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    resolved_main_id = main_id_snake or main_id
    await _validate_personal_workflow_documents(payload, main_id=resolved_main_id, user_id=user_id)
    created = await user_skill_service.create_skill(
        user_id,
        _admin_shape_payload_to_user_payload(payload, user_id=user_id, main_id=resolved_main_id),
    )
    from app.services.skill_lifecycle import SkillLifecycleService
    lifecycle = SkillLifecycleService()
    await lifecycle.initialize_draft(
        main_id=resolved_main_id,
        user_id=user_id,
        skill_id=str(created.get("id") or ""),
        draft=created,
        new_skill=True,
    )
    current = await user_skill_service.get_skill(user_id, str(created.get("id") or ""), main_id=resolved_main_id)
    return ApiResponse(code=0, message="success", data=_admin_shape_skill(current or created))


@router.get("/skills/{skill_id}", response_model=ApiResponse)
async def get_skill(
    skill_id: str,
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    resolved_main_id = main_id_snake or main_id
    skill = await user_skill_service.get_skill(user_id, skill_id, main_id=resolved_main_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return ApiResponse(code=0, message="success", data=_admin_shape_skill(skill))


@router.put("/skills/{skill_id}", response_model=ApiResponse)
async def update_skill(
    skill_id: str,
    payload: AdminShapeSkillPayload,
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    resolved_main_id = main_id_snake or main_id
    updates = _admin_shape_payload_to_user_payload(payload, user_id=user_id, main_id=resolved_main_id)
    from app.services.skill_lifecycle import SkillLifecycleError, SkillLifecycleService
    current = await user_skill_service.get_skill(user_id, skill_id, main_id=resolved_main_id)
    if not current:
        raise HTTPException(status_code=404, detail="Skill not found")
    if updates.get("enabled") and await environment_status(current) not in {None, "ready"}:
        raise HTTPException(status_code=409, detail="Skill environment is not ready")
    await _validate_personal_workflow_documents(payload, main_id=resolved_main_id, user_id=user_id)
    lifecycle = SkillLifecycleService()
    if not lifecycle.is_platform_skill(current):
        updated = await user_skill_service.update_skill(user_id, skill_id, updates, main_id=resolved_main_id)
        return ApiResponse(code=0, message="success", data=_admin_shape_skill(updated or current))
    try:
        await lifecycle.save_draft(
            main_id=resolved_main_id, user_id=user_id, skill_id=skill_id, draft=updates,
        )
    except SkillLifecycleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc
    updated = await user_skill_service.get_skill(user_id, skill_id, main_id=resolved_main_id)
    return ApiResponse(code=0, message="success", data=_admin_shape_skill(updated or {}))


@router.patch("/skills/{skill_id}/enabled", response_model=ApiResponse)
async def set_skill_enabled(
    skill_id: str,
    payload: SkillEnabledPayload,
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    resolved_main_id = main_id_snake or main_id
    current = await user_skill_service.get_skill(user_id, skill_id, main_id=resolved_main_id)
    if not current:
        raise HTTPException(status_code=404, detail="Skill not found")
    if payload.enabled and str(current.get("publication_status") or "") == "draft" and not current.get("published_version"):
        raise HTTPException(status_code=409, detail={
            "code": "skill_publish_required", "message": "Publish this Skill before enabling it",
        })
    if payload.enabled and await environment_status(current) not in {None, "ready"}:
        raise HTTPException(status_code=409, detail="Skill environment is not ready")
    updated = await user_skill_service.set_skill_enabled(
        user_id, skill_id, bool(payload.enabled), main_id=resolved_main_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Skill not found")
    updated["environment_status"] = await environment_status(updated)
    return ApiResponse(code=0, message="success", data=_admin_shape_skill(updated))


@router.delete("/skills/{skill_id}", response_model=ApiResponse)
async def delete_skill(
    skill_id: str,
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    main_id = main_id_snake or main_id
    ok = await user_skill_service.delete_skill(user_id, skill_id, main_id=main_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Skill not found")
    return ApiResponse(code=0, message="success", data={"id": skill_id})
