from __future__ import annotations

from typing import Any, Dict

from .operation import operation_event


class QualityOperationEmitter:
    """Native operation lifecycle for validation, repair, and visual checks."""

    def __init__(self, language: str) -> None:
        self.is_zh = str(language or "").startswith("zh")
        self._review_index = 0
        self._repair_index = 0
        self._visual_index = 0
        self._review_id = "operation_quality_review_0"
        self._repair_id = "operation_quality_repair_0"
        self._visual_id = "operation_quality_visual_0"

    def _event(self, state: str, operation_id: str, zh: str, en: str, *, detail: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return operation_event(
            state,
            operation_id=operation_id,
            label=zh if self.is_zh else en,
            category="verify" if "review" in operation_id else ("render" if "visual" in operation_id else "write"),
            parent_id="quality",
            detail=detail,
        )

    def emit_review_start(self) -> Dict[str, Any]:
        self._review_index += 1
        self._review_id = f"operation_quality_review_{self._review_index}"
        return self._event("started", self._review_id, "校验交付质量", "Validate delivery quality")

    def emit_review_issues(self, count: int = 0, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        issue_count = int(count or 0) + sum(int(kwargs.get(key) or 0) for key in ("critical", "major", "minor"))
        return self._event("completed", self._review_id, "校验交付质量", "Validate delivery quality", detail={"issue_count": issue_count, "passed": False, "outcome": "needs_repair"})

    def emit_review_issue_details(self, details: Any = None) -> None:
        # Findings stay in the evaluation report. They are not a second user-
        # visible progress item and must not update an already completed row.
        return None

    def emit_review_pass(self) -> Dict[str, Any]:
        return self._event("completed", self._review_id, "校验交付质量", "Validate delivery quality", detail={"outcome": "passed"})

    def emit_review_inconclusive(self, *, stage: str = "", error_type: str = "") -> Dict[str, Any]:
        return self._event(
            "completed",
            self._review_id,
            "校验交付质量",
            "Validate delivery quality",
            detail={"inconclusive": True, "outcome": "inconclusive", "stage": stage, "error_type": error_type},
        )

    def emit_repair_start(self) -> Dict[str, Any]:
        self._repair_index += 1
        self._repair_id = f"operation_quality_repair_{self._repair_index}"
        return self._event("started", self._repair_id, "修正质量问题", "Repair quality issues")

    def emit_repair_done(self) -> Dict[str, Any]:
        return self._event("completed", self._repair_id, "修正质量问题", "Repair quality issues")

    def emit_visual_start(self) -> Dict[str, Any]:
        self._visual_index += 1
        self._visual_id = f"operation_quality_visual_{self._visual_index}"
        return self._event("started", self._visual_id, "处理视觉内容", "Process visual content")

    def emit_visual_done(self) -> Dict[str, Any]:
        return self._event("completed", self._visual_id, "处理视觉内容", "Process visual content")
