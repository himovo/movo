from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.llm.base import BaseLLMClient
from app.llm.factory import get_request_scoped_llm_client
from app.llm.types import Message, Role

from .contracts import CachedWorkflowStep
from .manual_plan import build_manual_recording_plan


class ManualWorkflowClassification(BaseModel):
    display_name: str = Field(min_length=2, max_length=60)
    operation: str = Field(min_length=2, max_length=160)
    capability_id: str = "browser.navigate"


@dataclass(frozen=True)
class ManualRecordingAnalysis:
    display_name: str
    operation: str
    capability_id: str
    event_count: int
    action_count: int
    steps: list[Dict[str, Any]]
    complete: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "display_name": self.display_name,
            "operation": self.operation,
            "capability_id": self.capability_id,
            "event_count": self.event_count,
            "action_count": self.action_count,
            "steps": self.steps,
            "complete": self.complete,
            "reasons": list(self.reasons),
        }


class ManualRecordingAnalyzer:
    def __init__(self, llm: BaseLLMClient | None = None) -> None:
        self._llm = llm or get_request_scoped_llm_client(
            streaming=False,
            stage="browser_recording_naming",
            intent="browser_automation",
        )

    async def analyze(self, events: Iterable[Dict[str, Any]]) -> ManualRecordingAnalysis:
        recorded = [dict(item) for item in events if isinstance(item, dict)]
        actions = [
            item for item in recorded
            if str(item.get("type") or "") not in {"", "recording_started", "recording_stopped"}
        ]
        summaries = [_event_summary(item) for item in actions]
        try:
            classification = await self._classify(summaries)
        except Exception:
            classification = _fallback_classification(summaries)
        plan = build_manual_recording_plan(
            events=recorded,
            operation=classification.operation,
            display_name=classification.display_name,
            capability_id=classification.capability_id,
        )
        return ManualRecordingAnalysis(
            display_name=classification.display_name,
            operation=classification.operation,
            capability_id=plan.capability_id,
            event_count=len(recorded),
            action_count=len(actions),
            steps=[_preview_step(index, step) for index, step in enumerate(plan.compiled.steps, 1)],
            complete=plan.complete,
            reasons=plan.reasons,
        )

    async def _classify(self, steps: list[Dict[str, Any]]) -> ManualWorkflowClassification:
        response = await self._llm.ainvoke_structured(
            [
                Message(
                    role=Role.SYSTEM,
                    content=(
                        "Infer the reusable business workflow represented by recorded browser actions. "
                        "Generate a concise Chinese display name and a natural-language operation description. "
                        "Name the actual final outcome, not exploratory clicks. Choose capability_id from: "
                        "browser.navigate, browser.search, browser.submit, browser.modify, browser.delete, "
                        "browser.publish, browser.file_transfer. A save/submit/publish/delete terminal action "
                        "must use the corresponding write capability. Return only the schema."
                    ),
                ),
                Message(role=Role.USER, content=json.dumps({"recorded_steps": steps}, ensure_ascii=False)),
            ],
            ManualWorkflowClassification,
        )
        capability = str(response.capability_id or "").strip().lower()
        allowed = {
            "browser.navigate", "browser.search", "browser.submit", "browser.modify",
            "browser.delete", "browser.publish", "browser.file_transfer",
        }
        return response.model_copy(update={
            "display_name": " ".join(str(response.display_name or "").split())[:60],
            "operation": " ".join(str(response.operation or "").split())[:160],
            "capability_id": capability if capability in allowed else "browser.navigate",
        })


def _event_summary(event: Dict[str, Any]) -> Dict[str, Any]:
    target = event.get("target") if isinstance(event.get("target"), dict) else {}
    url = str(event.get("after_url") or event.get("url") or "")
    parsed = urlparse(url)
    return {
        "type": str(event.get("type") or ""),
        "site": str(parsed.hostname or "").lower(),
        "path": str(parsed.path or "")[:160],
        "target": {
            key: str(target.get(key) or "")[:160]
            for key in ("role", "name", "text", "placeholder", "semanticPurpose")
            if str(target.get(key) or "").strip()
        },
        "has_value": bool(event.get("value")) and not bool(event.get("value_redacted")),
        "media_count": int(event.get("file_count") or 0),
    }


def _preview_step(index: int, step: CachedWorkflowStep) -> Dict[str, Any]:
    locator = dict(step.locator or {})
    target = next((
        str(locator.get(key) or "").strip()
        for key in ("name", "text", "placeholder", "semanticPurpose", "role")
        if str(locator.get(key) or "").strip()
    ), "")
    return {
        "index": index,
        "tool": str(step.tool or ""),
        "target": target[:160],
        "parameterized": bool(step.arg_bindings or step.locator_bindings),
        "label": _step_label(step, target),
    }


def _step_label(step: CachedWorkflowStep, target: str) -> str:
    tool = str(step.tool or "")
    labels = {
        "browser_navigate": "打开页面",
        "browser_tab_new": "打开新标签页",
        "browser_click": "点击",
        "browser_fill": "填写",
        "browser_select": "选择",
        "browser_upload_file": "上传文件",
        "browser_paste_image": "插入图片",
        "browser_press": "按键",
        "browser_scroll": "滚动页面",
        "browser_wait_for": "等待页面就绪",
    }
    prefix = labels.get(tool, tool.removeprefix("browser_") or "浏览器操作")
    if target:
        return f"{prefix}「{target[:60]}」"
    return prefix


def _fallback_classification(steps: list[Dict[str, Any]]) -> ManualWorkflowClassification:
    corpus = " ".join(
        str(value or "")
        for step in steps
        for value in (step.get("type"), json.dumps(step.get("target") or {}, ensure_ascii=False))
    ).casefold()
    site = next((str(step.get("site") or "") for step in steps if step.get("site")), "网站")
    if any(token in corpus for token in ("保存", "草稿", "save")):
        outcome, capability = "保存草稿", "browser.submit"
    elif any(token in corpus for token in ("发布", "publish")):
        outcome, capability = "发布内容", "browser.publish"
    elif any(token in corpus for token in ("搜索", "search")):
        outcome, capability = "搜索内容", "browser.search"
    elif any(step.get("type") in {"fill", "select", "upload", "paste_image"} for step in steps):
        outcome, capability = "填写并提交表单", "browser.submit"
    else:
        outcome, capability = "打开目标页面", "browser.navigate"
    name = f"{site} {outcome}"
    return ManualWorkflowClassification(display_name=name[:60], operation=name[:160], capability_id=capability)


manual_recording_analyzer = ManualRecordingAnalyzer()


__all__ = [
    "ManualRecordingAnalysis", "ManualRecordingAnalyzer", "ManualWorkflowClassification",
    "manual_recording_analyzer",
]
