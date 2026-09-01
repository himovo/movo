from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List

from app.enterprise_capabilities.browser.engine.rules import matchers
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation

from .contracts import FieldDescriptor
from .identity import stable_field_key, visible_text
from .scopes import element_scope_id
from .structural_roles import annotate_structural_field_roles
from .field_value import current_field_value


_REQUIRED_RE = re.compile(r"(?:\*|必填|required)", re.I)
_SENSITIVE_RE = re.compile(r"(?:密码|口令|验证码|password|passcode|otp|secret|token)", re.I)


def discover_fields(observation: Observation) -> List[FieldDescriptor]:
    fields: List[FieldDescriptor] = []
    occurrences: Dict[str, int] = {}
    for element in list(observation.elements or []):
        if not isinstance(element, dict):
            continue
        field_type = str(element.get("type") or "").strip().lower()
        is_file = field_type == "file"
        if not is_file and not matchers.is_field(element) and not element.get("editable"):
            continue
        if element.get("disabled"):
            continue
        name = visible_text(element.get("name"))
        placeholder = visible_text(element.get("placeholder"))
        description = visible_text(element.get("description"))
        role = str(element.get("role") or "").strip().lower()
        tag = str(element.get("tag") or "").strip().lower()
        base = "\0".join((role, field_type, tag))
        occurrence = occurrences.get(base, 0)
        occurrences[base] = occurrence + 1
        field_key = stable_field_key(element, occurrence)
        corpus = " ".join((name, placeholder, description))
        fields.append(FieldDescriptor(
            field_key=field_key,
            ref=str(element.get("ref") or ""),
            role=role,
            name=name,
            placeholder=placeholder,
            description=description,
            scope_id=element_scope_id(element),
            scope_name=visible_text(element.get("scopeName") or element.get("scope_name")),
            scope_role=str(element.get("scopeRole") or element.get("scope_role") or "").strip().lower(),
            control_kind=_control_kind(element, tag=tag, field_type=field_type, role=role),
            required=bool(element.get("required")) or bool(_REQUIRED_RE.search(corpus)),
            sensitive=field_type == "password" or bool(_SENSITIVE_RE.search(corpus)),
            current_value=current_field_value(element, placeholder=placeholder),
            options=[str(item) for item in list(element.get("options") or []) if str(item).strip()][:100],
            raw=dict(element),
        ))
    return annotate_structural_field_roles(fields)


def is_business_form(fields: List[FieldDescriptor]) -> bool:
    usable = [field for field in fields if not field.sensitive]
    if any(field.control_kind in {"multiline", "rich_text", "file"} for field in usable):
        return True
    if any(field.required for field in usable):
        return True
    non_search = [
        field for field in usable
        if field.role != "searchbox"
        and not field.raw.get("searchContext")
        and not field.raw.get("search_context")
        and "搜索" not in field.label
        and "search" not in field.label.casefold()
    ]
    return len(non_search) >= 2


def page_signature(observation: Observation, fields: List[FieldDescriptor]) -> str:
    semantic = "\n".join(
        f"{field.field_key}:{field.control_kind}:{field.label}" for field in fields
    )
    return hashlib.sha1(f"{observation.url}\n{semantic}".encode("utf-8")).hexdigest()[:20]


def _control_kind(element: Dict[str, Any], *, tag: str, field_type: str, role: str) -> str:
    if field_type == "file":
        return "file"
    if tag == "select" or role == "listbox":
        return "select"
    if role == "combobox" and not element.get("editable") and element.get("options"):
        return "select"
    if role in {"checkbox", "radio", "switch"}:
        return "toggle"
    if element.get("contentEditable") or element.get("content_editable"):
        return "rich_text"
    if tag == "textarea" or element.get("multiline"):
        return "multiline"
    if role in {"textbox", "searchbox", "combobox", "spinbutton"} or element.get("editable"):
        return "text"
    return "unknown"
