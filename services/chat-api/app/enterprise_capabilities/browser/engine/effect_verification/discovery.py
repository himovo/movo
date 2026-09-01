from __future__ import annotations

import json
import re
from typing import Any, Dict

from pydantic import BaseModel, Field

from app.llm.factory import get_request_scoped_llm_client
from app.llm.types import Message, Role
from app.llm.decision_turn import DecisionOutput, DecisionTurnSpec, invoke_structured_decision

from .contract_normalization import normalize_discovered_contract
from .contracts import EffectContract


_COMMIT_RULES = (
    ("send", re.compile(r"^(发送|立即发送|确认发送|send|send now)$", re.I), "external"),
    ("publish", re.compile(r"^(发布|立即发布|确认发布|publish|post)$", re.I), "external"),
    ("delete", re.compile(r"^(删除|确认删除|永久删除|移除|delete|remove)$", re.I), "destructive"),
    ("submit", re.compile(r"^(提交|确认提交|递交|submit|confirm submission)$", re.I), "write"),
    ("save", re.compile(r"^(保存|保存修改|保存并关闭|save|save changes)$", re.I), "write"),
    ("create", re.compile(r"^(创建|确认创建|添加并保存|create|create now)$", re.I), "write"),
    ("approve", re.compile(r"^(批准|通过|同意|确认通过|approve|accept)$", re.I), "write"),
    ("reject", re.compile(r"^(驳回|拒绝|reject|decline)$", re.I), "write"),
)

# Query controls can appear inside a write-oriented browser node, but clicking
# them still only changes the page's read/navigation state.  Classify these
# exact semantic actions before consulting the model so a broad node goal such
# as "search, then publish" cannot turn the search button into a pending write.
_QUERY_ACTION = re.compile(
    r"^(?:搜索|查询|检索|查找|开始搜索|立即搜索|search|find|look\s*up|run\s+search)$",
    re.I,
)

_MUTATION_ACTION_HINT = re.compile(
    r"^(?:(?:立即|确认|继续)\s*)?(?:发送|发布|删除|移除|提交|保存|创建|新增|添加|"
    r"批准|通过|拒绝|驳回|修改|更新)|"
    r"^(?:(?:confirm|continue)\s+)?(?:send|publish|post|delete|remove|submit|save|"
    r"create|add|approve|accept|reject|decline|update|edit)\b",
    re.I,
)

_READ_ONLY_INTENT = re.compile(
    r"(?:只|仅).{0,12}(?:浏览|搜索|检索|查找|读取|查看|打开|返回)|"
    r"(?:不要|禁止|不得|无需).{0,24}(?:发送|发布|提交|保存|创建|新增|添加|修改|更新|删除|点赞|收藏|关注|评论|回答)|"
    r"(?:read|browse|search|inspect|open).{0,20}(?:only)|"
    r"(?:do not|don't|must not|without).{0,24}(?:send|publish|post|submit|save|create|add|update|edit|delete|like|follow|comment|answer)",
    re.I,
)


class _DiscoveredContract(DecisionOutput):
    is_commit: bool | None = None
    action_name: Any = ""
    operation_family: Any = "custom"
    entity: Any = ""
    side_effect: Any = None
    completes_goal: Any = False
    fingerprint: Any = Field(default_factory=dict)
    expected_effects: Any = Field(default_factory=list)
    verification_hints: Any = Field(default_factory=list)


async def discover_effect_contract(
    *,
    goal: str,
    capability_id: str,
    target: Dict[str, Any],
    lang: str,
    original_request: str = "",
    llm: Any = None,
) -> EffectContract:
    label = _target_label(target)
    local = _local_contract(goal=goal, capability_id=capability_id, label=label)
    if local is not None:
        return local
    if not _may_mutate(goal, original_request, capability_id, target):
        return EffectContract(action_name=label or "click", side_effect="none", is_commit=False)

    client = llm or get_request_scoped_llm_client(
        streaming=False,
        intent="browser_automation",
        stage="browser_effect_discovery",
    )
    system = (
        "你只判断一次浏览器点击是否会提交真实业务操作，并生成开放式结果验证契约。"
        "常见动作族可以使用 create/update/delete/submit/publish/send/transition；特殊动作必须使用能表达业务含义的自定义 operation_family，不能因为不在枚举中就判定不支持。"
        "is_commit 只在本次点击会真正写入、发送、发布、删除、审批或触发外部副作用时为 true；打开表单、切换页面、选择菜单不是 commit。"
        "action_name 使用 clicked_target 中本次点击动作的简短名称；如果页面名称已经准确，直接沿用。"
        "fingerprint 只保留目标描述中已经给出的业务字段，不得编造。verification_hints 描述如何回查结果，不得写站点专用代码。"
    ) if lang.startswith("zh") else (
        "Decide whether one browser click commits a real business side effect and produce an open-ended verification contract. "
        "Common families may be create/update/delete/submit/publish/send/transition; use a descriptive custom family for special actions. "
        "Opening a form or changing views is not a commit. Use the clicked target's concise action label as action_name. "
        "Never invent fingerprint values."
    )
    payload = {
        "goal": goal[:2000],
        "node_capability": capability_id,
        "clicked_target": {
            "role": target.get("role"),
            "name": target.get("name"),
            "text": target.get("text"),
            "type": target.get("type"),
        },
    }
    try:
        result = await invoke_structured_decision(
            client,
            _DiscoveredContract,
            [
                Message(role=Role.SYSTEM, content=system),
                Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
            ],
            spec=DecisionTurnSpec(locale=lang, turn_id="browser.effect_discovery"),
        )
        data = normalize_discovered_contract(
            result.model_dump(mode="json"),
            target_label=label,
        )
        return EffectContract(**data, source="model")
    except Exception:
        return EffectContract(
            action_name=label or "unknown action",
            operation_family="custom",
            side_effect="write",
            is_commit=False,
            expected_effects=[],
            verification_hints=["重新读取业务对象并确认预期状态变化"],
            source="model",
        )


