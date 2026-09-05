from __future__ import annotations

import re
from urllib.parse import quote_plus
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence

from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext, InputCandidate

from .contracts import CachedParameterBinding, CachedRequestTemplate
from .semantics import candidate_semantic_score


@dataclass(frozen=True)
class ParameterCatalog:
    request_template: CachedRequestTemplate | None
    request_bindings: Dict[str, CachedParameterBinding]
    sensitive_values: tuple[str, ...] = ()

    def binding_for(
        self,
        value: Any,
        context: BrowserInputContext,
        *,
        projection_hint: str = "value",
        semantic_hint: str = "",
    ) -> CachedParameterBinding | None:
        candidate = _unique_candidate_for_value(
            value, context.candidates, semantic_hint=semantic_hint,
        )
        if candidate is not None:
            return CachedParameterBinding(
                source="candidate",
                semantic_name=str(candidate.semantic_name or candidate.value_kind or "input"),
                source_path=str(candidate.source_path or ""),
                projection=_candidate_projection(candidate, value, projection_hint),
            )
        if isinstance(value, str):
            return self.request_bindings.get(value)
        return None


class RuntimeParameterResolver:
    def __init__(
        self,
        *,
        context: BrowserInputContext,
        request_template: CachedRequestTemplate | None,
    ) -> None:
        self._context = context
        self._request_slots = resolve_request_slots(
            request_template,
            context.original_request,
        )

    def resolve(self, binding: CachedParameterBinding) -> Any | None:
        if binding.source == "request":
            if binding.request_slot < 0 or binding.request_slot >= len(self._request_slots):
                return None
            value = self._request_slots[binding.request_slot]
            if value == "":
                return None
            encoded = quote_plus(value) if binding.encoding == "url_query" else value
            return f"{binding.prefix}{encoded}{binding.suffix}"
        candidate = _unique_runtime_candidate(self._context.candidates, binding)
        if candidate is None:
            return None
        if binding.projection == "files":
            if isinstance(candidate.value, list):
                return list(candidate.value)
            return [str(candidate.value)] if str(candidate.value or "").strip() else None
        if binding.projection == "plain_text":
            return str(candidate.plain_text or candidate.value or "") or None
        if binding.projection == "rich_html":
            # A value explicitly supplied in the request may be plain text
            # even when the recorded editor previously emitted HTML. Rich
            # editors accept the plain value; rejecting it would prevent a
            # semantically valid cache binding.
            return str(candidate.rich_html or candidate.plain_text or candidate.value or "") or None
        value = candidate.value
        if isinstance(value, str) and (binding.prefix or binding.suffix):
            encoded = quote_plus(value) if binding.encoding == "url_query" else value
            return f"{binding.prefix}{encoded}{binding.suffix}"
        return value


def build_parameter_catalog(
    *,
    context: BrowserInputContext,
    request_values: Iterable[str],
) -> ParameterCatalog:
    request = str(context.original_request or "")
    values = []
    for value in request_values:
        text = str(value or "")
        if not text or text not in request:
            continue
        if text not in values:
            values.append(text)
    spans: List[tuple[int, int, str]] = []
    for value in sorted(values, key=len, reverse=True):
        start = request.find(value)
        if start < 0:
            continue
        end = start + len(value)
        if any(start < other_end and end > other_start for other_start, other_end, _ in spans):
            continue
        spans.append((start, end, value))
    spans.sort()
    if not spans:
        return ParameterCatalog(
            request_template=None,
            request_bindings={},
            sensitive_values=_sensitive_values(context, values),
        )
    parts: List[str] = []
    bindings: Dict[str, CachedParameterBinding] = {}
    cursor = 0
    for slot, (start, end, value) in enumerate(spans):
        parts.append(request[cursor:start])
        bindings[value] = CachedParameterBinding(source="request", request_slot=slot)
        cursor = end
    parts.append(request[cursor:])
    return ParameterCatalog(
        request_template=CachedRequestTemplate(parts=parts, slot_count=len(spans)),
        request_bindings=bindings,
        sensitive_values=_sensitive_values(context, values),
    )


