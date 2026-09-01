"""Icon resolution utilities for presentation pipeline.

Icon library for the presentation pipeline.  The underlying
Tabler icon SVG assets are shared (backend/app/assets/tabler-icons/).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field

from app.llm.factory import get_llm_client
from app.llm.types import Message, Role


ICON_ASSET_DIR = Path(__file__).resolve().parents[2] / "assets" / "tabler-icons" / "outline"

CURATED_ICON_NAMES: Tuple[str, ...] = (
    "sparkles",
    "message-circle",
    "messages",
    "robot",
    "brain",
    "bulb",
    "clock",
    "calendar",
    "mail",
    "phone",
    "search",
    "users-group",
    "user",
    "briefcase",
    "building",
    "world",
    "target-arrow",
    "chart-line",
    "chart-bar",
    "chart-pie",
    "presentation",
    "database",
    "server",
    "cloud",
    "network",
    "settings",
    "settings-automation",
    "puzzle",
    "hierarchy",
    "git-branch",
    "file-text",
    "list-check",
    "check",
    "shield-lock",
    "shield-check",
    "lock",
    "key",
    "rocket",
    "device-laptop",
    "device-mobile",
    "photo",
    "video",
    "microphone",
    "map",
    "home",
    "click",
    "arrow-right",
)

LEGACY_ICON_NAME_ALIASES: Dict[str, str] = {
    "spark": "sparkles",
    "chat": "message-circle",
    "bot": "robot",
    "brain-circuit": "brain",
    "users": "users-group",
    "growth": "chart-line",
    "checklist": "list-check",
    "workflow": "settings-automation",
    "automation": "settings-automation",
    "filter": "settings-automation",
    "clean": "settings-automation",
    "tag": "hierarchy",
    "tags": "hierarchy",
    "label": "hierarchy",
    "labels": "hierarchy",
    "schedule": "calendar",
    "content-copy": "file-text",
    "content copy": "file-text",
    "gpp-maybe": "shield-lock",
    "gpp maybe": "shield-lock",
    "arrow-upward": "arrow-right",
    "arrow upward": "arrow-right",
}

ICON_DESCRIPTIONS: Dict[str, str] = {
    "sparkles": "generic highlight, emphasis, magic, upgrade",
    "message-circle": "chat, conversation, support, response",
    "messages": "discussion, multi-party communication, dialogue threads",
    "robot": "AI assistant, agent, bot, copilot",
    "brain": "knowledge, intelligence, reasoning, cognition",
    "bulb": "idea, strategy, innovation, insight",
    "clock": "time, duration, phase, timing",
    "calendar": "schedule, milestone, roadmap, timeline",
    "mail": "email, notification, inbox",
    "phone": "call, hotline, contact, mobile call",
    "search": "search, retrieval, lookup, discovery",
    "users-group": "team, organization, customer group, collaboration",
    "user": "individual owner, persona, profile",
    "briefcase": "business, project, case, work",
    "building": "enterprise, company, organization, office",
    "world": "global, internet, wide reach, ecosystem",
    "target-arrow": "goal, objective, target, focus",
    "chart-line": "growth, trend, KPI, performance",
    "chart-bar": "analysis, comparison, metrics, dashboard",
    "chart-pie": "share, composition, ratio, allocation",
    "presentation": "presentation, report, summary, briefing",
    "database": "data, repository, storage, knowledge base",
    "server": "system, backend, platform, infrastructure",
    "cloud": "cloud, SaaS, online service, hosting",
    "network": "network, connection, integration topology",
    "settings": "configuration, setup, settings",
    "settings-automation": "automation, workflow, orchestration, process",
    "puzzle": "modular, component, fit, assembly",
    "hierarchy": "structure, governance, layered organization, org chart",
    "git-branch": "branching, decision tree, fork, path split",
    "file-text": "document, report, policy, text content",
    "list-check": "task list, checklist, to-do, review items",
    "check": "complete, approved, success, verified",
    "shield-lock": "security, compliance, risk control, privacy",
    "shield-check": "trusted, quality assured, validated, governance",
    "lock": "access control, restricted, secure lock",
    "key": "credentials, permission, key access",
    "rocket": "launch, acceleration, rollout, growth push",
    "device-laptop": "platform, application, desktop system, digital workspace",
    "device-mobile": "mobile app, smartphone, on-the-go use",
    "photo": "image, portrait, visual, picture",
    "video": "video, recording, media, playback",
    "microphone": "voice, speech, audio, interview",
    "map": "location, geography, navigation, region",
    "home": "home, base, landing, central place",
    "click": "action, CTA, interaction, trigger",
    "arrow-right": "next step, continue, forward motion",
}

KEYWORD_RULES: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("security", "secure", "compliance", "risk", "privacy", "protect", "guard", "safety", "安全", "合规", "风险", "隐私", "治理"), "shield-lock"),
    (("verification", "trust", "approved", "quality", "success"), "shield-check"),
    (("growth", "revenue", "sales", "market", "trend", "metric", "performance", "kpi", "增长", "营收", "销售", "趋势", "指标", "成效", "效率", "成本"), "chart-line"),
    (("analytics", "report", "dashboard", "insight", "analysis"), "chart-bar"),
    (("share", "mix", "segment", "pie", "allocation", "ratio"), "chart-pie"),
    (("chat", "message", "conversation", "support", "feedback", "communication", "对话", "沟通", "消息", "反馈"), "message-circle"),
    (("messages", "dialogue", "discussion", "thread"), "messages"),
    (("user", "customer", "team", "people", "community", "audience", "org", "用户", "客户", "团队", "组织", "协作"), "users-group"),
    (("person", "individual", "profile", "owner"), "user"),
    (("data", "knowledge-base", "knowledge base", "repository", "record", "数据", "知识库", "存储", "资产"), "database"),
    (("ai", "agent", "assistant", "bot", "copilot", "智能体", "助手"), "robot"),
    (("thinking", "intelligence", "cognition", "knowledge", "推理", "智能", "知识"), "brain"),
    (("idea", "innovation", "strategy", "concept", "insight", "创意", "创新", "战略", "洞察"), "bulb"),
    (("system", "infrastructure", "backend", "server"), "server"),
    (("cloud", "saas", "hosting"), "cloud"),
    (("network", "connection", "topology", "routing"), "network"),
    (("settings", "config", "configuration"), "settings"),
    (("process", "workflow", "automation", "orchestration", "operation", "流程", "工作流", "自动化", "编排", "运营"), "settings-automation"),
    (("goal", "objective", "target", "mission", "目标", "使命", "聚焦"), "target-arrow"),
    (("business", "work", "project", "case"), "briefcase"),
    (("company", "enterprise", "office", "organization"), "building"),
    (("global", "world", "international", "web", "internet"), "world"),
    (("schedule", "timeline", "date", "deadline", "milestone", "计划", "时间线", "日期", "里程碑", "路线图"), "calendar"),
    (("time", "clock", "period", "phase"), "clock"),
    (("email", "mail", "inbox"), "mail"),
    (("phone", "call", "mobile"), "phone"),
    (("find", "search", "lookup", "discover", "搜索", "检索", "发现"), "search"),
    (("document", "file", "report", "proposal", "文档", "文件", "报告", "方案"), "file-text"),
    (("list", "todo", "task", "checklist", "清单", "任务", "待办"), "list-check"),
    (("confirm", "done", "complete", "pass"), "check"),
    (("lock", "access"), "lock"),
    (("key", "credential", "token"), "key"),
    (("launch", "go live", "startup", "启动", "上线", "落地", "推广"), "rocket"),
    (("laptop", "desktop", "computer", "device"), "device-laptop"),
    (("mobile", "app", "smartphone"), "device-mobile"),
    (("photo", "image", "portrait", "avatar"), "photo"),
    (("video", "recording", "camera"), "video"),
    (("audio", "voice", "podcast", "microphone"), "microphone"),
    (("map", "location", "navigation", "region"), "map"),
    (("home", "house", "base"), "home"),
    (("click", "tap", "cta", "action"), "click"),
    (("branch", "decision", "fork"), "git-branch"),
    (("hierarchy", "org chart", "structure", "layers"), "hierarchy"),
    (("puzzle", "fit", "module", "component"), "puzzle"),
    (("presentation", "deck", "slides", "演示", "汇报", "ppt"), "presentation"),
    (("arrow", "next", "forward", "continue"), "arrow-right"),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_token(text: str) -> str:
    return (
        str(text or "")
        .strip()
        .lower()
        .replace("_", "-")
        .replace("/", " ")
    )


def _tokenize_words(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", _normalize_token(text)) if token}


# ---------------------------------------------------------------------------
# Core resolution API
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def available_icon_names() -> Tuple[str, ...]:
    names = [path.stem for path in sorted(ICON_ASSET_DIR.glob("*.svg")) if path.is_file()]
    return tuple(names)


@lru_cache(maxsize=1)
def available_icon_name_set() -> set[str]:
    return set(available_icon_names())


def resolve_icon_name(raw: str, *, fallback: str = "sparkles") -> str:
    normalized = _normalize_token(raw)
    if not normalized:
        return fallback
    aliases = {
        normalized,
        normalized.replace(" ", "-"),
        normalized.replace("-", " "),
    }
    for alias in list(aliases):
        mapped = LEGACY_ICON_NAME_ALIASES.get(alias)
        if mapped:
            aliases.add(mapped)
    icon_names = available_icon_name_set()
    for alias in aliases:
        candidate = alias.replace(" ", "-")
        if candidate in icon_names:
            return candidate
    return fallback


def resolve_icon_from_texts(*texts: str, fallback: str = "sparkles") -> str:
    combined = " ".join(_normalize_token(text) for text in texts if str(text or "").strip())
    if not combined:
        return fallback
    tokens = _tokenize_words(combined)
    direct = resolve_icon_name(combined, fallback="")
    if direct:
        return direct
    for keywords, icon_name in KEYWORD_RULES:
        if any(
            (
                _normalize_token(keyword) in combined
                if (" " in keyword or "-" in keyword or not _normalize_token(keyword).isascii())
                else _normalize_token(keyword) in tokens
            )
            for keyword in keywords
        ):
            return icon_name
    return fallback


@lru_cache(maxsize=1)
def load_inline_svg_map() -> Dict[str, str]:
    svg_map: Dict[str, str] = {}
    for icon_name in available_icon_names():
        path = ICON_ASSET_DIR / f"{icon_name}.svg"
        if path.exists():
            raw = path.read_text(encoding="utf-8").strip()
            svg_map[icon_name] = re.sub(r"<!--.*?-->\s*", "", raw, flags=re.DOTALL).strip()
    return svg_map


# ---------------------------------------------------------------------------
# LLM-assisted icon selection
# ---------------------------------------------------------------------------


class IconBatchChoice(BaseModel):
    icons: List[str] = Field(default_factory=list)


async def choose_icons_with_llm(
    *,
    slot_id: str,
    items: List[Dict[str, Any]],
    icon_prompt: str = "",
) -> List[str]:
    sanitized_items = [dict(item or {}) for item in items]
    if not sanitized_items:
        return []
    candidates = [
        {
            "icon_name": icon_name,
            "description": ICON_DESCRIPTIONS.get(icon_name, ""),
        }
        for icon_name in CURATED_ICON_NAMES
    ]
    payload = {
        "slot_id": slot_id,
        "icon_prompt": str(icon_prompt or "").strip(),
        "items": [
            {
                "title": str(item.get("title") or "").strip(),
                "body": str(item.get("body") or "").strip(),
                "meta": str(item.get("meta") or "").strip(),
            }
            for item in sanitized_items
        ],
        "candidates": candidates,
    }
    system = (
        "You select icons for presentation cards.\n"
        "Choose exactly one icon_name for each item.\n"
        "You must only choose from the provided candidates.icon_name.\n"
        "Prefer concrete semantic fit over decorative icons.\n"
        "Use generic icons like sparkles only when nothing else clearly fits.\n"
        "Keep repeated icons only when the repeated concept is intentionally identical.\n"
        "Across unrelated items, vary icons by meaning while preserving one coherent visual family.\n"
        "Return JSON only matching this schema: {\"icons\": [\"...\"]}\n"
    )
    try:
        llm = get_llm_client(streaming=False, stage="compose", intent="generation")
        structured = llm.with_structured_output(IconBatchChoice, method="function_calling")
        result = await structured.ainvoke(
            [
                Message(role=Role.SYSTEM, content=system),
                Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
            ]
        )
        chosen = list(getattr(result, "icons", []) or [])
        resolved = [resolve_icon_name(str(name or ""), fallback="") for name in chosen]
        if len(resolved) == len(sanitized_items) and all(resolved):
            return resolved
    except Exception:
        pass
    return []
