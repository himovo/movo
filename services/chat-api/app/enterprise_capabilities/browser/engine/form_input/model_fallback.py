from __future__ import annotations

import json
import logging
from typing import List, Literal

from pydantic import BaseModel, Field

from app.llm.factory import get_request_scoped_llm_client
from app.llm.types import Message, Role
from app.llm.decision_turn import DecisionOutput, DecisionTurnSpec, invoke_structured_decision

from .binding_authority import (
    authoritative_publish_candidate,
    contains_serialized_media,
    direct_authoritative_binding,
    has_structured_media,
)
from .contracts import FieldBinding, FieldDescriptor
from .input_context import BrowserInputContext


logger = logging.getLogger(__name__)


class _ModelBinding(BaseModel):
    field_key: str
    resolution: Literal["direct", "transform", "selection", "attachment", "skip"]
    candidate_id: str = ""
    value: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""


class _ModelPlan(DecisionOutput):
    bindings: List[_ModelBinding] = Field(default_factory=list)


class FormInputModelResolver:
    def __init__(self, llm=None) -> None:
        self._llm = llm or get_request_scoped_llm_client(
            streaming=False,
            intent="browser_automation",
            stage="browser_form_input_resolution",
        )

    async def resolve(
        self,
        *,
        fields: List[FieldDescriptor],
        context: BrowserInputContext,
        lang: str,
        task_goal: str = "",
    ) -> List[FieldBinding]:
        if not fields:
            return []
        field_map = {field.field_key: field for field in fields}
        candidates = context.by_id()
        payload = {
            "original_user_request": context.original_request[:3000],
            "current_browser_node_goal": str(task_goal or "")[:4000],
            "fields": [
                {
                    "field_key": field.field_key,
                    "label": field.semantic_label,
                    "placeholder_hint": field.placeholder,
                    "scope_id": field.scope_id,
                    "scope_name": field.scope_name,
                    "scope_role": field.scope_role,
                    "label_source": str(field.raw.get("labelSource") or field.raw.get("label_source") or ""),
                    "control_kind": field.control_kind,
                    "required": field.required,
                    "options": field.options[:50],
                }
                for field in fields
            ],
            "available_inputs": context.model_payload(),
        }
        system = _system_prompt(lang)
        try:
            result = await invoke_structured_decision(
                self._llm,
                _ModelPlan,
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
                ],
                spec=DecisionTurnSpec(locale=lang, turn_id="browser.form_input_resolution"),
            )
        except Exception as exc:
            logger.warning(
                "browser form input resolution failed",
                extra={"event": "browser.form_input_model_failed", "error": str(exc)},
            )
            return []
        return _validated_bindings(
            result.bindings,
            field_map=field_map,
            candidates=candidates,
            lang=lang,
        )


def _validated_bindings(raw, *, field_map, candidates, lang: str = "zh") -> List[FieldBinding]:
    bindings: List[FieldBinding] = []
    seen = set()
    all_candidates = list(candidates.values())
    for item in raw:
        field = field_map.get(item.field_key)
        if field is None or item.field_key in seen:
            continue
        authoritative = authoritative_publish_candidate(field, all_candidates)
        if item.resolution == "transform" and authoritative is not None:
            bindings.append(direct_authoritative_binding(
                field=field,
                candidate=authoritative,
                confidence=max(item.confidence, 0.99),
                rationale=(
                    f"{item.rationale} [publish_payload_authority] "
                    "preserved canonical upstream content"
                ).strip(),
            ))
            seen.add(item.field_key)
            continue
        candidate = candidates.get(item.candidate_id) if item.candidate_id else None
        if item.candidate_id and candidate is None:
            continue
        if item.resolution in {"direct", "attachment"} and candidate is None:
            continue
        binding = None
        if item.resolution == "direct":
            if candidate.value_kind == "file" or field.control_kind == "file":
                continue
            binding = FieldBinding(
                field_key=field.field_key, action="fill",
                source_kind="user_input" if candidate.source_kind == "user_input" else "upstream",
                value=str(candidate.value or ""), candidate_id=candidate.candidate_id,
                source_path=candidate.source_path, confidence=item.confidence,
                plain_text=candidate.plain_text,
                rich_html=candidate.rich_html,
                rationale=item.rationale,
            )
        elif item.resolution == "attachment":
            if field.control_kind != "file" or candidate.value_kind != "file":
                continue
            binding = FieldBinding(
                field_key=field.field_key, action="upload", source_kind="attachment",
                value=list(candidate.value or []), candidate_id=candidate.candidate_id,
                source_path=candidate.source_path, confidence=item.confidence,
                rationale=item.rationale,
            )
        elif item.resolution == "selection":
            option = _valid_option(item.value, field.options)
            if not option:
                continue
            binding = FieldBinding(
                field_key=field.field_key, action="select", source_kind="selection",
                value=option, candidate_id=item.candidate_id,
                source_path=candidate.source_path if candidate else "",
                confidence=item.confidence, rationale=item.rationale,
            )
        elif item.resolution == "transform":
            value = str(item.value or "").strip()
            if not value or field.control_kind in {"file", "toggle"}:
                continue
            if contains_serialized_media(value) and has_structured_media(all_candidates):
                continue
            binding = FieldBinding(
                field_key=field.field_key, action="fill", source_kind="transform",
                value=value, candidate_id=item.candidate_id,
                source_path=candidate.source_path if candidate else "",
                confidence=item.confidence, rationale=item.rationale,
            )
        elif item.resolution == "skip":
            binding = FieldBinding(
                field_key=field.field_key, action="skip", source_kind="unknown",
                confidence=item.confidence, rationale=item.rationale,
            )
        if binding is not None:
            bindings.append(binding)
            seen.add(item.field_key)
    return bindings


