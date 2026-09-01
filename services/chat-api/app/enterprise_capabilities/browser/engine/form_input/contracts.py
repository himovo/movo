from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field

from .field_semantics import semantic_field_role


ControlKind = Literal[
    "text", "multiline", "rich_text", "select", "toggle", "file", "unknown",
]
SourceKind = Literal[
    "skill", "user_input", "upstream", "transform", "selection",
    "attachment", "unknown",
]
BindingAction = Literal["fill", "select", "upload", "skip"]


class FieldDescriptor(BaseModel):
    field_key: str
    ref: str
    role: str = ""
    name: str = ""
    placeholder: str = ""
    description: str = ""
    scope_id: str = ""
    scope_name: str = ""
    scope_role: str = ""
    control_kind: ControlKind = "unknown"
    required: bool = False
    sensitive: bool = False
    current_value: str = ""
    options: List[str] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict, exclude=True)

    @property
    def label(self) -> str:
        explicit = self.name or self.description
        if explicit:
            return explicit
        return {
            "multiline": "content",
            "rich_text": "content",
            "select": "selection",
            "toggle": "option",
            "file": "attachment",
            "text": "input",
        }.get(self.control_kind, "form field")

    @property
    def semantic_label(self) -> str:
        return self.semantic_role or self.label

    @property
    def semantic_role(self) -> str:
        inferred = str(
            self.raw.get("inferredFieldRole")
            or self.raw.get("inferred_field_role")
            or ""
        ).strip().lower()
        if inferred in {"title", "body", "recipient", "attachment"}:
            return inferred
        return semantic_field_role(
            name=self.name,
            description=self.description,
            placeholder=self.placeholder,
        )

    def display_label(self, lang: str = "zh") -> str:
        explicit = self.name or self.description
        if explicit:
            return explicit
        role = self.semantic_role
        if role:
            if str(lang or "").startswith("zh"):
                return {
                    "title": "标题",
                    "body": "正文内容",
                    "recipient": "收件人",
                    "attachment": "附件",
                }[role]
            return role
        if str(lang or "").startswith("zh"):
            return {
                "multiline": "正文内容",
                "rich_text": "正文内容",
                "select": "选项",
                "toggle": "开关选项",
                "file": "附件",
                "text": "输入项",
            }.get(self.control_kind, "表单项")
        return self.label


class FieldBinding(BaseModel):
    field_key: str
    action: BindingAction
    source_kind: SourceKind
    value: Any = None
    candidate_id: str = ""
    source_path: str = ""
    plain_text: str = ""
    rich_html: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""


class FormInputPlan(BaseModel):
    page_signature: str
    bindings: List[FieldBinding] = Field(default_factory=list)
    unresolved_field_keys: List[str] = Field(default_factory=list)
