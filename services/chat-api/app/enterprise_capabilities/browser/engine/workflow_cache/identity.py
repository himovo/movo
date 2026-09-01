from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict
from urllib.parse import urlparse

from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext
from app.enterprise_capabilities.browser.engine.business_site_scope import resolve_business_site_scope
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask

from .contracts import WorkflowIdentity


_URL_RE = re.compile(r"https?://[^\s\]\)\"'<>]+", re.IGNORECASE)
_DRAFT_WORDS = ("草稿", "存稿", "draft")
_PUBLISH_WORDS = ("发布", "发表", "publish", "post")


def build_workflow_identity(
    *,
    user_id: str,
    main_id: str,
    node: CapabilityTask,
    input_context: BrowserInputContext,
) -> WorkflowIdentity | None:
    site_id = site_id_for_node(node, input_context=input_context)
    capability_id = str((node.meta or {}).get("capability_id") or "").strip().lower()
    declared_operation = _declared_operation(node)
    action = _action_id(capability_id, " ".join((
        str(input_context.original_request or ""),
        str(node.goal or ""),
    )))
    object_type = _object_type(node, input_context)
    if not user_id or not site_id:
        return None
    operation_id = declared_operation or (
        f"{object_type}.{action}" if action else _unknown_operation(node, input_context)
    )
    identity_data = {
        "user_id": str(user_id),
        "main_id": str(main_id or "default"),
        "site_id": site_id,
        "operation_id": operation_id,
        "capability_id": capability_id,
    }
    # main_id and capability_id are useful audit metadata, but neither should
    # split the same user + site + normalized business operation into different
    # caches across later requests.
    signature_data = {
        key: identity_data[key]
        for key in ("user_id", "site_id", "operation_id")
    }
    raw = json.dumps(signature_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return WorkflowIdentity(
        **identity_data,
        signature_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


def _site_id(node: CapabilityTask) -> str:
    meta = node.meta if isinstance(node.meta, dict) else {}
    direct = str(meta.get("browser_site_scope") or "").strip()
    if direct:
        return _canonical_site(direct)
    site_context = meta.get("site_context") if isinstance(meta.get("site_context"), dict) else {}
    profile_id = str(site_context.get("site_profile_id") or site_context.get("id") or "").strip()
    if profile_id:
        return f"profile:{profile_id.lower()}"
    for candidate in (
        site_context.get("entry_url"),
        _semantic_config(meta).get("targetUrl"),
        _semantic_config(meta).get("target_url"),
    ):
        if str(candidate or "").strip():
            return _canonical_site(str(candidate))
    match = _URL_RE.search(str(node.goal or ""))
    return _canonical_site(match.group(0)) if match else ""


def _canonical_site(value: str) -> str:
    text = str(value or "").strip().lower()
    parsed = urlparse(text if "://" in text else f"//{text}")
    host = str(parsed.hostname or "").strip().lower().removeprefix("www.")
    return host or " ".join(text.split()).strip("/")


def _semantic_config(meta: Dict[str, Any]) -> Dict[str, Any]:
    direct = meta.get("semantic_config")
    if isinstance(direct, dict):
        return direct
    step = meta.get("workflow_step") if isinstance(meta.get("workflow_step"), dict) else {}
    nested = step.get("semantic_config")
    return nested if isinstance(nested, dict) else {}


def _action_id(capability_id: str, goal: str) -> str:
    text = str(goal or "").lower()
    if any(token in text for token in _DRAFT_WORDS):
        return "save_draft"
    if capability_id in {"browser.publish", "browser.publish_or_submit"}:
        return "publish"
    if capability_id == "browser.delete":
        return "delete"
    if capability_id == "browser.modify":
        return "update"
    if capability_id == "browser.file_transfer":
        return "file_transfer"
    if capability_id in {"browser.read", "browser.navigate_and_extract", "browser.search"}:
        return "read"
    if capability_id == "browser.navigate":
        return "navigate"
    if capability_id == "browser.submit":
        return "submit"
    if any(token in text for token in _PUBLISH_WORDS):
        return "publish"
    return ""


def _declared_operation(node: CapabilityTask) -> str:
    semantic = _semantic_config(node.meta if isinstance(node.meta, dict) else {})
    value = str(
        semantic.get("operationId")
        or semantic.get("operation_id")
        or semantic.get("businessOperation")
        or semantic.get("business_operation")
        or ""
    ).strip().lower()
    return value if re.fullmatch(r"[a-z][a-z0-9_.-]{2,127}", value) else ""


def _unknown_operation(node: CapabilityTask, input_context: BrowserInputContext) -> str:
    request = " ".join(str(input_context.original_request or node.goal or "").casefold().split())
    digest = hashlib.sha256(request.encode("utf-8")).hexdigest()[:24]
    return f"unknown.{digest}"


def site_id_for_node(
    node: CapabilityTask,
    input_context: BrowserInputContext | None = None,
) -> str:
    explicit = _site_id(node)
    if explicit:
        return explicit
    resolution = resolve_business_site_scope(
        node,
        original_request=(input_context.original_request if input_context is not None else ""),
    )
    return resolution.site_id


def _object_type(node: CapabilityTask, input_context: BrowserInputContext) -> str:
    semantic = _semantic_config(node.meta if isinstance(node.meta, dict) else {})
    declared = str(semantic.get("objectType") or semantic.get("object_type") or "").strip().lower()
    if declared and re.fullmatch(r"[a-z][a-z0-9_]{1,63}", declared):
        return declared
    roles = {str(item.semantic_name or "").strip().lower() for item in input_context.candidates}
    if roles.intersection({"title", "body", "article", "article_markdown"}):
        return "article"
    if roles.intersection({"recipient", "recipient_email", "subject"}):
        return "message"
    # The original request survives graph replanning and human-assisted resume;
    # a reconstructed node goal may omit the object noun (for example
    # "article") and must not split one business operation into two caches.
    text = " ".join((
        str(input_context.original_request or ""),
        str(node.goal or ""),
    )).lower()
    if any(token in text for token in ("文章", "图文", "article", "post")):
        return "article"
    if roles.intersection({"media", "attachment", "file", "images"}):
        return "content"
    return "resource"


__all__ = ["build_workflow_identity", "site_id_for_node"]
