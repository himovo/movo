from __future__ import annotations

import datetime
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_admin_user
from app.api.time_utils import utc_iso
from app.core.config import settings
from app.core.db import get_db

router = APIRouter()

SKILL_TYPES = {"writing_style", "workflow"}


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _time_text(value: Any) -> str:
    return utc_iso(value)


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _safe_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return default


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc.get("_id") or ""),
        "mainId": str(doc.get("main_id") or "default"),
        "name": str(doc.get("name") or ""),
        "description": str(doc.get("description") or ""),
        "scenario": str(doc.get("scenario") or ""),
        "type": str(doc.get("type") or "writing_style"),
        "config": _safe_dict(doc.get("config")),
        "enabled": _safe_bool(doc.get("enabled"), True),
        "createdAt": _time_text(doc.get("created_at")),
        "updatedAt": _time_text(doc.get("updated_at")),
    }


def _backend_url(path: str, main_id: str) -> str:
    base_url = str(settings.backend_base_url or "http://127.0.0.1:8000").rstrip("/")
    separator = "&" if "?" in path else "?"
    return f"{base_url}/api{path}{separator}{urllib.parse.urlencode({'mainId': main_id})}"


def _request_backend(method: str, path: str, main_id: str, body: Any | None = None) -> Any:
    data = None
    headers = {
        "Accept": "application/json",
        "X-MOVO-Service-Token": settings.backend_service_token,
    }
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(_backend_url(path, main_id), data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            message = parsed.get("detail") or parsed.get("message") or detail
        except json.JSONDecodeError:
            message = detail or str(exc)
        raise HTTPException(status_code=exc.code, detail=message) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"backend 不可用：{exc.reason}") from exc
    return json.loads(raw) if raw else {"code": 0, "data": None}


def _backend_data(response: Any) -> Any:
    if isinstance(response, dict) and "data" in response:
        return response.get("data")
    return response


def _normalize_writing_style_config(*, main_id: str, name: str, description: str, scenario: str, config: dict[str, Any]) -> dict[str, Any]:
    normalized = _safe_dict(config)
    contract_json = _safe_dict(normalized.get("contractJson") or normalized.get("contract_json"))
    normalized.pop("compiledPrompt", None)
    normalized.pop("compiled_prompt", None)
    if contract_json:
        normalized["contractJson"] = contract_json
    return normalized


def _normalize_payload(payload: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    if not partial or "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="技能名称不能为空")
        patch["name"] = name[:120]
    if not partial or "description" in payload:
        patch["description"] = str(payload.get("description") or "").strip()
    if not partial or "scenario" in payload:
        patch["scenario"] = str(payload.get("scenario") or "").strip()
    if not partial or "type" in payload:
        skill_type = str(payload.get("type") or "writing_style").strip().lower()
        if skill_type not in SKILL_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="技能类型只支持 writing_style 或 workflow")
        patch["type"] = skill_type
    if not partial or "config" in payload:
        patch["config"] = _safe_dict(payload.get("config"))
    if not partial or "enabled" in payload:
        patch["enabled"] = _safe_bool(payload.get("enabled"), False)
    return patch


class SkillPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    scenario: str = ""
    type: str = Field(default="writing_style", pattern=r"^(writing_style|workflow)$")
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = False


class SkillEnabledPayload(BaseModel):
    enabled: bool


class WorkflowStepsGeneratePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    scenario: str = ""
    existingSteps: list[str] = Field(default_factory=list)
    maxSteps: int = Field(default=8, ge=4, le=10)
    mode: str = "generate"
    supplement: str = ""


class WorkflowNodesGeneratePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    scenario: str = ""
    existingNodes: list[dict[str, Any]] = Field(default_factory=list)
    maxNodes: int = Field(default=8, ge=4, le=12)
    mode: str = "generate"
    supplement: str = ""
    nodeCatalog: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowLogicCheckPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    scenario: str = ""
    steps: list[str] = Field(default_factory=list)
    nodes: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowNodePolishPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    scenario: str = ""
    node: dict[str, Any] = Field(default_factory=dict)
    existingNodes: list[dict[str, Any]] = Field(default_factory=list)
    nodeCatalog: list[dict[str, Any]] = Field(default_factory=list)


class ScriptPluginCheckPayload(BaseModel):
    code: str = Field(min_length=1, max_length=262144)
    nodeTitle: str = ""
    nodeDescription: str = ""


class ScriptPluginFixPayload(ScriptPluginCheckPayload):
    issues: list[dict[str, Any]] = Field(default_factory=list)


class ScriptPluginGeneratePayload(BaseModel):
    processingInstruction: str = Field(min_length=1, max_length=8000)
    nodeTitle: str = ""
    nodeDescription: str = ""
    skillName: str = ""
    skillDescription: str = ""
    scenario: str = ""
    selectedInputSource: str = "all"
    selectedInputTypes: list[str] = Field(default_factory=list)
    workflowNodes: list[dict[str, Any]] = Field(default_factory=list)


class WritingStyleEnrichPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    scenario: str = ""
    draft: dict[str, Any] = Field(default_factory=dict)


