"""Collect durable business-object identity changes from browser URLs."""
from __future__ import annotations

import re
from typing import Dict, Iterable
from urllib.parse import parse_qsl, urlsplit

from .contracts import EffectContract, EffectEvidence


_IDENTIFIER_KEY = re.compile(r"(?:^id$|(?:^|_)(?:id|uuid|guid)$)", re.I)
_CAMEL_IDENTIFIER_KEY = re.compile(r"(?:Id|ID|Uuid|UUID|Guid|GUID)$")
_UUID_VALUE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.I,
)
_OPAQUE_VALUE = re.compile(r"^[A-Za-z0-9_-]{12,}$")
_VOLATILE_KEYS = {
    "sid",
    "session",
    "sessionid",
    "session_id",
    "source",
    "from",
    "ref",
    "nonce",
    "signature",
    "sign",
    "timestamp",
    "ts",
}


def collect_resource_identity_evidence(
    *,
    contract: EffectContract,
    before_url: str,
    after_url: str,
) -> list[EffectEvidence]:
    if not contract.is_commit or contract.side_effect == "none":
        return []
    if not _same_origin(before_url, after_url):
        return []
    before = _resource_identifiers(before_url)
    after = _resource_identifiers(after_url)
    assigned = sorted(key for key, value in after.items() if value and key not in before)
    if not assigned:
        return []
    return [
        EffectEvidence(
            evidence_id="resource_identity:" + ",".join(assigned),
            kind="business_object_id_assigned",
            detail="提交后获得稳定业务对象标识：" + ", ".join(assigned),
            polarity="positive",
            weight=0.9,
        ),
    ]


def _resource_identifiers(raw_url: str) -> Dict[str, str]:
    try:
        parsed = urlsplit(str(raw_url or "").strip())
    except Exception:
        return {}
    identifiers = _query_identifiers(parse_qsl(parsed.query, keep_blank_values=False))
    if parsed.fragment.startswith("/") and "?" in parsed.fragment:
        _, _, fragment_query = parsed.fragment.partition("?")
        identifiers.update(
            {
                f"fragment:{key}": value
                for key, value in _query_identifiers(
                    parse_qsl(fragment_query, keep_blank_values=False),
                ).items()
            },
        )
    for index, segment in enumerate(part for part in parsed.path.split("/") if part):
        if _looks_like_identifier_value(segment):
            identifiers[f"path:{index}"] = segment
    return identifiers


def _same_origin(left: str, right: str) -> bool:
    try:
        left_url = urlsplit(str(left or "").strip())
        right_url = urlsplit(str(right or "").strip())
    except Exception:
        return False
    return bool(
        left_url.hostname
        and right_url.hostname
        and left_url.scheme.casefold() == right_url.scheme.casefold()
        and left_url.netloc.casefold() == right_url.netloc.casefold()
    )


def _query_identifiers(pairs: Iterable[tuple[str, str]]) -> Dict[str, str]:
    identifiers: Dict[str, str] = {}
    for raw_key, raw_value in pairs:
        key = str(raw_key or "").strip()
        normalized = key.casefold()
        value = str(raw_value or "").strip()
        if (
            not key
            or not value
            or normalized in _VOLATILE_KEYS
            or normalized.startswith("utm_")
            or "token" in normalized
        ):
            continue
        if _looks_like_identifier_key(key) and _looks_like_identifier_value(value):
            identifiers[f"query:{normalized}"] = value
    return identifiers


def _looks_like_identifier_key(value: str) -> bool:
    raw = str(value or "").strip()
    return bool(
        _IDENTIFIER_KEY.search(raw.casefold())
        or _CAMEL_IDENTIFIER_KEY.search(raw)
    )


def _looks_like_identifier_value(value: str) -> bool:
    normalized = str(value or "").strip()
    return bool(
        (normalized.isdigit() and len(normalized) >= 4)
        or _UUID_VALUE.fullmatch(normalized)
        or _OPAQUE_VALUE.fullmatch(normalized)
    )


__all__ = ["collect_resource_identity_evidence"]
