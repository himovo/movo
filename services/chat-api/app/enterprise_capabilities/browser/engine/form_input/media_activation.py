from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .input_context import BrowserInputContext, InputCandidate
from .media_compatibility import file_input_accepts_media, requested_media_kinds
from .media_editor import (
    has_structured_empty_body_editor,
    media_editor_has_content,
    resolve_media_editor_ref,
)
from .media_handoff import pending_media_candidates
from .media_target_affinity import (
    MediaTargetHint,
    media_target_affinity_score,
)
from .value_equivalence import field_values_equivalent


_ACTION_ROLES = {"button", "link", "menuitem", "tab"}
_DOCUMENT_TERMS = {"document", "docx", "markdown", "文档", "导入文档"}
_MEDIA_LABEL_TERMS = {
    "image", "picture", "photo", "video", "media", "upload", "attach",
    "图片", "图像", "配图", "插图", "视频", "媒体", "上传", "附件",
}
_EXPLICIT_UPLOAD_TERMS = {"upload", "attach", "上传", "附件"}


@dataclass(frozen=True)
class MediaActivationResolution:
    decision: Optional[Decision] = None
    attempt_key: str = ""
    candidate_refs: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()


def resolve_media_activation(
    *,
    observation: Observation,
    context: BrowserInputContext,
    completed_candidate_ids: Iterable[str],
    attempted_keys: Iterable[str],
    preferred_target_hint: Optional[MediaTargetHint] = None,
) -> MediaActivationResolution:
    pending = pending_media_candidates(context, completed_candidate_ids)
    if not pending:
        return MediaActivationResolution()
    if not _content_ready_for_media(
        observation,
        context=context,
        completed_candidate_ids=completed_candidate_ids,
    ):
        return MediaActivationResolution()

    requested_kinds = requested_media_kinds(pending[:1])
    direct_inputs = sorted(
        _available_file_inputs(
            observation,
            requested_kinds=requested_kinds,
        ),
        key=lambda item: (
            -media_target_affinity_score(item, preferred_target_hint),
            str(item.get("ref") or ""),
        ),
    )
    if direct_inputs:
        candidate = pending[0]
        preferred_direct_score = media_target_affinity_score(
            direct_inputs[0],
            preferred_target_hint,
        )
        if len(direct_inputs) > 1 and preferred_direct_score < 1000:
            return MediaActivationResolution(
                candidate_refs=tuple(
                    str(item.get("ref") or "") for item in direct_inputs[:8]
                ),
            )
        target = direct_inputs[0]
        ref = str(target.get("ref") or "").strip()
        attempt_key = _attempt_key(
            observation,
            ref,
            candidate_id=candidate.candidate_id,
        )
        if attempt_key in {str(item) for item in attempted_keys if str(item)}:
            return MediaActivationResolution()
        return _upload_resolution(
            target=target,
            pending=pending,
            score=1000,
            attempt_key=attempt_key,
            editor_ref=resolve_media_editor_ref(
                observation,
                target,
                anchor=candidate.metadata.get("media_anchor"),
            ),
        )

    active_candidate_id = pending[0].candidate_id
    editor_scopes = _editor_scope_ids(observation)
    attempted = {str(item) for item in attempted_keys if str(item)}
    ranked: list[tuple[int, Dict[str, Any], str]] = []
    for element in list(observation.elements or []):
        if not isinstance(element, dict) or not _usable_action(element):
            continue
        score = _activation_score(
            element,
            requested_kinds=requested_kinds,
            editor_scopes=editor_scopes,
        )
        if score < 100:
            continue
        score += media_target_affinity_score(
            element,
            preferred_target_hint,
        )
        ref = str(element.get("ref") or "").strip()
        attempt_key = _attempt_key(
            observation,
            ref,
            candidate_id=active_candidate_id,
        )
        if attempt_key in attempted:
            continue
        ranked.append((score, element, attempt_key))

    ranked.sort(key=lambda item: (-item[0], str(item[1].get("ref") or "")))
    if not ranked:
        return MediaActivationResolution()
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 20:
        return MediaActivationResolution(
            candidate_refs=tuple(
                str(item[1].get("ref") or "") for item in ranked[:8]
            ),
        )

    score, target, attempt_key = ranked[0]
    return _upload_resolution(
        target=target,
        pending=pending,
        score=score,
        attempt_key=attempt_key,
        editor_ref=resolve_media_editor_ref(
            observation,
            target,
            anchor=pending[0].metadata.get("media_anchor"),
        ),
    )


