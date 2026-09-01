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
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from pydantic import AliasChoices, BaseModel, Field

from app.api.time_utils import utc_iso
from app.services.skill_assets.trajectory_distiller import distill_trajectory, refine_steps
from app.services.skills import user_skill_service
from app.services.org_skill_adapter import _workflow_markdown, _workflow_nodes, organization_skill_adapter
from app.core.config import get_settings
from app.llm.factory import get_llm_client
from app.llm.types import Message, Role
from app.utils.oss_uploader import AliyunOSSUploader
from app.utils.uploads import read_upload_with_limit
from app.governance.position_policy import MongoEmployeePolicyResolver
from app.api.principal import require_api_principal

import yaml as _yaml


router = APIRouter(dependencies=[Depends(require_api_principal)])


def _encode_composite_yaml(
    *,
    name: str,
    description: str,
    triggers: List[str],
    steps: List[Dict[str, Any]],
) -> str:
    """Serialize composite-skill fields as YAML frontmatter markdown.

    Mirrors ``frontend/src/api/compositeSkill.ts::encodeCompositeSkill``
    but routes through PyYAML so arbitrary strings survive safely."""
    payload: Dict[str, Any] = {"name": name}
    if description:
        payload["description"] = description
    if triggers:
        payload["triggers"] = list(triggers)
    payload["steps"] = list(steps)
    body = _yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    return f"---\n{body}---\n"

class ApiResponse(BaseModel):
    code: int = 0
    message: Optional[str] = None
    data: Optional[object] = None