def _local_contract(*, goal: str, capability_id: str, label: str) -> EffectContract | None:
    normalized = re.sub(r"\s+", " ", label).strip()
    if _QUERY_ACTION.fullmatch(normalized):
        return EffectContract(
            action_name=normalized,
            operation_family="search",
            side_effect="none",
            is_commit=False,
            completes_goal=False,
            source="local_rule",
        )
    for family, pattern, side_effect in _COMMIT_RULES:
        if not pattern.fullmatch(normalized):
            continue
        return EffectContract(
            action_name=normalized,
            operation_family=family,
            entity=_entity_hint(goal),
            side_effect=side_effect,  # type: ignore[arg-type]
            is_commit=True,
            completes_goal=not _looks_multi_operation(goal),
            fingerprint=_fingerprint(goal),
            expected_effects=["业务对象状态发生变化", "提交入口关闭或页面进入后续状态"],
            verification_hints=["捕获瞬时状态提示", "根据业务指纹回查对象状态"],
            source="local_rule",
        )
    return None


def read_only_navigation_contract(target: Dict[str, Any]) -> EffectContract | None:
    """Classify ordinary links before any side-effect model call.

    Following a link can move the browser to another business object, but it
    does not itself write that object. Semantic write-object alignment belongs
    on the later commit control, not on list/result navigation.
    """
    role = str(target.get("role") or "").strip().casefold()
    href = str(target.get("href") or "").strip()
    if role != "link" and not href:
        return None
    label = _target_label(target) or "open link"
    # Links are normally navigation, but some applications implement real
    # commits as anchors. Never bypass effect verification when the visible
    # action itself has write semantics.
    if _MUTATION_ACTION_HINT.search(re.sub(r"\s+", " ", label).strip()):
        return None
    return EffectContract(
        action_name=label,
        operation_family="navigate",
        entity="",
        side_effect="none",
        is_commit=False,
        completes_goal=False,
        source="local_rule",
    )


def _target_label(target: Dict[str, Any]) -> str:
    for key in ("name", "text", "value", "aria_label"):
        value = str(target.get(key) or "").strip()
        if value:
            return value[:160]
    return ""


def _may_mutate(
    goal: str,
    original_request: str,
    capability_id: str,
    target: Dict[str, Any],
) -> bool:
    cap = str(capability_id or "").lower()
    if cap in {"browser.submit", "browser.modify", "browser.delete", "browser.publish"}:
        return True
    if cap in {
        "browser.navigate",
        "browser.navigate_and_extract",
        "browser.browse",
        "browser.read",
        "browser.search",
    }:
        return False
    text = f"{goal or ''}\n{original_request or ''}"
    if _READ_ONLY_INTENT.search(text):
        return False
    return str(target.get("role") or "").lower() in {"button", "menuitem"}


def _looks_multi_operation(goal: str) -> bool:
    text = str(goal or "").lower()
    return bool(re.search(r"(多个|每个|分别|批量|所有|逐一|each|multiple|all\s+of|batch)", text))


def _entity_hint(goal: str) -> str:
    text = re.sub(r"\s+", " ", str(goal or "")).strip()
    return text[:160]


def _fingerprint(goal: str) -> Dict[str, Any]:
    text = str(goal or "")
    values: Dict[str, Any] = {}
    emails = list(dict.fromkeys(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)))
    if emails:
        values["email"] = emails[:5]
    quoted = list(dict.fromkeys(re.findall(r"[\"'“”‘’]([^\"'“”‘’]{2,80})[\"'“”‘’]", text)))
    if quoted:
        values["quoted_values"] = quoted[:5]
    return values