def promote_media_control_decision(
    *,
    decision: Decision,
    observation: Observation,
    context: BrowserInputContext,
    completed_candidate_ids: Iterable[str],
) -> MediaActivationResolution:
    """Prevent a pending media upload from degrading into a plain click."""

    if decision.tool not in {"browser_click", "browser_click_at"}:
        return MediaActivationResolution()
    all_media = [
        candidate for candidate in context.candidates
        if candidate.value_kind == "file" and list(candidate.value or [])
    ]
    if not all_media:
        return MediaActivationResolution()
    pending = pending_media_candidates(context, completed_candidate_ids)
    requested_kinds = requested_media_kinds((pending or all_media)[:1])
    editor_scopes = _editor_scope_ids(observation)
    target = _decision_target(decision, observation)
    if target is None or not _usable_action(target):
        return MediaActivationResolution()
    score = _activation_score(
        target,
        requested_kinds=requested_kinds,
        editor_scopes=editor_scopes,
    )
    if score < 100:
        return MediaActivationResolution()
    if not pending:
        return MediaActivationResolution(
            decision=Decision(
                tool="browser_observe",
                args={},
                rationale=(
                    "[form_media_activation] all upstream media are already uploaded; "
                    "suppress duplicate activation and verify the current editor"
                ),
            ),
            attempt_key=_attempt_key(
                observation,
                str(target.get("ref") or "").strip(),
                candidate_id="completed",
            ),
        )
    if not _content_ready_for_media(
        observation,
        context=context,
        completed_candidate_ids=completed_candidate_ids,
    ):
        return MediaActivationResolution(
            decision=Decision(
                tool="browser_observe",
                args={},
                rationale=(
                    "[form_media_activation] generated title/body must be written "
                    "before anchored media placement"
                ),
            ),
            attempt_key=_attempt_key(
                observation,
                str(target.get("ref") or "").strip(),
                candidate_id=pending[0].candidate_id,
            ),
        )
    return _upload_resolution(
        target=target,
        pending=pending,
        score=score,
        attempt_key=_attempt_key(
            observation,
            str(target.get("ref") or "").strip(),
            candidate_id=pending[0].candidate_id,
        ),
        editor_ref=resolve_media_editor_ref(
            observation,
            target,
            anchor=pending[0].metadata.get("media_anchor"),
        ),
    )


def _upload_resolution(
    *,
    target: Dict[str, Any],
    pending: Iterable[InputCandidate],
    score: int,
    attempt_key: str,
    editor_ref: str,
) -> MediaActivationResolution:
    pending_list = list(pending)
    if not pending_list:
        return MediaActivationResolution()
    candidate = pending_list[0]
    ref = str(target.get("ref") or "").strip()
    purpose = str(target.get("semanticPurpose") or "").strip().lower()
    anchor = candidate.metadata.get("media_anchor")
    # New publish payloads model each anchored asset as one transaction so the
    # editor caret can be positioned independently. Keep legacy batch
    # candidates intact because direct file inputs may accept multiple files.
    raw_sources = list(candidate.value or [])
    selected_sources = raw_sources[:1] if isinstance(anchor, dict) else raw_sources
    sources = [
        str(source)
        for source in selected_sources
        if str(source).strip()
    ]
    args: Dict[str, Any] = {"ref": ref, "sources": sources}
    has_anchor = isinstance(anchor, dict) and any(
        anchor.get(key) not in {None, ""}
        for key in ("after_text", "before_text", "plain_offset")
    )
    if has_anchor and not editor_ref:
        return MediaActivationResolution(
            decision=Decision(
                tool="browser_observe",
                args={},
                rationale=(
                    "[form_media_activation] anchored media has no matching live "
                    "editor; refresh the editor before uploading"
                ),
            ),
            attempt_key=attempt_key,
            candidate_refs=(ref,),
        )
    if editor_ref:
        args["editor_ref"] = editor_ref
    if has_anchor:
        args["anchor"] = dict(anchor)
    return MediaActivationResolution(
        decision=Decision(
            tool="browser_upload_file",
            args=args,
            rationale=(
                "[form_media_activation] upload upstream files through the live editor media control "
                f"(semanticPurpose={purpose or 'media'}, score={score})"
            ),
        ),
        attempt_key=attempt_key,
        candidate_refs=(ref,),
        candidate_ids=(candidate.candidate_id,),
    )


def _decision_target(
    decision: Decision,
    observation: Observation,
) -> Optional[Dict[str, Any]]:
    args = dict(decision.args or {})
    if decision.tool == "browser_click":
        ref = str(args.get("ref") or "").strip()
        return next((
            element
            for element in list(observation.elements or [])
            if isinstance(element, dict)
            and str(element.get("ref") or "").strip() == ref
        ), None)
    x = _number(args.get("x"))
    y = _number(args.get("y"))
    if x is None or y is None:
        return None
    candidates = [
        element
        for element in list(observation.elements or [])
        if isinstance(element, dict) and _contains_point(element, x, y)
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            max(1.0, _number(item.get("width")) or 0.0)
            * max(1.0, _number(item.get("height")) or 0.0),
            str(item.get("ref") or ""),
        ),
    )


def _contains_point(element: Dict[str, Any], x: float, y: float) -> bool:
    left = _number(element.get("x"))
    top = _number(element.get("y"))
    width = _number(element.get("width"))
    height = _number(element.get("height"))
    return bool(
        left is not None
        and top is not None
        and width is not None
        and height is not None
        and width > 0
        and height > 0
        and left <= x <= left + width
        and top <= y <= top + height
    )


