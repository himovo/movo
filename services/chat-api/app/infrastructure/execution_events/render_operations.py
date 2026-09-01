from __future__ import annotations

import re
from typing import Any, Dict

from .operation import operation_event


_FORMAT_NAMES = {
    "docx": ("Word 文档", "Word document"),
    "pdf": ("PDF 文档", "PDF document"),
    "pptx": ("PowerPoint 演示文稿", "PowerPoint presentation"),
    "xlsx": ("Excel 工作簿", "Excel workbook"),
}


class RenderOperation:
    """Lifecycle for one real renderer invocation."""

    def __init__(self, *, fmt: str, index: int, language: str, scope: str = "") -> None:
        self.fmt = str(fmt or "").strip().lower()
        safe_scope = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(scope or "delivery"))[:80]
        self.operation_id = f"operation_render_{safe_scope}_{self.fmt}_{index}"
        zh, en = _FORMAT_NAMES.get(self.fmt, (self.fmt.upper(), self.fmt.upper()))
        self.label = f"导出 {zh}" if str(language or "").startswith("zh") else f"Export {en}"

    def _event(self, state: str, detail: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return operation_event(
            state,
            operation_id=self.operation_id,
            label=self.label,
            category="render",
            parent_id="delivery",
            detail=detail,
        )

    def started(self) -> Dict[str, Any]:
        return self._event("started", {"format": self.fmt})

    def completed(self) -> Dict[str, Any]:
        return self._event("completed", {"format": self.fmt})

    def failed(self, error: str) -> Dict[str, Any]:
        return self._event("failed", {"format": self.fmt, "error": str(error or "")[:240]})