def _valid_option(value: str, options: List[str]) -> str:
    normalized = str(value or "").strip().casefold()
    for option in options:
        if option.strip().casefold() == normalized:
            return option
    return ""


def _system_prompt(lang: str) -> str:
    if str(lang or "").startswith("zh"):
        return (
            "你只负责为当前网页已经出现的表单字段制定输入绑定。field_key 和 candidate_id "
            "只能从输入候选中选择，禁止创造新标识。已有完整产物使用 direct，附件使用 attachment；"
            "只有标题、摘要、备注、分类等页面级短适配允许 transform/selection。不得在这里重新生成报告、"
            "文章等独立长篇业务产物；缺少这类产物或无法可靠判断时不要返回该字段绑定，由浏览器 Agent "
            "Loop 统一决定是否询问用户。selection.value 必须"
            "逐字来自该字段 options。可选字段在用户目标未要求且没有对应输入时必须 skip，只有完成用户目标"
            "确实需要的未解析字段才留给 Agent Loop。不要填写密码、验证码。每个字段最多返回一个绑定。"
            "current_browser_node_goal 是当前浏览器节点的直接执行目标，字段填写要求以它为准；"
            "original_user_request 只用于补充整体意图。对于每个传入字段，都必须返回一个绑定或明确 skip，"
            "不能静默遗漏。"
            "评论、回复、邮件说明等页面内短文本，如果原始请求和 available_inputs 已提供足够事实，"
            "应使用 transform 生成当前字段所需短文本；不得仅因字段标签是正文或内容就判定缺少长篇产物。"
            "若标题/主题字段缺少独立标题候选，但原始请求或上游正文已经明确主题，必须用 transform "
            "生成页面所需的短标题。"
            "placeholder_hint 只是网页提示，可能动态变化，绝不能把它当作待填写值或字段唯一身份。"
            "scope_name/scope_role 表示字段所属的业务容器，只能处理当前容器内的字段，不能跨容器组合。"
            "available_inputs 中标记 binding_authority=publish_payload 的标题/正文是上游权威产物，"
            "只能 direct，禁止 transform、摘要、重写或把图片拼成 HTML/Markdown 文本；"
            "图片文件必须保留给独立媒体事务处理。"
        )
    return (
        "Resolve inputs only for form fields already visible on the current page. Use only supplied field_key and "
        "candidate_id values. Use direct for complete inputs and attachment for files. transform/selection are only "
        "for short page-bound adaptations such as titles, summaries, notes, and categories. Never create a missing "
        "standalone report or article here; omit the field binding when required information is unavailable so the "
        "browser Agent Loop owns any user intervention. A selection value must "
        "exactly match one supplied option. Skip optional fields that are not requested and have no matching input; "
        "leave unresolved required fields to the Agent Loop. Never fill passwords or verification codes."
        " Treat current_browser_node_goal as the authoritative instruction for the current browser node and "
        "original_user_request as supporting context. Return one binding or an explicit skip for every supplied field."
        " For short page-bound comments, replies, or message text, use transform when the original request and "
        "available inputs provide enough facts; a generic content/body label alone does not imply a missing article."
        " If a title, subject, or headline field lacks a dedicated title candidate but the request or upstream body "
        "already establishes the topic, use transform to produce the short page-bound title."
        " placeholder_hint is an unstable page hint; never use it as the value to enter or as field identity."
        " scope_name and scope_role identify the owning interaction container; never combine fields across containers."
        " A title or body marked binding_authority=publish_payload is canonical upstream content: bind it directly and "
        "never transform, summarize, rewrite, or serialize its media as HTML/Markdown text. Structured media remains "
        "owned by the separate media transaction."
    )