@router.get("")
async def list_skills(current_user: dict = Depends(get_current_admin_user)) -> list[dict[str, Any]]:
    main_id = str(current_user.get("main_id") or "default")
    db = get_db()
    cursor = db.skills.find({"main_id": main_id}).sort("updated_at", -1)
    return [_serialize(doc) async for doc in cursor]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_skill(payload: SkillPayload, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    db = get_db()
    now = _now()
    normalized_payload = _normalize_payload(payload.model_dump())
    if str(normalized_payload.get("type") or "") == "writing_style":
        normalized_payload["config"] = _normalize_writing_style_config(
            main_id=main_id,
            name=str(normalized_payload.get("name") or ""),
            description=str(normalized_payload.get("description") or ""),
            scenario=str(normalized_payload.get("scenario") or ""),
            config=_safe_dict(normalized_payload.get("config")),
        )
    doc = {
        "_id": uuid.uuid4().hex,
        "main_id": main_id,
        **normalized_payload,
        "created_at": now,
        "updated_at": now,
    }
    await db.skills.insert_one(doc)
    return _serialize(doc)


@router.post("/generate-workflow-steps")
async def generate_workflow_steps(payload: WorkflowStepsGeneratePayload, current_user: dict = Depends(get_current_admin_user)) -> Any:
    main_id = str(current_user.get("main_id") or "default")
    body = payload.model_dump()
    body["existing_steps"] = _safe_list(body.pop("existingSteps", []))
    max_steps = body.pop("maxSteps", None)
    if max_steps is not None:
        body["max_steps"] = max_steps
    try:
        return _backend_data(_request_backend("POST", "/skills/generate-workflow-steps", main_id, body))
    except HTTPException as exc:
        return {
            "steps": [],
            "source": "error",
            "message": str(exc.detail or "生成服务不可用"),
        }


@router.post("/generate-workflow-nodes")
async def generate_workflow_nodes(payload: WorkflowNodesGeneratePayload, current_user: dict = Depends(get_current_admin_user)) -> Any:
    main_id = str(current_user.get("main_id") or "default")
    body = payload.model_dump()
    body["existing_nodes"] = _safe_list(body.pop("existingNodes", []))
    body["node_catalog"] = _safe_list(body.pop("nodeCatalog", []))
    max_nodes = body.pop("maxNodes", None)
    if max_nodes is not None:
        body["max_nodes"] = max_nodes
    try:
        return _backend_data(_request_backend("POST", "/skills/generate-workflow-nodes", main_id, body))
    except HTTPException as exc:
        return {
            "nodes": [],
            "source": "error",
            "message": str(exc.detail or "生成服务不可用"),
        }


@router.post("/polish-workflow-node")
async def polish_workflow_node(payload: WorkflowNodePolishPayload, current_user: dict = Depends(get_current_admin_user)) -> Any:
    main_id = str(current_user.get("main_id") or "default")
    body = payload.model_dump()
    body["existing_nodes"] = _safe_list(body.pop("existingNodes", []))
    body["node_catalog"] = _safe_list(body.pop("nodeCatalog", []))
    try:
        return _backend_data(_request_backend("POST", "/skills/polish-workflow-node", main_id, body))
    except HTTPException as exc:
        return {
            "text": "",
            "source": "error",
            "message": str(exc.detail or "润色服务不可用"),
        }


@router.post("/check-workflow-logic")
async def check_workflow_logic(payload: WorkflowLogicCheckPayload, current_user: dict = Depends(get_current_admin_user)) -> Any:
    main_id = str(current_user.get("main_id") or "default")
    body = payload.model_dump()
    try:
        return _backend_data(_request_backend("POST", "/skills/check-workflow-logic", main_id, body))
    except HTTPException as exc:
        return {
            "pass": False,
            "logic": {
                "label": "检查失败",
                "level": "warning",
                "summary": str(exc.detail or "检查服务不可用"),
            },
            "coverage": [],
            "readiness": [],
            "suggestions": ["后端检查服务暂不可用，请稍后重试。"],
            "conclusion": "本次未完成后端语义检查。",
            "source": "error",
            "message": str(exc.detail or "检查服务不可用"),
        }


@router.post("/check-workflow-nodes")
async def check_workflow_nodes(payload: WorkflowLogicCheckPayload, current_user: dict = Depends(get_current_admin_user)) -> Any:
    main_id = str(current_user.get("main_id") or "default")
    body = payload.model_dump()
    try:
        return _backend_data(_request_backend("POST", "/skills/check-workflow-nodes", main_id, body))
    except HTTPException as exc:
        return {
            "pass": False,
            "logic": {
                "label": "检查失败",
                "level": "warning",
                "summary": str(exc.detail or "检查服务不可用"),
            },
            "coverage": [],
            "readiness": [],
            "suggestions": ["后端检查服务暂不可用，请稍后重试。"],
            "conclusion": "本次未完成后端语义节点检查。",
            "source": "error",
            "message": str(exc.detail or "检查服务不可用"),
        }


@router.post("/check-script-plugin")
async def check_script_plugin(payload: ScriptPluginCheckPayload, current_user: dict = Depends(get_current_admin_user)) -> Any:
    main_id = str(current_user.get("main_id") or "default")
    return _backend_data(_request_backend("POST", "/skills/check-script-plugin", main_id, payload.model_dump()))


@router.post("/fix-script-plugin")
async def fix_script_plugin(payload: ScriptPluginFixPayload, current_user: dict = Depends(get_current_admin_user)) -> Any:
    main_id = str(current_user.get("main_id") or "default")
    return _backend_data(_request_backend("POST", "/skills/fix-script-plugin", main_id, payload.model_dump()))


@router.post("/generate-script-plugin")
async def generate_script_plugin(payload: ScriptPluginGeneratePayload, current_user: dict = Depends(get_current_admin_user)) -> Any:
    main_id = str(current_user.get("main_id") or "default")
    return _backend_data(_request_backend("POST", "/skills/generate-script-plugin", main_id, payload.model_dump()))


@router.post("/enrich-writing-style")
async def enrich_writing_style(payload: WritingStyleEnrichPayload, current_user: dict = Depends(get_current_admin_user)) -> Any:
    main_id = str(current_user.get("main_id") or "default")
    draft = _safe_dict(payload.draft)
    body = {
        "user_id": "organization",
        "name": payload.name,
        "description": payload.description,
        "skill_type": "style",
        "input_profile": {
            "skill_type": "style",
            "name": payload.name,
            "summary": payload.description,
            "applicable_scenarios": payload.scenario,
            "publish_channel": _safe_list(draft.get("publishChannel")),
            "content_form": _safe_list(draft.get("contentForm")),
            "target_audience": _safe_list(draft.get("targetAudience")),
            "preferred_style": _safe_list(draft.get("preferredStyle")),
            "target_length": _safe_dict(draft.get("targetLength")),
            "section_structure": _safe_list(draft.get("sectionStructure")),
            "required_sections": _safe_list(draft.get("requiredSections")),
            "required_elements": _safe_list(draft.get("requiredElements")),
            "forbidden_elements": _safe_list(draft.get("forbiddenElements")),
            "notes": str(draft.get("notes") or "").strip(),
        },
    }
    try:
        data = _backend_data(_request_backend("POST", "/skills/enrich_draft", main_id, body))
    except HTTPException as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc.detail or "写作规范补全失败")) from exc
    if not isinstance(data, dict):
        return {"inputProfile": body["input_profile"], "contractJson": body["input_profile"], "skillMarkdown": ""}
    normalized_config = _normalize_writing_style_config(
        main_id=main_id,
        name=payload.name,
        description=payload.description,
        scenario=payload.scenario,
        config={"contractJson": _safe_dict(data.get("contract_json"))},
    )
    return {
        "inputProfile": _safe_dict(data.get("input_profile")),
        "contractJson": _safe_dict(normalized_config.get("contractJson") or data.get("contract_json")),
        "skillMarkdown": str(data.get("skill_markdown") or ""),
    }