def resolve_request_slots(
    template: CachedRequestTemplate | None,
    request: str,
) -> List[str]:
    if template is None or template.slot_count <= 0:
        return []
    parts = list(template.parts)
    if len(parts) != template.slot_count + 1:
        return []
    pattern = "^"
    for index, part in enumerate(parts):
        pattern += _static_pattern(part)
        if index < template.slot_count:
            pattern += "(.+?)"
    pattern += "$"
    match = re.match(pattern, str(request or ""), flags=re.S)
    if match is None:
        return []
    return [str(item).strip() for item in match.groups()]


def _static_pattern(text: str) -> str:
    chunks = re.split(r"(\s+)", text)
    return "".join(r"\s+" if chunk.isspace() else re.escape(chunk) for chunk in chunks if chunk)


def _unique_candidate_for_value(
    value: Any,
    candidates: Sequence[InputCandidate],
    *,
    semantic_hint: str = "",
) -> InputCandidate | None:
    if isinstance(value, list):
        normalized = _files(value)
        matches = [item for item in candidates if item.value_kind == "file" and _files(item.value) == normalized]
    else:
        actual = str(value or "")
        matches = [
            item for item in candidates
            if item.value_kind != "file" and actual in {
                str(item.value or ""), str(item.plain_text or ""), str(item.rich_html or ""),
            }
        ]
    matches = _collapse_equivalent_candidates(matches)
    if len(matches) == 1:
        return matches[0]
    if len(matches) <= 1 or not semantic_hint:
        return None
    ranked = sorted(
        ((candidate_semantic_score(item, semantic_hint), item) for item in matches),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if ranked[0][0] <= 0 or (len(ranked) > 1 and ranked[0][0] == ranked[1][0]):
        return None
    return ranked[0][1]


def _collapse_equivalent_candidates(
    candidates: Sequence[InputCandidate],
) -> List[InputCandidate]:
    """Treat repeated recorder emissions for one semantic value as one input.

    Reactive applications can emit the same value again while hydrating a new
    route. Distinct semantic fields remain distinct even when their values are
    equal, so genuine confirmation or multi-field forms stay unambiguous.
    """
    output: List[InputCandidate] = []
    recorded: set[tuple[str, str, str, tuple[str, ...]]] = set()
    for candidate in candidates:
        if str(candidate.source_kind or "").strip().casefold() != "human_recording":
            output.append(candidate)
            continue
        key = (
            str(candidate.semantic_name or "").strip().casefold(),
            str(candidate.value_kind or "").strip().casefold(),
            str(candidate.plain_text or ""),
            _files(candidate.value),
        )
        if key in recorded:
            continue
        recorded.add(key)
        output.append(candidate)
    return output


def _unique_runtime_candidate(
    candidates: Sequence[InputCandidate],
    binding: CachedParameterBinding,
) -> InputCandidate | None:
    exact = [item for item in candidates if binding.source_path and item.source_path == binding.source_path]
    matches = exact or [
        item for item in candidates
        if str(item.semantic_name or "").strip().casefold() == binding.semantic_name.strip().casefold()
    ]
    return matches[0] if len(matches) == 1 else None


def _candidate_projection(candidate: InputCandidate, value: Any, hint: str) -> str:
    if isinstance(value, list) or candidate.value_kind == "file":
        return "files"
    actual = str(value or "")
    if hint == "rich_html" or (candidate.rich_html and actual == str(candidate.rich_html)):
        return "rich_html"
    if hint == "plain_text" or (candidate.plain_text and actual == str(candidate.plain_text)):
        return "plain_text"
    return "value"


def _files(value: Any) -> tuple[str, ...]:
    values = value if isinstance(value, list) else [value]
    return tuple(str(item or "").strip() for item in values if str(item or "").strip())


def _sensitive_values(context: BrowserInputContext, request_values: Iterable[str]) -> tuple[str, ...]:
    values = {str(item) for item in request_values if str(item)}
    for candidate in context.candidates:
        raw_values = candidate.value if isinstance(candidate.value, list) else [candidate.value]
        values.update(str(item) for item in raw_values if str(item or ""))
        if candidate.plain_text:
            values.add(str(candidate.plain_text))
        if candidate.rich_html:
            values.add(str(candidate.rich_html))
    return tuple(sorted(values, key=len, reverse=True))


__all__ = [
    "ParameterCatalog",
    "RuntimeParameterResolver",
    "build_parameter_catalog",
    "resolve_request_slots",
]
