"""Semantic consistency checks for goal-directed browser actions.

The browser planner chooses concrete DOM refs, while effect verification tracks
side effects.  This module connects the two without knowing anything about a
specific site: it compares the business object requested by the goal with the
object named by a target or observed after an action.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Literal

from pydantic import BaseModel, Field

from app.llm.factory import get_request_scoped_llm_client
from app.llm.types import Message, Role
from app.llm.decision_turn import DecisionOutput, DecisionTurnSpec, invoke_structured_decision
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


AlignmentStatus = Literal["compatible", "incompatible", "unknown"]


class SemanticDescriptor(BaseModel):
    operation: str = ""
    entity: str = ""
    confidence: float = 0.0
    evidence: str = ""


class SemanticAlignment(BaseModel):
    status: AlignmentStatus = "unknown"
    confidence: float = 0.0
    intended: SemanticDescriptor = Field(default_factory=SemanticDescriptor)
    observed: SemanticDescriptor = Field(default_factory=SemanticDescriptor)
    reason: str = ""
    source: Literal["local_rule", "model", "fallback"] = "fallback"

    @property
    def blocks_action(self) -> bool:
        return self.status == "incompatible" and self.confidence >= 0.78


class _AlignmentDecision(DecisionOutput):
    status: AlignmentStatus
    confidence: float = 0.0
    intended: SemanticDescriptor = Field(default_factory=SemanticDescriptor)
    observed: SemanticDescriptor = Field(default_factory=SemanticDescriptor)
    reason: str = ""


_ACTION_WORDS = re.compile(
    r"(?:立即|确认|开始|继续|完成|去|请|一下|now|please|confirm|start|continue|finish)?"
    r"(?:新建|新增|创建|添加|写|撰写|编辑|修改|更新|删除|移除|提交|发布|发表|发送|保存|"
    r"批准|通过|拒绝|驳回|回复|查看|打开|选择|执行|处理|"
    r"create|add|new|write|compose|edit|update|delete|remove|submit|publish|post|send|"
    r"save|approve|accept|reject|reply|view|open|select|execute|process)"
    r"(?:立即|确认|一下|now)?",
    re.I,
)
_NOISE = re.compile(r"[\s\W_]+", re.UNICODE)


async def assess_target_alignment(
    *,
    goal: str,
    original_request: str,
    target: Dict[str, Any],
    lang: str,
    llm: Any = None,
) -> SemanticAlignment:
    label = target_label(target)
    target_entity = _open_entity(label)
    objective = _objective(goal, original_request)

    # A target whose explicit object is already present in the objective is
    # safely compatible. A pure operation label ("Submit", "Save") carries
    # no contradictory object and remains eligible for normal verification.
    if not target_entity or (
        _locally_same_entity(goal, original_request, target_entity)
        and not _entity_is_negated(objective, target_entity)
    ):
        return SemanticAlignment(
            status="compatible",
            confidence=0.92 if target_entity else 0.72,
            intended=SemanticDescriptor(entity=target_entity if target_entity else "", confidence=0.72),
            observed=SemanticDescriptor(entity=target_entity, confidence=0.9 if target_entity else 0.0, evidence=label),
            reason="目标元素未包含冲突的业务对象",
            source="local_rule",
        )

    payload = {
        "original_user_request": original_request[:2000],
        "current_browser_node_goal": goal[:2000],
        "target": _target_payload(target),
    }
    return await _model_alignment(payload=payload, surface="target", lang=lang, llm=llm)


async def assess_outcome_alignment(
    *,
    intended_operation: str,
    intended_entity: str,
    after: Observation,
    lang: str,
    llm: Any = None,
) -> SemanticAlignment:
    if not intended_entity:
        return SemanticAlignment(status="unknown", reason="目标契约没有可比较的业务对象")
    payload = {
        "intended": {"operation": intended_operation, "entity": intended_entity},
        "result_surface": _outcome_payload(after),
    }
    return await _model_alignment(payload=payload, surface="outcome", lang=lang, llm=llm)


async def _model_alignment(
    *, payload: Dict[str, Any], surface: str, lang: str, llm: Any,
) -> SemanticAlignment:
    client = llm or get_request_scoped_llm_client(
        streaming=False,
        intent="browser_automation",
        stage=f"browser_semantic_{surface}_alignment",
    )
    if lang.startswith("zh"):
        system = (
            "你是浏览器动作的语义安全校验器。业务实体是开放字符串，不能依赖站点名称或固定实体枚举。"
            "当前浏览器节点目标定义本节点要做的动作，用户原始请求只补充最终意图和禁止条件；不能要求一个中间节点完成整个原始请求。"
            "先仅根据这两项提取 intended.operation/entity；再仅根据 target 或 result_surface "
            "提取 observed.operation/entity，禁止用用户目标改写页面证据。最后判断两者是否指向同一种业务对象和相容动作。"
            "例如创建A与创建B、发布A与发布B是 incompatible；打开A编辑器与最终发布A可以 compatible。"
            "打开菜单、切换页面、搜索、登录等不产生其他业务对象的必要中间动作应判为 compatible 或 unknown，不能仅因按钮名称不同就拦截。"
            "证据不足返回 unknown。entity 使用简短、规范的业务对象名称；reason 必须引用输入中的具体文字。"
        )
    else:
        system = (
            "You are a semantic safety gate for browser actions. Business entities are open strings; do not rely on a site-specific "
            "or fixed entity list. The browser node goal defines this node's action; the original request only adds final intent and constraints. "
            "Do not require an intermediate node to complete the full request. Derive intended operation/entity from those inputs, then derive observed "
            "operation/entity only from the target or result surface. Never relabel page evidence to match the goal. Different business "
            "objects are incompatible; opening an editor and publishing the same object may be compatible. Navigation, menus, search and login "
            "that create no conflicting business object are compatible or unknown prerequisites. Return unknown if evidence is weak."
        )
    try:
        result = await invoke_structured_decision(
            client,
            _AlignmentDecision,
            [
                Message(role=Role.SYSTEM, content=system),
                Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
            ],
            spec=DecisionTurnSpec(locale=lang, turn_id=f"browser.{surface}_alignment"),
        )
        confidence = max(0.0, min(1.0, float(result.confidence)))
        status: AlignmentStatus = result.status
        # An incompatibility must identify both sides. This prevents a model
        # from blocking ordinary navigation based on a vague suspicion.
        if status == "incompatible" and not (
            result.intended.entity.strip() and result.observed.entity.strip()
        ):
            status = "unknown"
            confidence = min(confidence, 0.5)
        return SemanticAlignment(
            status=status,
            confidence=confidence,
            intended=result.intended,
            observed=result.observed,
            reason=result.reason,
            source="model",
        )
    except Exception as exc:
        return SemanticAlignment(
            status="unknown",
            confidence=0.0,
            reason=f"语义校验模型不可用: {type(exc).__name__}",
            source="fallback",
        )


def target_label(target: Dict[str, Any]) -> str:
    for key in ("name", "text", "value", "aria_label", "description"):
        value = str(target.get(key) or "").strip()
        if value:
            return value[:200]
    return ""


def _open_entity(label: str) -> str:
    text = re.sub(r"\s+", " ", str(label or "")).strip()
    if not text:
        return ""
    stripped = _ACTION_WORDS.sub("", text).strip(" -_:/|·，。！!？?()（）[]【】")
    # Keep the entity open-ended. This parser removes generic action words;
    # it never enumerates business objects such as tickets, posts or records.
    return stripped[:80] if len(stripped) >= 1 else ""


def _locally_same_entity(goal: str, original_request: str, entity: str) -> bool:
    needle = _NOISE.sub("", entity).lower()
    if not needle:
        return False
    for value in (goal, original_request):
        candidate = _NOISE.sub("", _open_entity(value)).lower()
        if not candidate:
            continue
        if candidate == needle:
            return True
        shorter, longer = sorted((candidate, needle), key=len)
        # Containment is only decisive when the two phrases are similar in
        # size. This avoids treating a contextual noun in a long instruction
        # as the requested object.
        if shorter in longer and len(shorter) / max(1, len(longer)) >= 0.65:
            return True
    return False


def _entity_is_negated(objective: str, entity: str) -> bool:
    text = str(objective or "")
    entity_text = str(entity or "").strip()
    if not text or not entity_text:
        return False
    escaped = re.escape(entity_text)
    zh = re.compile(rf"(?:不要|禁止|不可|不能|别|无需|不允许)[^，。；\n]{{0,18}}{escaped}", re.I)
    en = re.compile(rf"(?:do\s+not|don't|never|must\s+not|without)[^,.;\n]{{0,40}}{escaped}", re.I)
    return bool(zh.search(text) or en.search(text))


def _objective(goal: str, original_request: str) -> str:
    values = [str(original_request or "").strip(), str(goal or "").strip()]
    return "\n".join(value for value in values if value)


def _target_payload(target: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: target.get(key)
        for key in ("role", "name", "text", "type", "aria_label", "description")
        if target.get(key) not in (None, "")
    }


def _outcome_payload(observation: Observation) -> Dict[str, Any]:
    elements = []
    for item in list(observation.elements or [])[:100]:
        if not isinstance(item, dict):
            continue
        elements.append({
            key: item.get(key)
            for key in ("role", "name", "text", "description")
            if item.get(key) not in (None, "")
        })
    effects = [item for item in list(observation.effects or [])[-40:] if isinstance(item, dict)]
    return {
        "url": observation.url,
        "title": observation.title,
        "page_text": str(observation.page_text or "")[:3000],
        "elements": elements,
        "effects": effects,
    }