@router.get("/{skill_id}")
async def get_skill(skill_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    db = get_db()
    doc = await db.skills.find_one({"_id": str(skill_id), "main_id": main_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="技能不存在")
    return _serialize(doc)


@router.put("/{skill_id}")
async def update_skill(skill_id: str, payload: SkillPayload, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    db = get_db()
    normalized_payload = _normalize_payload(payload.model_dump())
    if str(normalized_payload.get("type") or "") == "writing_style":
        normalized_payload["config"] = _normalize_writing_style_config(
            main_id=main_id,
            name=str(normalized_payload.get("name") or ""),
            description=str(normalized_payload.get("description") or ""),
            scenario=str(normalized_payload.get("scenario") or ""),
            config=_safe_dict(normalized_payload.get("config")),
        )
    patch = {**normalized_payload, "updated_at": _now()}
    result = await db.skills.update_one({"_id": str(skill_id), "main_id": main_id}, {"$set": patch})
    if not result.matched_count:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="技能不存在")
    doc = await db.skills.find_one({"_id": str(skill_id), "main_id": main_id})
    return _serialize(doc or {})


@router.patch("/{skill_id}/enabled")
async def set_skill_enabled(
    skill_id: str,
    payload: SkillEnabledPayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    db = get_db()
    result = await db.skills.update_one(
        {"_id": str(skill_id), "main_id": main_id},
        {"$set": {"enabled": bool(payload.enabled), "updated_at": _now()}},
    )
    if not result.matched_count:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="技能不存在")
    doc = await db.skills.find_one({"_id": str(skill_id), "main_id": main_id})
    return _serialize(doc or {})


@router.delete("/{skill_id}")
async def delete_skill(skill_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, str]:
    main_id = str(current_user.get("main_id") or "default")
    db = get_db()
    result = await db.skills.delete_one({"_id": str(skill_id), "main_id": main_id})
    if not result.deleted_count:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="技能不存在")
    return {"id": skill_id}


async def ensure_indexes() -> None:
    db = get_db()
    await db.skills.create_index([("main_id", 1), ("updated_at", -1)], name="skills_main_updated")
    await db.skills.create_index([("main_id", 1), ("name", 1)], name="skills_main_name")
    await db.skills.create_index([("main_id", 1), ("enabled", 1), ("updated_at", -1)], name="skills_main_enabled_updated")
