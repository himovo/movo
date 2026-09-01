from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator


class OperationCategory(str, Enum):
    ANALYZE = "analyze"
    SEARCH = "search"
    READ = "read"
    WRITE = "write"
    TOOL = "tool"
    BROWSER = "browser"
    RENDER = "render"
    VERIFY = "verify"


class ModelOperation(BaseModel):
    """User-facing description for a real runtime operation.

    The model supplies only presentation metadata. Runtime code owns the
    operation id and lifecycle, so prose can never create or complete work.
    """

    label: str = Field(default="", max_length=180)
    category: OperationCategory = OperationCategory.TOOL

    @field_validator("label", mode="before")
    @classmethod
    def _normalize_label(cls, value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_model_operation(value: Any) -> Dict[str, str] | None:
    try:
        operation = value if isinstance(value, ModelOperation) else ModelOperation.model_validate(value or {})
    except Exception:
        return None
    if len(operation.label) < 4:
        return None
    return {"label": operation.label, "category": operation.category.value, "source": "model"}


def operation_event(
    state: str,
    *,
    operation_id: str,
    label: str = "",
    category: str = "",
    parent_id: str = "",
    source: str = "",
    detail: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a native execution event at the producer boundary.

    These events are not legacy timeline/activity messages. They describe a
    real operation whose lifecycle is controlled by runtime code.
    """

    normalized_state = str(state or "updated").strip().lower()
    if normalized_state not in {"started", "updated", "completed", "failed", "blocked"}:
        raise ValueError(f"unsupported operation state: {state}")
    content: Dict[str, Any] = {"operation_id": str(operation_id)}
    normalized_label = re.sub(r"\s+", " ", str(label or "")).strip()
    if normalized_label:
        content["label"] = normalized_label
    if str(category or "").strip():
        content["category"] = str(category).strip().lower()
    if str(source or "").strip():
        content["source"] = str(source).strip()
    if parent_id:
        content["parent_id"] = str(parent_id)
    if detail:
        content["detail"] = dict(detail)
    return {"type": f"operation.{normalized_state}", "content": content}


def model_operation_event(
    value: Any,
    *,
    state: str,
    operation_id: str,
    parent_id: str = "",
) -> Dict[str, Any] | None:
    descriptor = normalize_model_operation(value)
    if descriptor is None:
        return None
    return operation_event(
        state,
        operation_id=operation_id,
        label=descriptor["label"],
        category=descriptor["category"],
        parent_id=parent_id,
        source="model",
    )


def operation_descriptor_for_node(node: Any) -> Dict[str, str]:
    """Resolve display metadata from planner output without parsing prose."""

    meta = dict(getattr(node, "meta", None) or {})
    modeled = normalize_model_operation(meta.get("model_operation"))
    if modeled is not None:
        return modeled
    task_step = meta.get("task_ir_step") if isinstance(meta.get("task_ir_step"), dict) else {}
    label = str(task_step.get("title") or getattr(node, "goal", "") or getattr(node, "node_id", "")).strip()
    capability = str(meta.get("capability_id") or "").strip().lower()
    family = capability.split(".", 1)[0]
    category = {
        "research": "search",
        "web": "read",
        "kb": "search",
        "generation": "write",
        "browser": "browser",
        "file": "render",
        "analysis": "analyze",
        "control": "analyze",
        "vision": "read",
        "quality": "verify",
        "external": "tool",
    }.get(family, "tool")
    return {"label": re.sub(r"\s+", " ", label)[:180], "category": category, "source": "runtime"}
