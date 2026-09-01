"""Project verified browser mutations into safe downstream result details."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectReceipt


_SENSITIVE_QUERY_PARTS = {
    "access_token",
    "auth",
    "authorization",
    "code",
    "credential",
    "key",
    "nonce",
    "password",
    "secret",
    "session",
    "sessionid",
    "sid",
    "signature",
    "sign",
    "ticket",
    "token",
}
_MAX_FIELDS = 12
_MAX_FIELD_VALUE_CHARS = 2400
_MAX_LABEL_CHARS = 200
_MAX_TITLE_CHARS = 300


def project_verified_operation_result(
    *,
    receipt: EffectReceipt,
    context: Any,
    form_state: Mapping[str, Any] | None,
    observation: Any,
) -> Dict[str, Any]:
    """Return verified, non-secret business details for ``browser_result.data``.

    The projection is deliberately downstream-only: it does not participate
    in action selection, effect verification, replay blocking, or completion.
    """
    if receipt.status != "confirmed_success":
        return {}

    context_data = _context_result_evidence(context, observation)
    submitted_fields = _submitted_fields(
        form_state,
        receipt.fingerprint,
    )
    details: Dict[str, Any] = {}
    if context_data:
        details.update(context_data)
    if submitted_fields:
        details["submitted_fields"] = submitted_fields

    target_url = _sanitize_url(
        details.get("target_url")
        or receipt.business_target_id
        or getattr(observation, "url", "")
    )
    if target_url:
        details["target_url"] = target_url
    target_title = _compact(
        details.get("target_title") or getattr(observation, "title", ""),
        _MAX_TITLE_CHARS,
    )
    if target_title:
        details["target_title"] = target_title

    if not details:
        return {}
    return {"operation_details": details}


def _context_result_evidence(context: Any, observation: Any) -> Dict[str, Any]:
    projector = getattr(context, "result_evidence", None)
    if not callable(projector):
        return {}
    try:
        value = projector(observation)
    except Exception:
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _submitted_fields(
    form_state: Mapping[str, Any] | None,
    fingerprint: Mapping[str, Any] | None,
) -> list[Dict[str, str]]:
    allowed_hashes = {
        str(value or "").strip()
        for value in list(dict(fingerprint or {}).get("confirmed_fill_hashes") or [])
        if str(value or "").strip()
    }
    if not allowed_hashes:
        return []

    projected: list[Dict[str, str]] = []
    for item in _iter_fields(form_state):
        if (
            str(item.get("status") or "") != "confirmed"
            or bool(item.get("secret"))
            or str(item.get("value_hash") or "").strip() not in allowed_hashes
        ):
            continue
        value = _compact(item.get("expected_value"), _MAX_FIELD_VALUE_CHARS)
        if not value:
            continue
        target = item.get("target") if isinstance(item.get("target"), Mapping) else {}
        projected_item = {
            "label": _safe_label(item, target),
            "value": value,
        }
        purpose = _field_purpose(target)
        if purpose:
            projected_item["purpose"] = purpose
        projected.append(projected_item)
        if len(projected) >= _MAX_FIELDS:
            break
    return projected


def _iter_fields(form_state: Mapping[str, Any] | None) -> Iterable[Mapping[str, Any]]:
    if not isinstance(form_state, Mapping):
        return ()
    return (
        item
        for item in list(form_state.get("fields") or [])
        if isinstance(item, Mapping)
    )


def _safe_label(item: Mapping[str, Any], target: Mapping[str, Any]) -> str:
    candidates = (
        item.get("label"),
        target.get("name"),
        target.get("placeholder"),
        target.get("description"),
    )
    for candidate in candidates:
        label = _compact(candidate, _MAX_LABEL_CHARS)
        if label and not re.fullmatch(r"e\d+", label, re.I):
            return label
    purpose = _field_purpose(target)
    return purpose or "submitted_value"


def _field_purpose(target: Mapping[str, Any]) -> str:
    semantic = _compact(target.get("semanticPurpose"), 80).lower()
    if semantic:
        return semantic
    if target.get("searchContext") or str(target.get("role") or "").lower() == "searchbox":
        return "search"
    role = str(target.get("role") or "").strip().lower()
    field_type = str(target.get("type") or "").strip().lower()
    if role == "textbox" or field_type in {"text", "email", "tel", "url"}:
        return "text"
    return ""


def _sanitize_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_sensitive_query_key(key)
    ]
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query, doseq=True),
        "",
    ))


def _is_sensitive_query_key(key: str) -> bool:
    normalized = str(key or "").strip().lower()
    return (
        normalized in _SENSITIVE_QUERY_PARTS
        or normalized.startswith("utm_")
        or any(part in normalized for part in ("token", "secret", "password", "signature"))
    )


def _compact(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


__all__ = ["project_verified_operation_result"]
