"""User-visible stages backed by actual content pipeline transitions."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from .timeline import ContentTimelineProjector


class ContentProgressReporter:
    def __init__(
        self,
        *,
        projector: ContentTimelineProjector,
        sink: Callable[[dict[str, Any]], Awaitable[None]],
        language: str,
    ) -> None:
        self._projector = projector
        self._sink = sink
        self._is_zh = str(language or "").lower().startswith("zh")

    async def emit(self, stage: str) -> None:
        zh = {
            "requirements": "正在解析写作要求、风格规范与证据边界",
            "planning": "正在规划正文结构、篇幅与质量要求",
            "direct": "已确定采用一次性长文写作",
            "sectional": "已确定采用分章节超长文写作",
        }
        en = {
            "requirements": "Resolving writing requirements, style rules, and evidence boundaries",
            "planning": "Planning the structure, length, and quality requirements",
            "direct": "Selected single-pass long-form writing",
            "sectional": "Selected sectional ultra-long-form writing",
        }
        text = (zh if self._is_zh else en).get(stage, "")
        if not text:
            return
        for row in self._projector.project({
            "type": "activity",
            "content": {"kind": "writing", "message": text},
        }):
            await self._sink(row)


__all__ = ["ContentProgressReporter"]