def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _activation_score(
    element: Dict[str, Any],
    *,
    requested_kinds: set[str],
    editor_scopes: set[str],
) -> int:
    purpose = str(element.get("semanticPurpose") or "").strip().lower()
    visible_label = " ".join(
        str(element.get(key) or "") for key in ("name", "text")
    ).casefold().strip()
    text = " ".join(
        str(element.get(key) or "")
        for key in ("name", "text", "description", "semanticPurpose", "accept")
    ).casefold()
    scope_id = str(element.get("scopeId") or element.get("scope_id") or "")
    explicit_upload = (
        purpose in {"upload", "attachment", "media"}
        or any(term in text for term in _EXPLICIT_UPLOAD_TERMS)
    )
    implicit_media = purpose in {"image", "video"} and not explicit_upload
    if implicit_media:
        # Geometry-only image semantics are useful for unlabeled editor toolbar
        # icons, but the same shape also appears in ordinary navigation cards.
        # Require a live editor scope and reject controls with unrelated visible
        # labels before treating the control as a file chooser.
        if not editor_scopes or scope_id not in editor_scopes:
            return -1000
        if visible_label and not any(
            term in visible_label for term in _MEDIA_LABEL_TERMS
        ):
            return -1000

    score = 0
    if purpose in requested_kinds:
        score += 180
    elif purpose in {"image", "video"}:
        score += 90
    elif purpose in {"upload", "attachment", "media"}:
        score += 75

    if "image" in requested_kinds and any(term in text for term in (
        "image", "picture", "photo", "图片", "图像", "配图", "插图",
    )):
        score += 75
    if "video" in requested_kinds and any(term in text for term in ("video", "视频")):
        score += 75
    if any(term in text for term in ("upload", "attach", "上传", "附件")):
        score += 35

    if editor_scopes and scope_id in editor_scopes:
        score += 45
    elif editor_scopes and scope_id:
        score -= 30
    if any(term in text for term in _DOCUMENT_TERMS) and "image" in requested_kinds:
        score -= 100
    if purpose in {"send", "submit", "publish", "save", "delete"}:
        score -= 200
    return score


def _editor_scope_ids(observation: Observation) -> set[str]:
    return {
        str(element.get("scopeId") or element.get("scope_id") or "")
        for element in list(observation.elements or [])
        if isinstance(element, dict)
        and element.get("editable")
        and not element.get("searchContext")
        and not element.get("search_context")
        and str(element.get("scopeId") or element.get("scope_id") or "")
    }


def _content_ready_for_media(
    observation: Observation,
    *,
    context: BrowserInputContext,
    completed_candidate_ids: Iterable[str],
) -> bool:
    editor_ref = resolve_media_editor_ref(observation, {})
    body_candidates = [
        candidate for candidate in context.candidates
        if candidate.value_kind != "file"
        and candidate.semantic_name.casefold() in {
            "body", "content", "article", "markdown", "正文", "内容", "文章",
        }
    ]
    if not body_candidates:
        if (
            editor_ref
            and not media_editor_has_content(observation, editor_ref)
            and has_structured_empty_body_editor(observation, editor_ref)
        ):
            return False
        return True
    if not editor_ref:
        return False
    completed = {str(item) for item in completed_candidate_ids if str(item)}
    editor = next((
        element for element in list(observation.elements or [])
        if isinstance(element, dict)
        and str(element.get("ref") or "").strip() == editor_ref
    ), None)
    if editor is None:
        return False
    for candidate in body_candidates:
        expected = candidate.plain_text or candidate.value
        if field_values_equivalent(
            editor.get("value") or editor.get("text") or "",
            expected,
            target=editor,
        ):
            return True
        if (
            candidate.candidate_id in completed
            and media_editor_has_content(observation, editor_ref)
        ):
            return True
    return False


def _usable_action(element: Dict[str, Any]) -> bool:
    return (
        str(element.get("role") or "").strip().lower() in _ACTION_ROLES
        and bool(str(element.get("ref") or "").strip())
        and not element.get("disabled")
        and element.get("visible") is not False
        and element.get("inViewport") is not False
        and element.get("hitTestable") is not False
    )


def _available_file_inputs(
    observation: Observation,
    *,
    requested_kinds: set[str],
) -> list[Dict[str, Any]]:
    return [
        element
        for element in list(observation.elements or [])
        if isinstance(element, dict)
        and str(element.get("type") or "").strip().lower() == "file"
        and not element.get("disabled")
        and str(element.get("ref") or "").strip()
        and file_input_accepts_media(element, requested_kinds)
    ]


def _attempt_key(
    observation: Observation,
    ref: str,
    *,
    candidate_id: str = "",
) -> str:
    revision = str(getattr(observation, "revision", "") or "").strip()
    if not revision:
        revision = (
            f"{str(observation.url or '')}|{str(observation.title or '')}|"
            f"{len(list(observation.elements or []))}"
        )
    return f"{revision}:{ref}:{candidate_id}"


__all__ = [
    "MediaActivationResolution",
    "promote_media_control_decision",
    "resolve_media_activation",
]