class SkillGenerateRequest(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    main_id: Optional[str] = Field(None, validation_alias=AliasChoices("main_id", "mainId"), description="Tenant / main account ID")
    name: str = Field(..., description="Skill name")
    description: Optional[str] = Field(default="", description="Skill description")
    summary: Optional[str] = Field(default="", description="Short summary")
    category: Optional[str] = Field(default="document", description="Skill category")
    role: Optional[str] = Field(default=None, description="Skill role: execution/renderer/style")
    skill_type: Optional[str] = Field(default="style", description="Skill type: style/execution/renderer/composite_task")
    tags: Optional[List[str]] = Field(default_factory=list, description="Skill tags")
    visibility: Optional[str] = Field(default="private", description="Visibility")
    formats: Optional[List[str]] = Field(default_factory=list, description="Supported formats")
    notes: Optional[str] = Field(default="", description="Additional notes")
    sources: Optional[List[str]] = Field(default_factory=list, description="OSS object paths for source docs")
    resources: Optional[Dict[str, List[Dict[str, str]]]] = Field(
        default_factory=dict, description="Typed resources"
    )
    skill_markdown: Optional[str] = Field(default="", description="User provided SKILL.md")
    input_profile: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Structured user input profile")
    contract_json: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Structured skill contract")
    advanced: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Advanced settings")
    is_active: Optional[bool] = Field(default=False, description="Whether the skill is selectable")


class SkillUpdateRequest(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    main_id: Optional[str] = Field(None, validation_alias=AliasChoices("main_id", "mainId"), description="Tenant / main account ID")
    name: Optional[str] = Field(None, description="Skill name")
    description: Optional[str] = Field(None, description="Skill description")
    summary: Optional[str] = Field(None, description="Short summary")
    category: Optional[str] = Field(None, description="Skill category")
    role: Optional[str] = Field(None, description="Skill role: execution/renderer/style")
    skill_type: Optional[str] = Field(None, description="Skill type: style/execution/renderer/composite_task")
    tags: Optional[List[str]] = Field(default=None, description="Skill tags")
    visibility: Optional[str] = Field(None, description="Visibility")
    formats: Optional[List[str]] = Field(default=None, description="Supported formats")
    notes: Optional[str] = Field(None, description="Additional notes")
    resources: Optional[Dict[str, List[Dict[str, str]]]] = Field(default=None, description="Typed resources")
    skill_markdown: Optional[str] = Field(None, description="Updated SKILL.md")
    input_profile: Optional[Dict[str, Any]] = Field(default=None, description="Structured user input profile")
    contract_json: Optional[Dict[str, Any]] = Field(default=None, description="Structured skill contract")
    advanced: Optional[Dict[str, Any]] = Field(default=None, description="Advanced settings")
    is_active: Optional[bool] = Field(None, description="Whether the skill is selectable")


class SkillListRequest(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    main_id: Optional[str] = Field(None, validation_alias=AliasChoices("main_id", "mainId"), description="Tenant / main account ID")


class AdminShapeSkillPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    scenario: str = ""
    type: str = Field(default="writing_style", pattern=r"^(writing_style|workflow)$")
    config: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = False


class SkillEnabledPayload(BaseModel):
    enabled: bool


class RecordingEventModel(BaseModel):
    type: str = Field(..., description="click | fill | navigate | select")
    url: Optional[str] = Field(default="")
    value: Optional[str] = Field(default="")
    target: Optional[Dict[str, Any]] = Field(default_factory=dict)
    instruction: Optional[str] = Field(default="")


class RecordingEditModel(BaseModel):
    op: str = Field(..., description="delete | set_instruction | set_variable")
    index: int = Field(..., ge=0)
    value: Optional[str] = Field(default=None)
    field: Optional[str] = Field(default=None)
    var: Optional[str] = Field(default=None)


class SkillFromRecordingRequest(BaseModel):
    user_id: str = Field(...)
    main_id: Optional[str] = Field(None, validation_alias=AliasChoices("main_id", "mainId"))
    name: str = Field(...)
    description: Optional[str] = Field(default="")
    triggers: Optional[List[str]] = Field(default_factory=list)
    site_profile_id: Optional[str] = Field(default="")
    events: List[RecordingEventModel] = Field(default_factory=list)
    edits: Optional[List[RecordingEditModel]] = Field(default_factory=list)
    variables: Optional[Dict[str, str]] = Field(default_factory=dict)
    visibility: Optional[str] = Field(default="private")
    is_active: Optional[bool] = Field(default=False)


class SkillEnrichRequest(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    main_id: Optional[str] = Field(None, validation_alias=AliasChoices("main_id", "mainId"), description="Tenant / main account ID")
    name: str = Field(..., description="Skill name")
    description: Optional[str] = Field(default="", description="Skill description")
    skill_type: Optional[str] = Field(default="style", description="Skill type")
    input_profile: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Structured user input profile")


class WorkflowStepsGenerateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Workflow skill name")
    description: Optional[str] = Field(default="", description="Skill description")
    scenario: Optional[str] = Field(default="", description="Applicable business scenario")
    existing_steps: Optional[List[str]] = Field(default_factory=list, validation_alias=AliasChoices("existing_steps", "existingSteps"))
    max_steps: Optional[int] = Field(default=8, validation_alias=AliasChoices("max_steps", "maxSteps"))
    mode: Optional[str] = Field(default="generate", description="generate | optimize | supplement | supplement_step")
    supplement: Optional[str] = Field(default="", description="New business point to supplement into existing steps")
    node_catalog: Optional[List[Dict[str, Any]]] = Field(default_factory=list, validation_alias=AliasChoices("node_catalog", "nodeCatalog"))


class WorkflowNodesGenerateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Workflow skill name")
    description: Optional[str] = Field(default="", description="Skill description")
    scenario: Optional[str] = Field(default="", description="Applicable business scenario")
    existing_nodes: Optional[List[Dict[str, Any]]] = Field(default_factory=list, validation_alias=AliasChoices("existing_nodes", "existingNodes"))
    max_nodes: Optional[int] = Field(default=8, validation_alias=AliasChoices("max_nodes", "maxNodes"))
    mode: Optional[str] = Field(default="generate", description="generate | optimize | supplement | supplement_step")
    supplement: Optional[str] = Field(default="", description="New business point to supplement into existing nodes")
    node_catalog: Optional[List[Dict[str, Any]]] = Field(default_factory=list, validation_alias=AliasChoices("node_catalog", "nodeCatalog"))


class WorkflowNodePolishRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Workflow skill name")
    description: Optional[str] = Field(default="", description="Skill description")
    scenario: Optional[str] = Field(default="", description="Applicable business scenario")
    node: Dict[str, Any] = Field(default_factory=dict, description="Current workflow node")
    existing_nodes: Optional[List[Dict[str, Any]]] = Field(default_factory=list, validation_alias=AliasChoices("existing_nodes", "existingNodes"))
    node_catalog: Optional[List[Dict[str, Any]]] = Field(default_factory=list, validation_alias=AliasChoices("node_catalog", "nodeCatalog"))


class WorkflowLogicCheckRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Workflow skill name")
    description: Optional[str] = Field(default="", description="Skill description")
    scenario: Optional[str] = Field(default="", description="Applicable business scenario")
    steps: List[str] = Field(default_factory=list, description="Current natural language workflow steps")
    nodes: List[Dict[str, Any]] = Field(default_factory=list, description="Current semantic workflow nodes")


class ScriptPluginCheckRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=262144, description="Python script plugin code")
    node_title: Optional[str] = Field(default="", validation_alias=AliasChoices("node_title", "nodeTitle"))
    node_description: Optional[str] = Field(default="", validation_alias=AliasChoices("node_description", "nodeDescription"))


class ScriptPluginFixRequest(ScriptPluginCheckRequest):
    issues: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Current check issues")


class ScriptPluginGenerateRequest(BaseModel):
    processing_instruction: str = Field(..., min_length=1, max_length=8000, validation_alias=AliasChoices("processing_instruction", "processingInstruction"))
    node_title: Optional[str] = Field(default="", validation_alias=AliasChoices("node_title", "nodeTitle"))
    node_description: Optional[str] = Field(default="", validation_alias=AliasChoices("node_description", "nodeDescription"))
    skill_name: Optional[str] = Field(default="", validation_alias=AliasChoices("skill_name", "skillName"))
    skill_description: Optional[str] = Field(default="", validation_alias=AliasChoices("skill_description", "skillDescription"))
    scenario: Optional[str] = Field(default="", description="Applicable business scenario")
    selected_input_source: Optional[str] = Field(default="all", validation_alias=AliasChoices("selected_input_source", "selectedInputSource"))
    selected_input_types: Optional[List[str]] = Field(default_factory=list, validation_alias=AliasChoices("selected_input_types", "selectedInputTypes"))
    workflow_nodes: Optional[List[Dict[str, Any]]] = Field(default_factory=list, validation_alias=AliasChoices("workflow_nodes", "workflowNodes"))


async def _download_object(object_path: str) -> bytes:
    uploader = AliyunOSSUploader()
    return uploader.read_bytes(object_path)


def _extract_text_sync(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in {".txt", ".md"}:
        try:
            return open(file_path, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            return ""
    if ext == ".pdf":
        try:
            import subprocess
            import sys

            script = os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "skills_specs",
                "pdf",
                "scripts",
                "extract_pdf_text.py",
            )
            script = os.path.abspath(script)
            result = subprocess.run(
                [sys.executable, script, file_path, "--max-pages", "8"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:
            return ""
    if ext == ".docx":
        try:
            from docx import Document

            doc = Document(file_path)
            parts = [p.text for p in doc.paragraphs if p.text]
            return "\n".join(parts)
        except Exception:
            return ""
    return ""


async def _extract_text_from_object(object_path: str) -> str:
    content = await _download_object(object_path)
    filename = os.path.basename(object_path)
    suffix = os.path.splitext(filename)[1] or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        return await asyncio.to_thread(_extract_text_sync, tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


def _truncate(text: str, limit: int = 20000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit]


def _estimate_workflow_step_count(payload: WorkflowStepsGenerateRequest) -> int:
    existing_steps = [str(item or "").strip() for item in list(payload.existing_steps or []) if str(item or "").strip()]
    if existing_steps:
        base = len(existing_steps)
        mode = str(payload.mode or "generate").strip().lower()
        if mode == "optimize":
            return max(4, min(base, 10))
        if mode == "supplement":
            return max(4, min(base + 1, 10))
        if mode == "supplement_step":
            return 1
        return max(4, min(base, 10))

    text = " ".join(
        [
            str(payload.name or "").strip(),
            str(payload.description or "").strip(),
            str(payload.scenario or "").strip(),
            str(payload.supplement or "").strip(),
        ]
    )
    complexity_score = 0
    text_length = len(text)
    if text_length >= 80:
        complexity_score += 1
    if text_length >= 180:
        complexity_score += 1
    if text_length >= 320:
        complexity_score += 1

    complexity_keywords = [
        "多",
        "多个",
        "跨",
        "并行",
        "协同",
        "审批",
        "汇总",
        "复盘",
        "分析",
        "诊断",
        "策略",
        "区域",
        "门店",
        "团队",
        "客户",
        "经营",
        "异常",
        "规则",
        "判断",
        "分支",
        "例外",
        "风险",
        "预警",
        "对比",
        "跟进",
        "闭环",
        "workflow",
    ]
    keyword_hits = sum(1 for token in complexity_keywords if token in text)
    complexity_score += min(keyword_hits // 2, 4)

    target = 4 + complexity_score
    return max(4, min(target, 9))


def _resolved_workflow_step_count(payload: WorkflowStepsGenerateRequest) -> int:
    if payload.max_steps is None:
        return _estimate_workflow_step_count(payload)
    return max(4, min(int(payload.max_steps), 10))


def _resolved_workflow_node_count(payload: WorkflowNodesGenerateRequest) -> int:
    if payload.max_nodes is None:
        return 8
    return max(4, min(int(payload.max_nodes), 12))


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


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


def _time_text(value: Any) -> str:
    return utc_iso(value)


def _workflow_text_steps(config: Dict[str, Any]) -> List[str]:
    raw_steps = config.get("workflowSteps") or config.get("workflow_steps")
    if not isinstance(raw_steps, list):
        return []
    steps: List[str] = []
    for item in raw_steps:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("description") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            steps.append(text)
    return steps


def _admin_shape_payload_to_user_payload(
    payload: AdminShapeSkillPayload,
    *,
    user_id: str,
    main_id: str,
) -> Dict[str, Any]:
    skill_type = str(payload.type or "writing_style").strip().lower()
    config = _safe_dict(payload.config)
    name = str(payload.name or "").strip()
    description = str(payload.description or "").strip()
    scenario = str(payload.scenario or "").strip()
    enabled = bool(payload.enabled)

    if skill_type == "workflow":
        nodes = _workflow_nodes(config)
        steps = [
            str(node.get("description") or "").strip()
            for node in nodes
            if str(node.get("description") or "").strip()
        ] or _workflow_text_steps(config)
        skill_markdown = _workflow_markdown(
            name=name,
            description=description,
            scenario=scenario,
            steps=steps,
            nodes=nodes,
        )
        contract_json = {
            "skill_type": "composite_task",
            "name": name,
            "summary": description or scenario,
            "applicable_scenarios": scenario,
            "notes": description,
        }
        return {
            "user_id": user_id,
            "main_id": main_id,
            "name": name,
            "description": description,
            "summary": description or scenario,
            "category": "Workflow",
            "role": "execution",
            "skill_type": "composite_task",
            "tags": ["workflow"],
            "visibility": "private",
            "formats": ["markdown"],
            "notes": scenario,
            "input_profile": contract_json,
            "contract_json": contract_json,
            "skill_markdown": skill_markdown,
            "resources": {},
            "advanced": {},
            "is_active": enabled,
            "type": "workflow",
            "config": config,
            "scenario": scenario,
            "enabled": enabled,
        }

    contract_json = _safe_dict(config.get("contractJson") or config.get("contract_json"))
    input_profile = _safe_dict(config.get("inputProfile") or config.get("input_profile")) or contract_json
    skill_markdown = str(config.get("skillMarkdown") or config.get("skill_markdown") or "").strip()
    return {
        "user_id": user_id,
        "main_id": main_id,
        "name": name,
        "description": description,
        "summary": description or scenario,
        "category": "Writing Guidelines",
        "role": "style",
        "skill_type": "style",
        "tags": ["writing_style"],
        "visibility": "private",
        "formats": ["markdown"],
        "notes": scenario,
        "input_profile": input_profile,
        "contract_json": contract_json,
        "skill_markdown": skill_markdown,
        "resources": {},
        "advanced": {},
        "is_active": enabled,
        "type": "writing_style",
        "config": config,
        "scenario": scenario,
        "enabled": enabled,
    }


def _admin_shape_skill(skill: Dict[str, Any]) -> Dict[str, Any]:
    config = _safe_dict(skill.get("config"))
    raw_type = str(skill.get("type") or "").strip().lower()
    if raw_type not in {"writing_style", "workflow"}:
        raw_type = "workflow" if str(skill.get("skill_type") or "").strip().lower() == "composite_task" else "writing_style"
    if not config:
        if raw_type == "writing_style":
            config = {
                "inputProfile": _safe_dict(skill.get("input_profile")),
                "contractJson": _safe_dict(skill.get("contract_json")),
                "skillMarkdown": str(skill.get("skill_markdown") or ""),
            }
        else:
            config = {}
    return {
        "id": str(skill.get("id") or skill.get("_id") or ""),
        "mainId": str(skill.get("main_id") or skill.get("mainId") or "default"),
        "name": str(skill.get("name") or ""),
        "description": str(skill.get("description") or ""),
        "scenario": str(skill.get("scenario") or skill.get("notes") or ""),
        "type": raw_type,
        "config": config,
        "enabled": _safe_bool(skill.get("enabled"), _safe_bool(skill.get("is_active"), True)),
        "createdAt": _time_text(skill.get("created_at")),
        "updatedAt": _time_text(skill.get("updated_at")),
    }


def _selectable_skill_type(skill: Dict[str, Any]) -> str:
    raw_type = str(skill.get("type") or "").strip().lower()
    if raw_type in {"writing_style", "workflow"}:
        return raw_type
    return "workflow" if str(skill.get("skill_type") or "").strip().lower() == "composite_task" else "writing_style"


def _skill_source_scope(skill: Dict[str, Any]) -> str:
    visibility = str(skill.get("visibility") or "").strip().lower()
    owner = str(skill.get("user_id") or "").strip().lower()
    skill_id = str(skill.get("id") or skill.get("_id") or "").strip()
    if visibility == "organization" or owner == "organization" or skill_id.startswith("org_skill:"):
        return "organization"
    return "user"


def _selectable_skill_item(skill: Dict[str, Any]) -> Dict[str, Any]:
    source_scope = _skill_source_scope(skill)
    return {
        "id": str(skill.get("id") or skill.get("_id") or ""),
        "mainId": str(skill.get("main_id") or skill.get("mainId") or "default"),
        "name": str(skill.get("name") or ""),
        "description": str(skill.get("description") or skill.get("summary") or ""),
        "scenario": str(skill.get("scenario") or skill.get("notes") or ""),
        "type": _selectable_skill_type(skill),
        "sourceScope": source_scope,
        "enabled": _safe_bool(skill.get("enabled"), _safe_bool(skill.get("is_active"), True)),
        "updatedAt": _time_text(skill.get("updated_at")),
    }


def _matches_skill_keyword(skill: Dict[str, Any], keyword: str) -> bool:
    query = str(keyword or "").strip().lower()
    if not query:
        return True
    haystack = "\n".join(
        str(skill.get(key) or "")
        for key in ("name", "description", "summary", "scenario", "notes")
    ).lower()
    return query in haystack


def _cursor_offset(cursor: str | None) -> int:
    try:
        return max(0, int(str(cursor or "0").strip() or "0"))
    except Exception:
        return 0


def _extract_workflow_steps_from_text(text: str, max_steps: int) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    candidates = [raw]
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        candidates.insert(0, match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        raw_steps: Any = parsed.get("steps") if isinstance(parsed, dict) else parsed
        if not isinstance(raw_steps, list):
            continue
        steps: List[str] = []
        for item in raw_steps:
            if isinstance(item, dict):
                value = item.get("text") or item.get("step") or item.get("instruction") or ""
            else:
                value = item
            value = re.sub(r"\s+", " ", str(value or "")).strip()
            value = re.sub(r"^\d+[\.、\)]\s*", "", value).strip()
            if value:
                steps.append(value[:360])
        if steps:
            return steps[:max_steps]
    steps = []
    for line in raw.splitlines():
        value = re.sub(r"^\s*(?:[-*]|\d+[\.、\)])\s*", "", line).strip()
        if value:
            steps.append(value[:360])
    return steps[:max_steps]


def _extract_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    candidates = [raw]
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        candidates.insert(0, match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


_WORKFLOW_NODE_TYPES = {
    "read_material",
    "extract_resources",
    "understand_image",
    "extract_info",
    "compute_metric",
    "data_collect",
    "browser_automation",
    "internal_search",
    "external_search",
    "call_tool",
    "script_plugin",
    "generate_content",
    "translate_rewrite",
    "fill_table",
    "export_delivery",
}

_NODE_TYPE_ALIASES = {
    "读取材料": "read_material",
    "文档读取": "read_material",
    "提取资源": "extract_resources",
    "资源提取": "extract_resources",
    "提取图片": "extract_resources",
    "提取链接": "extract_resources",
    "提取附件": "extract_resources",
    "图片理解": "understand_image",
    "图像理解": "understand_image",
    "多模态理解": "understand_image",
    "图片识别": "understand_image",
    "识图": "understand_image",
    "文档抽取": "extract_info",
    "抽取信息": "extract_info",
    "信息抽取": "extract_info",
    "统计计算": "compute_metric",
    "指标计算": "compute_metric",
    "数据采集": "data_collect",
    "网页采集": "data_collect",
    "链接采集": "data_collect",
    "浏览器自动化": "browser_automation",
    "浏览器操作": "browser_automation",
    "网页操作": "browser_automation",
    "内部知识搜索": "internal_search",
    "知识检索": "internal_search",
    "外部搜索": "external_search",
    "公网搜索": "external_search",
    "调用工具": "call_tool",
    "MCP工具": "call_tool",
    "MCP 工具": "call_tool",
    "脚本插件": "script_plugin",
    "插件脚本": "script_plugin",
    "运行脚本": "script_plugin",
    "代码插件": "script_plugin",
    "生成内容": "generate_content",
    "内容生成": "generate_content",
    "翻译改写": "translate_rewrite",
    "翻译": "translate_rewrite",
    "文档翻译": "translate_rewrite",
    "填表制表": "fill_table",
    "导出交付": "export_delivery",
    "导出": "export_delivery",
}


def _normalize_workflow_node_type(value: Any, fallback: str = "generate_content") -> str:
    token = str(value or "").strip()
    if token in _WORKFLOW_NODE_TYPES:
        return token
    lowered = token.lower()
    if lowered in _WORKFLOW_NODE_TYPES:
        return lowered
    return _NODE_TYPE_ALIASES.get(token, fallback)


def _normalize_workflow_node_catalog(raw_items: Any) -> List[Dict[str, str]]:
    catalog: List[Dict[str, str]] = []
    if not isinstance(raw_items, list):
        return catalog
    for raw in raw_items[:30]:
        if not isinstance(raw, dict):
            continue
        node_type = str(raw.get("type") or "").strip()
        if node_type not in _WORKFLOW_NODE_TYPES:
            continue
        catalog.append({
            "type": node_type,
            "name": re.sub(r"\s+", " ", str(raw.get("name") or raw.get("label") or node_type).strip())[:80],
            "usageDescription": re.sub(r"\s+", " ", str(raw.get("usageDescription") or raw.get("usage_description") or "").strip())[:600],
            "usageExample": re.sub(r"\s+", " ", str(raw.get("usageExample") or raw.get("usage_example") or "").strip())[:600],
        })
    return catalog


def _normalize_workflow_node(raw: Any, index: int) -> Dict[str, Any] | None:
    if isinstance(raw, str):
        raw = {"description": raw}
    if not isinstance(raw, dict):
        return None
    node_type = _normalize_workflow_node_type(raw.get("type") or raw.get("node_type"))
    title = re.sub(r"\s+", " ", str(raw.get("title") or raw.get("name") or "").strip())[:80]
    description = re.sub(
        r"\s+",
        " ",
        str(raw.get("description") or raw.get("instruction") or raw.get("text") or "").strip(),
    )[:420]
    if not description and title:
        description = title
    if not title and description:
        title = description[:48]
    if not description:
        return None
    business_config = raw.get("businessConfig") or raw.get("business_config") or {}
    if not isinstance(business_config, dict):
        business_config = {}
    output_alias = str(raw.get("outputAlias") or raw.get("output_alias") or business_config.get("outputAlias") or business_config.get("output_alias") or "").strip()[:80]
    bound_writing_skill_id = str(raw.get("boundWritingSkillId") or raw.get("bound_writing_skill_id") or "").strip()[:120]
    return {
        "id": str(raw.get("id") or f"node_{index + 1}"),
        "type": node_type,
        "title": title,
        "description": description,
        "businessConfig": business_config,
        "boundWritingSkillId": bound_writing_skill_id,
        "outputAlias": output_alias,
    }


def _extract_workflow_nodes_from_text(text: str, max_nodes: int) -> List[Dict[str, Any]]:
    raw = str(text or "").strip()
    if not raw:
        return []
    candidates = [raw]
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        candidates.insert(0, match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        raw_nodes = parsed.get("nodes") if isinstance(parsed, dict) else parsed
        if not isinstance(raw_nodes, list):
            continue
        nodes = [_normalize_workflow_node(item, idx) for idx, item in enumerate(raw_nodes)]
        nodes = [item for item in nodes if item]
        if nodes:
            return nodes[:max_nodes]
    return []


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"true", "1", "yes", "y", "是", "已覆盖", "可解析", "通过"}


def _normalize_workflow_check_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    logic = payload.get("logic") if isinstance(payload.get("logic"), dict) else {}
    coverage = payload.get("coverage") if isinstance(payload.get("coverage"), list) else []
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), list) else []
    suggestions = payload.get("suggestions") if isinstance(payload.get("suggestions"), list) else []
    normalized_coverage = []
    for item in coverage:
        if not isinstance(item, dict):
            continue
        normalized_coverage.append({
            "key": str(item.get("key") or ""),
            "label": str(item.get("label") or ""),
            "covered": _normalize_bool(item.get("covered")),
        })
    normalized_readiness = []
    for item in readiness:
        if not isinstance(item, dict):
            continue
        normalized_readiness.append({
            "key": str(item.get("key") or ""),
            "label": str(item.get("label") or ""),
            "ready": _normalize_bool(item.get("ready")),
        })
    return {
        "pass": _normalize_bool(payload.get("pass")),
        "logic": {
            "label": str(logic.get("label") or "需要澄清")[:40],
            "level": "success" if str(logic.get("level") or "").lower() == "success" else "warning",
            "summary": str(logic.get("summary") or "模型未返回明确的逻辑说明。")[:320],
        },
        "coverage": normalized_coverage[:8],
        "readiness": normalized_readiness[:8],
        "suggestions": [str(item or "").strip()[:220] for item in suggestions if str(item or "").strip()][:5],
        "conclusion": str(payload.get("conclusion") or "当前业务逻辑仍需进一步澄清。")[:320],
    }


_SCRIPT_PLUGIN_ALLOWED_IMPORT_ROOTS = {"json", "os", "re", "shutil", "zipfile", "csv", "math", "statistics", "datetime", "collections", "docx", "openpyxl", "pptx", "urllib"}
_SCRIPT_PLUGIN_ALLOWED_IMPORT_MODULES = {"urllib.parse"}
_SCRIPT_PLUGIN_DENIED_IMPORT_ROOTS = {
    "subprocess", "socket", "requests", "http", "ftplib", "smtplib", "paramiko", "asyncio",
    "multiprocessing", "threading", "ctypes", "sys", "pathlib", "importlib", "builtins",
}
_SCRIPT_PLUGIN_DENIED_CALLS = {"eval", "exec", "compile", "__import__", "input", "breakpoint", "globals", "locals", "vars"}
_SCRIPT_PLUGIN_DENIED_FULL_CALLS = {
    "os.system", "os.popen", "os.spawn", "os.fork", "os.execv", "os.execve",
    "os.remove", "os.unlink", "os.rmdir", "os.removedirs", "os.chdir", "os.chmod", "os.chown",
    "os.kill", "os.killpg", "shutil.rmtree",
}
_SCRIPT_PLUGIN_WRITE_FUNCS = {"open", "copyfile", "copy", "copy2", "move"}
_SCRIPT_PLUGIN_CODE_MAX_BYTES = 200 * 1024


def _script_issue(level: str, code: str, message: str, line: int | None = None) -> Dict[str, Any]:
    return {"level": level, "code": code, "message": message, "line": line}


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _literal_string(node: ast.AST | None) -> str:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""


def _is_allowed_script_import(module_name: str) -> bool:
    if not module_name:
        return False
    root = module_name.split(".")[0]
    if module_name in _SCRIPT_PLUGIN_ALLOWED_IMPORT_MODULES:
        return True
    if root == "urllib":
        return False
    return root in _SCRIPT_PLUGIN_ALLOWED_IMPORT_ROOTS and root not in _SCRIPT_PLUGIN_DENIED_IMPORT_ROOTS


def _looks_like_output_dir_expr(node: ast.AST | None, safe_names: set[str] | None = None) -> bool:
    safe_names = safe_names or set()
    if node is None:
        return False
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "context":
        return _literal_string(node.slice) == "output_dir"
    if isinstance(node, ast.Call) and _call_name(node.func).endswith(".get"):
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "context":
            return bool(node.args and _literal_string(node.args[0]) == "output_dir")
    if isinstance(node, ast.Name):
        return node.id in {"out_dir", "output_dir"} or node.id in safe_names
    if isinstance(node, ast.Call) and _call_name(node.func) in {"os.path.join", "join"}:
        return bool(node.args and _looks_like_output_dir_expr(node.args[0], safe_names))
    return False


def _assign_target_names(node: ast.AST) -> List[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        names: List[str] = []
        for item in node.elts:
            names.extend(_assign_target_names(item))
        return names
    return []


def _collect_output_path_names(tree: ast.AST) -> set[str]:
    safe_names: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                if _looks_like_output_dir_expr(node.value, safe_names):
                    for target in node.targets:
                        for name in _assign_target_names(target):
                            if name not in safe_names:
                                safe_names.add(name)
                                changed = True
            elif isinstance(node, ast.AnnAssign):
                if _looks_like_output_dir_expr(node.value, safe_names):
                    for name in _assign_target_names(node.target):
                        if name not in safe_names:
                            safe_names.add(name)
                            changed = True
    return safe_names


def _is_import_only_try(node: ast.Try) -> bool:
    def _safe_try_body_item(item: ast.AST) -> bool:
        return isinstance(item, (ast.Import, ast.ImportFrom))

    def _safe_handler_item(item: ast.AST) -> bool:
        if isinstance(item, ast.Assign):
            return all(isinstance(target, ast.Name) for target in item.targets) and isinstance(item.value, (ast.Constant, ast.Name))
        return isinstance(item, ast.Pass)

    return (
        bool(node.handlers)
        and all(_safe_try_body_item(item) for item in node.body)
        and not node.orelse
        and not node.finalbody
        and all(all(_safe_handler_item(item) for item in handler.body) for handler in node.handlers)
    )


def _validate_script_plugin_static(code: str) -> Dict[str, Any]:
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    raw = str(code or "")
    if len(raw.encode("utf-8")) > _SCRIPT_PLUGIN_CODE_MAX_BYTES:
        errors.append(_script_issue("error", "CODE_TOO_LARGE", "脚本代码不能超过 200KB。"))
    try:
        tree = ast.parse(raw)
    except SyntaxError as exc:
        errors.append(_script_issue("error", "SYNTAX_ERROR", f"Python 语法错误：{exc.msg}", exc.lineno))
        return {"pass": False, "rulePass": False, "errors": errors, "warnings": warnings, "llm": None}

    output_path_names = _collect_output_path_names(tree)
    run_defs = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run"]
    if not run_defs:
        errors.append(_script_issue("error", "MISSING_RUN", "必须定义入口函数 def run(inputs, context):。"))
        run_def = None
    else:
        run_def = run_defs[0]
        arg_names = [arg.arg for arg in run_def.args.args]
        if isinstance(run_def, ast.AsyncFunctionDef):
            errors.append(_script_issue("error", "ASYNC_RUN", "run 入口必须是普通函数，不能使用 async def。", run_def.lineno))
        if arg_names[:2] != ["inputs", "context"]:
            errors.append(_script_issue("error", "RUN_SIGNATURE", "run 函数前两个参数必须是 inputs, context。", run_def.lineno))
        if not any(isinstance(node, ast.Return) for node in ast.walk(run_def)):
            errors.append(_script_issue("error", "MISSING_RETURN", "run 函数必须 return 一个 dict，通常包含 artifacts 和 logs。", run_def.lineno))

    for node in tree.body:
        if isinstance(node, (ast.Expr, ast.For, ast.While, ast.With, ast.Try, ast.If)):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue
            if isinstance(node, ast.Try) and _is_import_only_try(node):
                continue
            errors.append(_script_issue("error", "TOP_LEVEL_EXECUTION", "禁止在顶层直接执行业务逻辑，请放到 run(inputs, context) 或辅助函数中。", getattr(node, "lineno", None)))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _is_allowed_script_import(alias.name):
                    errors.append(_script_issue("error", "DENIED_IMPORT", f"不允许导入模块：{alias.name}。", node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if not _is_allowed_script_import(node.module or ""):
                errors.append(_script_issue("error", "DENIED_IMPORT", f"不允许 from {node.module or ''} import ...。", node.lineno))
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            short = name.split(".")[-1]
            if short in _SCRIPT_PLUGIN_DENIED_CALLS:
                errors.append(_script_issue("error", "DENIED_CALL", f"不允许调用危险函数：{short}。", node.lineno))
            if name in _SCRIPT_PLUGIN_DENIED_FULL_CALLS:
                errors.append(_script_issue("error", "DENIED_CALL", f"不允许调用危险系统函数：{name}。", node.lineno))
            if name in {"open", "io.open"}:
                mode = _literal_string(node.args[1] if len(node.args) > 1 else None) or _literal_string(next((kw.value for kw in node.keywords if kw.arg == "mode"), None))
                if any(flag in mode for flag in ("w", "a", "x", "+")) and not _looks_like_output_dir_expr(node.args[0] if node.args else None, output_path_names):
                    warnings.append(_script_issue("warning", "WRITE_PATH_REVIEW", "写文件路径应来自 context['output_dir']。请确认没有写到输入目录或固定绝对路径。", node.lineno))
            if name in {"shutil.copyfile", "shutil.copy", "shutil.copy2", "shutil.move"} and len(node.args) >= 2:
                if not _looks_like_output_dir_expr(node.args[1], output_path_names):
                    warnings.append(_script_issue("warning", "OUTPUT_PATH_REVIEW", "输出文件目标路径建议使用 os.path.join(context['output_dir'], filename)。", node.lineno))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.match(r"^/(Users|var|tmp|etc|private|home|root)/", node.value):
                warnings.append(_script_issue("warning", "ABSOLUTE_PATH_LITERAL", "脚本中出现固定绝对路径，插件运行时通常不可访问。", getattr(node, "lineno", None)))

    if raw.count("context[\"output_dir\"]") + raw.count("context['output_dir']") + raw.count("context.get(\"output_dir\")") + raw.count("context.get('output_dir')") == 0:
        warnings.append(_script_issue("warning", "OUTPUT_DIR_NOT_REFERENCED", "未明显使用 context['output_dir']，如果要生成文件，必须写入该目录。"))
    if "\"artifacts\"" not in raw and "'artifacts'" not in raw and "\"files\"" not in raw and "'files'" not in raw:
        warnings.append(_script_issue("warning", "OUTPUT_FILES_NOT_REFERENCED", "未明显返回 files/artifacts；如果该节点要导出文件，后续导出节点可能拿不到文件。"))
    return {"pass": not errors, "rulePass": not errors, "errors": errors[:50], "warnings": warnings[:50], "llm": None}


def _normalize_script_llm_review(payload: Dict[str, Any]) -> Dict[str, Any]:
    risks = payload.get("risks") if isinstance(payload.get("risks"), list) else []
    suggestions = payload.get("suggestions") if isinstance(payload.get("suggestions"), list) else []
    return {
        "pass": _normalize_bool(payload.get("pass")),
        "level": str(payload.get("level") or "warning")[:20],
        "summary": str(payload.get("summary") or "LLM 未返回明确审查结论。")[:320],
        "risks": [str(item or "").strip()[:220] for item in risks if str(item or "").strip()][:8],
        "suggestions": [str(item or "").strip()[:220] for item in suggestions if str(item or "").strip()][:8],
    }


def _generated_code_hardcode_warnings(code: str, instruction: str) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    instruction_text = str(instruction or "")
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return warnings
    generic_terms = {
        "未检测到可处理的文件",
        "处理完成",
        "处理失败",
        "输入为空",
        "输出文件",
        "处理结果",
        "数据处理结果",
        "无法打开文件",
        "保存文件失败",
    }
    seen: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        text = re.sub(r"\s+", "", node.value)
        if len(text) < 8 or not re.search(r"[\u4e00-\u9fff]", text):
            continue
        if text in seen or text in generic_terms or text in instruction_text:
            continue
        if re.search(r"(中心|公司|项目|白皮书|报告|发稿|统计|客户|定版|原版|\d{4}年|\d{8})", text):
            warnings.append(_script_issue("warning", "POSSIBLE_HARDCODED_CASE", f"生成代码包含处理要求之外的疑似业务硬编码：{text[:60]}。", getattr(node, "lineno", None)))
            seen.add(text)
        if len(warnings) >= 8:
            break
    return warnings


async def _review_script_plugin_with_llm(payload: ScriptPluginCheckRequest, static_result: Dict[str, Any]) -> Dict[str, Any]:
    system_prompt = (
        "你是脚本插件审查助手。只做代码规范和业务风险审查，不执行代码。"
        "插件必须定义 run(inputs, context)，优先读取 inputs['selected'] 中的 files/documents/images/urls/texts/tables/data，输出写入 context['output_dir']，返回 dict。"
        "请重点检查：是否可能丢文件/图片，是否没有返回 artifacts，是否异常处理不足，是否业务意图与脚本逻辑不匹配。"
        "不要提出需要联网或外部依赖的建议。只输出 JSON。"
    )
    user_prompt = (
        f"节点标题：{payload.node_title or '（无）'}\n"
        f"节点描述：{payload.node_description or '（无）'}\n"
        f"规则检测结果：{json.dumps(static_result, ensure_ascii=False)}\n"
        f"脚本代码：\n{payload.code[:12000]}\n\n"
        "返回 JSON 格式：{\"pass\": true, \"level\": \"success|warning\", \"summary\": \"一句话结论\", \"risks\": [], \"suggestions\": []}"
    )
    llm = get_llm_client(streaming=False, stage="script_plugin_check", intent="classification")
    resp = await llm.ainvoke([
        Message(role=Role.SYSTEM, content=system_prompt),
        Message(role=Role.USER, content=user_prompt),
    ])
    return _normalize_script_llm_review(_extract_json_object(str((resp.content if resp else "") or "")))


async def _fix_script_plugin_with_llm(payload: ScriptPluginFixRequest, static_result: Dict[str, Any]) -> Dict[str, Any]:
    system_prompt = (
        "你是 Python 脚本插件修复助手。任务是对用户脚本做最小修改，使其符合平台脚本插件规范。"
        "必须保留原业务逻辑，不要重写成完全不同的程序。"
        "规范：必须定义 def run(inputs, context)；优先从 inputs['selected'] 读取 files/documents/images/urls/texts/tables/data；"
        "输出文件只能写入 context['output_dir']；返回 dict，可返回 files/data/logs 或 artifacts/data/logs；"
        "禁止联网、子进程、eval/exec、固定本机路径、os.remove/os.unlink/shutil.rmtree 等危险操作。"
        "允许 python-docx 的 XML 操作，例如 parent.remove(element)。"
        "可选依赖请优先在 run 内部导入，或只使用顶层 try/except ImportError 包裹 import，不得在顶层执行数据处理。"
        "输出路径变量必须直接或间接来源于 context['output_dir']，例如 output_dir = context.get('output_dir'); out_path = os.path.join(output_dir, filename)。"
        "只输出 JSON，格式为 {\"code\":\"修复后的完整代码\", \"notes\":[\"修改说明\"]}。"
    )
    issues = payload.issues or []
    user_prompt = (
        f"节点标题：{payload.node_title or '（无）'}\n"
        f"节点描述：{payload.node_description or '（无）'}\n"
        f"当前规则检测结果：{json.dumps(static_result, ensure_ascii=False)}\n"
        f"用户看到的问题：{json.dumps(issues, ensure_ascii=False)}\n"
        f"原代码：\n{payload.code[:20000]}\n\n"
        "请修复代码。要求：\n"
        "1. 尽量只修改违规点和明显不符合 I/O 契约的地方。\n"
        "2. 不要删除正常的 parent.remove(element) 这类 docx XML 操作。\n"
        "3. 如果顶层有 try/except 导入依赖，优先改为 run 内局部导入，或保持为只含 import/赋值的 ImportError 兜底。\n"
        "4. 如果输出路径使用变量但实际来源是 context['output_dir']，可以保持或轻微改写得更清楚。\n"
        "5. 返回完整可粘贴代码，不要 Markdown。"
    )
    llm = get_llm_client(streaming=False, stage="script_plugin_fix", intent="generation")
    resp = await llm.ainvoke([
        Message(role=Role.SYSTEM, content=system_prompt),
        Message(role=Role.USER, content=user_prompt),
    ])
    parsed = _extract_json_object(str((resp.content if resp else "") or ""))
    fixed_code = str(parsed.get("code") or "").strip()
    notes = parsed.get("notes") if isinstance(parsed.get("notes"), list) else []
    return {
        "code": fixed_code,
        "notes": [str(item or "").strip()[:300] for item in notes if str(item or "").strip()][:10],
    }


async def _generate_script_plugin_with_llm(payload: ScriptPluginGenerateRequest) -> Dict[str, Any]:
    input_types = [str(item or "").strip() for item in list(payload.selected_input_types or []) if str(item or "").strip()]
    nodes = []
    for item in list(payload.workflow_nodes or [])[:20]:
        if not isinstance(item, dict):
            continue
        config = item.get("businessConfig") if isinstance(item.get("businessConfig"), dict) else {}
        nodes.append(
            {
                "type": str(item.get("type") or "")[:80],
                "title": str(item.get("title") or "")[:160],
                "outputAlias": str(item.get("outputAlias") or config.get("outputAlias") or "")[:120],
            }
        )
    system_prompt = (
        "你是平台“数据处理”节点的 Python 代码生成助手。"
        "你的任务是根据业务描述生成完整可粘贴的脚本插件代码，只输出 JSON。"
        "脚本必须定义 def run(inputs, context):，不得在顶层执行业务逻辑。"
        "运行时只允许从 inputs、context 取数；优先读取 inputs.get('selected') 中的 files/documents/images/urls/texts/tables/data。"
        "输出文件只能写入 context['output_dir']，路径必须使用 os.path.join(context['output_dir'], filename)。"
        "返回 dict，优先返回 {\"files\": [{\"path\": 文件名或完整路径, \"type\": 扩展名}], \"data\": {}, \"logs\": []}。"
        "禁止联网、子进程、eval/exec、固定本机路径、删除系统文件、修改输入文件。"
        "只允许依据用户的处理要求生成业务逻辑；禁止引用处理要求之外的具体客户名、项目名、标题、日期、案例名。"
        "如果需求不明确，生成稳健的通用处理代码和清晰 logs，不要编造外部数据。"
        "可使用常见标准库以及 python-docx/openpyxl/python-pptx/pypdf 这类平台文档处理库。"
        "不要在顶层写 try/if/for/with 等业务执行代码；可选依赖优先在 run 内部导入并兜底。"
        "只输出 JSON：{\"code\":\"完整 Python 代码\", \"notes\":[\"说明\"]}。"
    )
    user_prompt = (
        f"处理要求：{payload.processing_instruction.strip()}\n"
        f"当前节点标题：{payload.node_title or '（无）'}\n"
        f"输入来源配置：{payload.selected_input_source or 'all'}\n"
        f"输入类型配置：{json.dumps(input_types or ['files', 'documents', 'images', 'urls', 'texts', 'data'], ensure_ascii=False)}\n"
        f"简化工作流上下文：{json.dumps(nodes, ensure_ascii=False)[:4000]}\n\n"
        "请生成数据处理节点代码。要求：\n"
        "1. 代码要以 inputs['selected'] 作为主要输入适配层，不要求用户知道上游文件名。\n"
        "2. 对 files/images/texts/urls/documents/data 做空值保护。\n"
        "3. 如果生成文件，文件名使用安全的固定业务名，不使用用户本机绝对路径。\n"
        "4. 如果是 DOCX 处理，要保留图片并尽量使用 python-docx 操作，不经过 Markdown 中转。\n"
        "5. 不得把处理要求里没有出现的客户名、项目名、正式标题、日期写死到代码或输出文件名中。\n"
        "6. 返回完整 Python 代码，不要 Markdown 代码块。"
    )
    llm = get_llm_client(streaming=False, stage="script_plugin_generate", intent="generation")
    resp = await llm.ainvoke([
        Message(role=Role.SYSTEM, content=system_prompt),
        Message(role=Role.USER, content=user_prompt),
    ])
    parsed = _extract_json_object(str((resp.content if resp else "") or ""))
    code = str(parsed.get("code") or "").strip()
    notes = parsed.get("notes") if isinstance(parsed.get("notes"), list) else []
    return {
        "code": code,
        "notes": [str(item or "").strip()[:300] for item in notes if str(item or "").strip()][:10],
    }


async def _generate_workflow_steps_with_llm(payload: WorkflowStepsGenerateRequest) -> List[str]:
    name = payload.name.strip()
    description = str(payload.description or "").strip()
    scenario = str(payload.scenario or "").strip()
    max_steps = _resolved_workflow_step_count(payload)
    existing_steps = [str(item or "").strip() for item in list(payload.existing_steps or []) if str(item or "").strip()]
    mode = str(payload.mode or "generate").strip().lower()
    supplement = str(payload.supplement or "").strip()
    node_catalog = _normalize_workflow_node_catalog(payload.node_catalog)
    if mode == "supplement_step":
        existing_instruction = (
            "本次不是重写整套流程，而是补充当前输入框里的这一条新业务步骤。"
            f"请基于用户新增业务点，把它扩写成 1 条更完整、更清楚、适合直接加入步骤列表的业务步骤；新增业务点：{supplement or '（未提供）'}。"
            "不要改写已有步骤，不要返回多条步骤，不要生成完整流程。"
        )
    elif mode == "supplement":
        existing_instruction = (
            "本次是补充业务步骤：如果已有步骤存在，请保留其中的核心业务意图和大体顺序，"
            f"把用户新增的业务点融入到最合适的位置，必要时可改写相邻步骤或新增一步；用户新增业务点：{supplement or '（未提供）'}。"
            "如果没有已有步骤，请围绕这个新增业务点生成一套完整的业务逻辑草稿。最终返回完整的更新后步骤列表，而不是只返回新增步骤。"
        )
    elif mode == "optimize" and existing_steps:
        existing_instruction = (
            "本次是优化已有步骤：请保留现有步骤中的核心业务意图和顺序，只在表达不清、缺少判断依据、缺少异常处理或缺少输出要求时进行重写、合并或补充；"
            "不要完全另起一套无关流程。最终返回完整的优化后步骤列表。"
        )
    elif existing_steps:
        existing_instruction = (
            "本次有现有步骤作为参考：请结合 Skill 信息和现有步骤生成一套完整步骤，优先保留合理业务意图，补齐明显缺口。"
        )
    else:
        existing_instruction = "本次是从 Skill 信息生成初始业务步骤：请根据名称、描述和使用场景直接生成一套完整的业务逻辑草稿。"

    system_prompt = (
        "你是资深业务分析师，负责帮助非技术用户把一个 Skill 的业务逻辑说清楚。"
        "当前阶段不是生成可执行技术工作流，而是产出后续可被解析成结构化工作流的业务逻辑草稿。"
        "步骤必须使用自然语言表达业务目标、输入边界、默认规则、判断标准、异常处理和输出要求。"
        "不要把步骤拆成变量、字段、表单或节点配置，也不要要求用户理解技术概念。"
        "每一步都应尽量在一句业务语言中交代：需要关注的业务信息、依据什么标准判断、得到什么中间结论；"
        "涉及默认值、缺失信息、不确定结果或异常波动时，要说明采用什么业务处理方式。"
        "涉及内部规定、历史口径、知识库、经营标准、会议结论等外部依据时，只能表达为优先查找或确认该依据；"
        "如果无法获取该依据，必须说明要求用户补充、标注未知或基于已确认信息给出有限结论，不能直接假设该依据一定存在或一定可用。"
        "不要描述底层工具、接口、API、数据库、MCP、HTTP、字段名、节点连线或技术实现。"
        "每一步都要能被业务人员理解，并且能为后续结构化解析提供清晰依据。"
        "只输出 JSON，格式为 {\"steps\":[\"步骤1\", \"步骤2\"]}。"
    )
    user_prompt = (
        f"Skill 名称：{name}\n"
        f"技能描述：{description or '（无）'}\n"
        f"使用场景：{scenario or '（无）'}\n"
        f"建议步骤数上限：{max_steps}\n"
        f"生成模式：{mode}\n"
        f"可用节点能力目录：{json.dumps(node_catalog, ensure_ascii=False) if node_catalog else '（未提供）'}\n"
        f"现有步骤参考：{json.dumps(existing_steps, ensure_ascii=False) if existing_steps else '（无）'}\n\n"
        f"{existing_instruction}\n\n"
        "请生成用于“业务逻辑澄清”的自然语言步骤，要求：\n"
        "1. 如果生成模式是 supplement_step，只返回 1 条补充后的步骤；否则步骤数应按 Skill 复杂度决定：简单场景 4-5 步即可，常规场景 5-7 步，复杂场景 7-9 步；最多不超过建议步骤数上限。\n"
        "2. 从确认用户目标和输入边界开始，到定义输出结果结束。\n"
        "3. 必须覆盖范围确认、默认规则、业务判断标准、异常/缺失处理、结论与建议。\n"
        "4. 尽量让每一步都自然包含四类信息中的至少两类：要看的业务信息、判断依据或阈值、异常/缺失时的处理、该步形成的中间结论。\n"
        "5. 如果 Skill 描述较宽泛，可以用“先明确/如果未提供/根据业务目标选择”等业务表达保留弹性，不要编造固定字段名。\n"
        "6. 如需依赖内部规定、历史口径、知识库、经营标准或会议结论，只能写成“优先查找/确认；无法获取时要求补充或给出有限结论”，不能默认这些依据必然存在。\n"
        "7. 用业务语言描述“应该怎么判断和处理”，不要出现任何具体工具、接口、系统调用、参数字段、JSON Schema、节点或技术名词。\n"
        "8. 每步是一句话，直接可放入配置页面；允许稍长，但不要写成多段解释。\n"
        "9. 可用节点能力目录只用于理解平台能做什么，不要在步骤中照抄目录示例，也不要输出英文节点类型。"
    )
    llm = get_llm_client(streaming=False, stage="admin_workflow_steps", intent="generation")
    resp = await llm.ainvoke(
        [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=user_prompt),
        ]
    )
    return _extract_workflow_steps_from_text(str((resp.content if resp else "") or ""), max_steps)


async def _generate_workflow_nodes_with_llm(payload: WorkflowNodesGenerateRequest) -> List[Dict[str, Any]]:
    name = payload.name.strip()
    description = str(payload.description or "").strip()
    scenario = str(payload.scenario or "").strip()
    max_nodes = _resolved_workflow_node_count(payload)
    existing_nodes = [
        node for idx, raw in enumerate(list(payload.existing_nodes or []))
        for node in [_normalize_workflow_node(raw, idx)]
        if node
    ]
    allowed_config_keys = {
        "input", "target", "method", "format", "source", "failurePolicy",
        "resourceTypes", "outputAlias", "toolId", "toolName", "toolScope",
        "targetName", "targetUrl",
    }
    for node in existing_nodes:
        config = node.get("businessConfig") if isinstance(node.get("businessConfig"), dict) else {}
        node["businessConfig"] = {
            key: value for key, value in config.items()
            if key in allowed_config_keys and value not in (None, "", [], {})
        }
    mode = str(payload.mode or "generate").strip().lower()
    supplement = str(payload.supplement or "").strip()
    node_catalog = _normalize_workflow_node_catalog(payload.node_catalog)
    system_prompt = (
        "你是业务流程 Skill 配置助手。你的任务是把非技术用户的业务意图整理成语义化业务步骤节点。"
        "这些节点是图规划的强指导，不是固定执行图；不要生成字段 Schema、入参出参、循环、条件分支、工具参数或代码逻辑。"
        "节点类型只能使用以下英文枚举：read_material, extract_resources, understand_image, extract_info, compute_metric, data_collect, browser_automation, internal_search, external_search, call_tool, "
        "script_plugin, generate_content, translate_rewrite, fill_table, export_delivery。"
        "每个节点只表达业务步骤：type,title,description,businessConfig,outputAlias,boundWritingSkillId。"
        "businessConfig 只能放业务级短语，例如 input, target, method, format, source, failurePolicy；"
        "browser_automation 可使用 targetName 和 targetUrl；不要放其他技术参数。"
        "如果需要从文档/材料中拿出图片、URL、附件等可继续处理的资源，使用 extract_resources，并在 businessConfig.resourceTypes 中写 images/urls/attachments。"
        "如果需要理解图片、截图、图表或文档内嵌图片的视觉内容，使用 understand_image；通常它应跟在 extract_resources 之后。"
        "如果需要从文本、表格、文档解析结果或图片理解结果中抽取公司名、金额、日期、字段值等语义信息，使用 extract_info。"
        "如果需要从已知 URL 或上游抽取出的链接采集网页正文，使用 data_collect；如果需要搜索未知公开资料，使用 external_search。"
        "如果需要 MCP、企业系统或第三方工具，使用 call_tool；内部知识库使用 internal_search。"
        "如果需要在网页或企业后台中查询、填写、保存、提交、上传或发布，使用 browser_automation；"
        "目标名称放在 businessConfig.targetName（如 OA），对应网址放在 businessConfig.targetUrl，未知时可留空。"
        "页面会提供完整的节点能力目录，其中的使用场景用于判断节点边界，示例只用于理解写法，禁止把示例中的文件名、日期、地区或业务数据带入结果。"
        "只输出 JSON，格式为 {\"nodes\":[...]}。"
    )
    if mode == "supplement_step":
        mode_instruction = (
            "本次只补充用户输入的一条业务节点。请把新增业务点整理成 1 个语义节点，不要重写完整流程。"
            f"新增业务点：{supplement or '（未提供）'}"
        )
    elif mode == "optimize" and existing_nodes:
        mode_instruction = (
            "本次优化当前完整节点配置：逐项理解已有节点中用户填写的要求，并结合 Skill 目标检查流程是否完整。"
            "可以重写节点要求、调整顺序、合并重复节点、删除无必要节点，也可以从能力目录中新增缺失节点。"
            "不要机械保留原数量和顺序，也不要把用户的具体要求改成能力目录里的通用示例。"
            "保留的节点必须沿用原 id；新增节点使用 new_node_1、new_node_2 这类唯一 id。"
        )
    else:
        mode_instruction = (
            "本次从零生成完整业务流程节点：根据 Skill 名称、描述和使用场景，从能力目录中选择真正需要的节点，"
            "并为每个节点生成符合当前 Skill 的具体要求；不要为了覆盖目录而添加无关节点。"
        )
    user_prompt = (
        f"Skill 名称：{name}\n"
        f"技能描述：{description or '（无）'}\n"
        f"使用场景：{scenario or '（无）'}\n"
        f"建议节点数上限：{max_nodes}\n"
        f"生成模式：{mode}\n"
        f"可用节点能力目录：{json.dumps(node_catalog, ensure_ascii=False) if node_catalog else '（未提供）'}\n"
        f"已有节点：{json.dumps(existing_nodes, ensure_ascii=False)}\n\n"
        f"{mode_instruction}\n\n"
        "要求：\n"
        "1. 常规流程 4-7 个节点，复杂流程最多不超过上限。\n"
        "2. 节点描述必须是一句话业务语言。\n"
        "3. 对复杂写作，优先拆成读取/抽取/统计或检索/生成/审核/导出。\n"
        "4. 生成内容节点如果未明确写作 Skill，boundWritingSkillId 留空。\n"
        "5. 数据缺失、循环、条件、失败重试由系统规划处理，不要作为用户配置节点展开。\n"
        "6. outputAlias 使用用户能理解的短名，例如“传播数据”“指标分析”“复盘稿”。\n"
        "7. description 必须是针对当前 Skill 的可执行业务要求，优先保留用户已填写的具体文件、范围、字段、口径和输出要求。\n"
        "8. 只选择完成该 Skill 所需的节点；允许优化模式新增、删除、合并和重排节点。\n"
        "9. 能力目录中的示例不能作为当前业务事实，不得照抄其中的专名、日期、数字或文件名。\n"
        "10. 优化时如果保留调用工具节点、生成内容节点或浏览器自动化节点，应保留仍然适用的 toolId、toolName、boundWritingSkillId、businessConfig.targetName 和 businessConfig.targetUrl 等已有绑定。"
    )
    llm = get_llm_client(streaming=False, stage="admin_workflow_nodes", intent="generation")
    resp = await llm.ainvoke(
        [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=user_prompt),
        ]
    )
    return _extract_workflow_nodes_from_text(str((resp.content if resp else "") or ""), max_nodes)


async def _polish_workflow_node_with_llm(payload: WorkflowNodePolishRequest) -> str:
    name = payload.name.strip()
    description = str(payload.description or "").strip()
    scenario = str(payload.scenario or "").strip()
    node = _normalize_workflow_node(payload.node, 0)
    if not node:
        return ""
    existing_nodes = [
        normalized for idx, raw in enumerate(list(payload.existing_nodes or []))
        for normalized in [_normalize_workflow_node(raw, idx)]
        if normalized
    ]
    node_catalog = _normalize_workflow_node_catalog(payload.node_catalog)
    node_type = str(node.get("type") or "").strip()
    catalog_item = next((item for item in node_catalog if item.get("type") == node_type), {})
    current_text = str(node.get("description") or "").strip()
    system_prompt = (
        "你是工作流 Skill 节点要求润色助手。"
        "你只负责把单个节点的业务要求改写得更清楚、更可执行，不能改变业务事实、节点类型、工具绑定、写作 Skill 绑定或流程顺序。"
        "不得新增用户没有提供的文件名、日期、数字、地区、系统名、指标口径或交付物。"
        "输出必须是 JSON，不要 Markdown，不要解释。"
    )
    user_prompt = (
        f"Skill 名称：{name}\n"
        f"Skill 描述：{description or '（无）'}\n"
        f"使用场景：{scenario or '（无）'}\n"
        f"当前节点：{json.dumps(node, ensure_ascii=False)}\n"
        f"同一工作流其他节点：{json.dumps(existing_nodes, ensure_ascii=False)}\n"
        f"该节点能力说明：{json.dumps(catalog_item, ensure_ascii=False) if catalog_item else '（无）'}\n\n"
        "请仅润色当前节点 description，要求：\n"
        "1. 保留原有业务事实、范围、对象、口径、异常处理和输出要求。\n"
        "2. 如果原描述过短，可以结合 Skill 目标和节点能力说明补足可执行表达，但不能编造具体事实。\n"
        "3. 不要输出技术实现、接口参数、代码、字段 schema、循环或分支 DSL。\n"
        "4. 用一句中文业务要求表达，建议 40-160 字。\n"
        "5. 返回 JSON：{\"text\":\"润色后的节点要求\"}。"
    )
    llm = get_llm_client(streaming=False, stage="admin_workflow_node_polish", intent="generation")
    resp = await llm.ainvoke(
        [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=user_prompt),
        ]
    )
    parsed = _extract_json_object(str((resp.content if resp else "") or ""))
    text = re.sub(r"\s+", " ", str(parsed.get("text") or parsed.get("description") or "").strip())[:420]
    return text or current_text


async def _check_workflow_logic_with_llm(payload: WorkflowLogicCheckRequest) -> Dict[str, Any]:
    name = payload.name.strip()
    description = str(payload.description or "").strip()
    scenario = str(payload.scenario or "").strip()
    steps = [str(item or "").strip() for item in list(payload.steps or []) if str(item or "").strip()]
    nodes = [
        node for idx, raw in enumerate(list(payload.nodes or []))
        for node in [_normalize_workflow_node(raw, idx)]
        if node
    ]
    system_prompt = (
        "你是资深业务分析师，负责检查非技术用户编写的自然语言业务步骤是否已经足够清楚。"
        "当前检查目标不是执行任务，也不是生成技术工作流，而是判断这些业务步骤是否适合作为后续结构化工作流解析的输入。"
        "检查时必须基于 Skill 名称、描述、使用场景和当前步骤本身，不能编造用户没有提供的业务事实。"
        "如果步骤依赖内部规定、历史口径、知识库、经营标准或会议结论，应检查它是否说明了优先查找/确认以及无法获取时的兜底处理。"
        "不要输出工具、接口、API、数据库、HTTP、节点、字段映射等技术实现建议。"
        "只输出 JSON，不要输出 Markdown 或解释性前后缀。"
    )
    user_prompt = (
        f"Skill 名称：{name}\n"
        f"技能描述：{description or '（无）'}\n"
        f"使用场景：{scenario or '（无）'}\n"
        f"当前业务步骤：{json.dumps(steps, ensure_ascii=False)}\n"
        f"当前语义节点：{json.dumps(nodes, ensure_ascii=False)}\n\n"
        "请返回检查结果 JSON，格式必须为：\n"
        "{\n"
        "  \"pass\": true,\n"
        "  \"logic\": {\"label\": \"适合解析或需要澄清\", \"level\": \"success或warning\", \"summary\": \"一句话说明整体逻辑情况\"},\n"
        "  \"coverage\": [\n"
        "    {\"key\":\"goal\", \"label\":\"业务目标\", \"covered\":true},\n"
        "    {\"key\":\"input_scope\", \"label\":\"输入边界\", \"covered\":true},\n"
        "    {\"key\":\"default_rule\", \"label\":\"默认规则\", \"covered\":true},\n"
        "    {\"key\":\"decision_rule\", \"label\":\"判断标准\", \"covered\":true},\n"
        "    {\"key\":\"exception\", \"label\":\"异常处理\", \"covered\":true},\n"
        "    {\"key\":\"output\", \"label\":\"输出要求\", \"covered\":true}\n"
        "  ],\n"
        "  \"readiness\": [\n"
        "    {\"key\":\"step_count\", \"label\":\"步骤数量足够\", \"ready\":true},\n"
        "    {\"key\":\"branch_seed\", \"label\":\"可识别默认/异常分支\", \"ready\":true},\n"
        "    {\"key\":\"rule_seed\", \"label\":\"可提取业务判断规则\", \"ready\":true},\n"
        "    {\"key\":\"io_seed\", \"label\":\"可推导输入输出边界\", \"ready\":true}\n"
        "  ],\n"
        "  \"suggestions\": [\"最多5条具体补充建议\"],\n"
        "  \"conclusion\": \"本次检查结论\"\n"
        "}\n\n"
        "判断标准：\n"
        "1. 业务目标、输入边界、默认规则、判断标准、异常处理、输出要求都较清楚时，pass 才能为 true。\n"
        "2. 如果步骤里引用外部依据但没有说明查找/确认失败时怎么办，异常处理或默认规则应判为不足。\n"
        "3. 建议必须具体指出缺什么、应如何用业务语言补充，不要给技术实现建议。"
    )
    llm = get_llm_client(streaming=False, stage="admin_workflow_check", intent="evaluation")
    resp = await llm.ainvoke(
        [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=user_prompt),
        ]
    )
    parsed = _extract_json_object(str((resp.content if resp else "") or ""))
    return _normalize_workflow_check_result(parsed)


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
async def generate_workflow_steps(payload: WorkflowStepsGenerateRequest) -> ApiResponse:
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
async def generate_workflow_nodes(payload: WorkflowNodesGenerateRequest) -> ApiResponse:
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
async def polish_workflow_node(payload: WorkflowNodePolishRequest) -> ApiResponse:
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
async def check_workflow_logic(payload: WorkflowLogicCheckRequest) -> ApiResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill name is required")
    source = "llm"
    message = "success"
    try:
        result = await _check_workflow_logic_with_llm(payload)
    except Exception as exc:
        log_print(f"[skills] check_workflow_logic failed: {exc}", flush=True)
        result = {}
        source = "error"
        message = str(exc) or "检查失败"
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
async def check_workflow_nodes(payload: WorkflowLogicCheckRequest) -> ApiResponse:
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
        result = await _check_workflow_logic_with_llm(enriched_payload)
    except Exception as exc:
        log_print(f"[skills] check_workflow_nodes failed: {exc}", flush=True)
        result = {}
        source = "error"
        message = str(exc) or "检查失败"
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
async def check_script_plugin(payload: ScriptPluginCheckRequest) -> ApiResponse:
    static_result = _validate_script_plugin_static(payload.code)
    source = "rules"
    message = "success"
    llm_result = None
    if static_result.get("rulePass"):
        source = "rules+llm"
        try:
            llm_result = await _review_script_plugin_with_llm(payload, static_result)
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
    return ApiResponse(
        code=0,
        message=message,
        data={
            **static_result,
            "pass": bool(static_result.get("rulePass")),
            "llm": llm_result,
            "source": source,
            "message": message,
        },
    )


@router.post("/skills/fix-script-plugin", response_model=ApiResponse)
async def fix_script_plugin(payload: ScriptPluginFixRequest) -> ApiResponse:
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
            "check": recheck,
        },
    )


@router.post("/skills/generate-script-plugin", response_model=ApiResponse)
async def generate_script_plugin(payload: ScriptPluginGenerateRequest) -> ApiResponse:
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
            "check": check,
        },
    )


@router.get("/skills", response_model=ApiResponse)
async def list_skills(
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    main_id = main_id_snake or main_id
    skills = await user_skill_service.list_skills(user_id, main_id=main_id)
    policy = await MongoEmployeePolicyResolver().resolve(main_id, user_id)
    skills = [item for item in skills if policy.allows_skill(str(item.get("id") or item.get("_id") or ""))]
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
    policy = await MongoEmployeePolicyResolver().resolve(resolved_main_id, user_id)

    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for skill in list(user_skills or []) + list(org_skills or []):
        if not isinstance(skill, dict):
            continue
        if not _safe_bool(skill.get("enabled"), _safe_bool(skill.get("is_active"), True)):
            continue
        skill_id = str(skill.get("id") or skill.get("_id") or "").strip()
        if not policy.allows_skill(skill_id):
            continue
        if not skill_id or skill_id in seen:
            continue
        current_scope = _skill_source_scope(skill)
        if source_scope != "all" and current_scope != source_scope:
            continue
        if not _matches_skill_keyword(skill, keyword):
            continue
        seen.add(skill_id)
        items.append(_selectable_skill_item(skill))

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


@router.post("/skills", response_model=ApiResponse)
async def create_admin_shape_skill(
    payload: AdminShapeSkillPayload,
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    resolved_main_id = main_id_snake or main_id
    created = await user_skill_service.create_skill(
        user_id,
        _admin_shape_payload_to_user_payload(payload, user_id=user_id, main_id=resolved_main_id),
    )
    return ApiResponse(code=0, message="success", data=_admin_shape_skill(created))


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
    updated = await user_skill_service.update_skill(user_id, skill_id, updates, main_id=resolved_main_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Skill not found")
    return ApiResponse(code=0, message="success", data=_admin_shape_skill(updated))


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
    admin_payload = AdminShapeSkillPayload(
        name=str(current.get("name") or "Untitled Skill"),
        description=str(current.get("description") or ""),
        scenario=str(current.get("scenario") or current.get("notes") or ""),
        type=str(current.get("type") or ("workflow" if str(current.get("skill_type") or "") == "composite_task" else "writing_style")),
        config=_safe_dict(current.get("config")),
        enabled=bool(payload.enabled),
    )
    updates = _admin_shape_payload_to_user_payload(admin_payload, user_id=user_id, main_id=resolved_main_id)
    updated = await user_skill_service.update_skill(user_id, skill_id, updates, main_id=resolved_main_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Skill not found")
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
