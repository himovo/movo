"""Build a user-visible handoff when automatic media upload is exhausted."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
from urllib.parse import urlparse

from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext
from app.enterprise_capabilities.browser.engine.form_human_assistance import (
    FORM_MEDIA_CATEGORY,
    build_assistance_contract,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision
from app.utils.object_storage import ObjectStorageClient


MEDIA_UPLOAD_CATEGORY = "media_upload"


def is_media_upload_receiver_error(error: Any) -> bool:
    text = str(error or "").strip().lower()
    return "file upload receiver" in text or "node is not a file input element" in text


def is_media_delivery_handoff_error(*, tool: str, error: Any) -> bool:
    """Return whether a failed media mutation is safer to finish by hand.

    Clipboard paste already performs its own focus, delivery and DOM
    verification cycle in the local agent.  Replaying it after that cycle
    fails can duplicate an image which was accepted but rendered too late.
    File-input uploads remain narrower because ordinary transport failures may
    still be retried safely by the existing driver.
    """
    tool_name = str(tool or "").strip()
    text = str(error or "").strip().lower()
    if not text:
        return False
    if tool_name == "browser_paste_image":
        return True
    if tool_name != "browser_upload_file":
        return False
    return is_media_upload_receiver_error(text) or any(marker in text for marker in (
        "accepted the upload, but no new media appeared",
        "upload was accepted but",
        "media insertion could not be verified",
        "media appeared in the target editor",
    ))


def completed_media_candidate_ids(driver_state: Mapping[str, Any] | None) -> set[str]:
    """Read completed ids through decorator checkpoints without knowing driver type."""
    state = dict(driver_state or {})
    completed = {
        str(item).strip()
        for item in list(state.get("completed_candidate_ids") or [])
        if str(item).strip()
    }
    fallback = state.get("fallback_state")
    if isinstance(fallback, Mapping):
        completed.update(completed_media_candidate_ids(fallback))
    return completed


def build_media_upload_handoff(
    *,
    context: BrowserInputContext,
    completed_candidate_ids: Iterable[str],
    user_id: str,
) -> Optional[Dict[str, Any]]:
    completed = {str(item).strip() for item in completed_candidate_ids}
    content = build_form_content_handoff(
        context=context,
        completed_candidate_ids=completed,
        user_id=user_id,
        include_completed_media=False,
    )
    images = list(content.get("images") or [])
    if not images:
        return None
    pending_candidate_ids = list(dict.fromkeys(
        str(item["candidate_id"]) for item in images
    ))
    return {
        **content,
        "contract": build_assistance_contract(
            kind=FORM_MEDIA_CATEGORY,
            action="upload_media",
            payload={"pending_candidate_ids": pending_candidate_ids},
        ),
        "pending_candidate_ids": pending_candidate_ids,
    }


def build_form_content_handoff(
    *,
    context: BrowserInputContext,
    completed_candidate_ids: Iterable[str],
    user_id: str,
    include_completed_media: bool,
) -> Dict[str, Any]:
    """Project authoritative article content into a user-visible handoff."""
    completed = {str(item).strip() for item in completed_candidate_ids}
    title = ""
    body = ""
    images = []
    for candidate in context.candidates:
        authority = str(candidate.metadata.get("binding_authority") or "")
        role = str(candidate.metadata.get("field_role") or "")
        if authority == "publish_payload" and role == "title" and not title:
            title = str(candidate.value or "")
        elif authority == "publish_payload" and role == "body" and not body:
            body = str(candidate.plain_text or candidate.value or "")
        if candidate.value_kind != "file" or (
            not include_completed_media and candidate.candidate_id in completed
        ):
            continue
        for source_index, source in enumerate(list(candidate.value or [])):
            source_text = str(source or "").strip()
            if not source_text:
                continue
            resource = candidate.metadata.get("handoff_resource")
            display = _display_resource(
                resource if isinstance(resource, Mapping) else {},
                source=source_text,
                user_id=user_id,
            )
            images.append({
                "candidate_id": candidate.candidate_id,
                "source_index": source_index,
                "filename": display["filename"],
                "url": display["url"],
                "download_url": display["url"],
                **(
                    {"_oss_object_path": display["object_path"]}
                    if display.get("object_path") else {}
                ),
                "anchor": dict(candidate.metadata.get("media_anchor") or {}),
                "completed_by_agent": candidate.candidate_id in completed,
            })
    return {
        "schema_version": "1.0",
        "article": {"title": title, "body": body},
        "images": images,
        "pending_candidate_ids": list(dict.fromkeys(
            str(item["candidate_id"])
            for item in images
            if not bool(item.get("completed_by_agent"))
        )),
    }


def augment_form_assistance_handoff(
    handoff: Mapping[str, Any] | None,
    *,
    context: BrowserInputContext,
    completed_candidate_ids: Iterable[str],
    user_id: str,
) -> Dict[str, Any] | None:
    """Attach article assets to every typed form-assistance contract."""
    if not isinstance(handoff, Mapping):
        return None
    output = dict(handoff)
    contract = output.get("contract")
    if not isinstance(contract, Mapping):
        return output
    kind = str(contract.get("kind") or "")
    if not kind.startswith("form_"):
        return output
    if kind == FORM_MEDIA_CATEGORY and output.get("article") is not None:
        return output
    content = build_form_content_handoff(
        context=context,
        completed_candidate_ids=completed_candidate_ids,
        user_id=user_id,
        include_completed_media=True,
    )
    return {**content, **output}


def media_upload_assistance_decision(
    handoff: Mapping[str, Any] | None,
    *,
    lang: str,
) -> Optional[Decision]:
    if not handoff:
        return None
    zh = str(lang or "").startswith("zh")
    return Decision(
        tool="browser_ask_user",
        args={
            "question": (
                "自动上传图片未成功。文章和待上传图片已展示在协助卡中，"
                "请在浏览器中手动上传，勾选已完成的图片后继续执行。"
                if zh else
                "Automatic image upload did not complete. Use the article and images "
                "shown in the assistance card, mark uploaded images, then continue."
            ),
            "category": MEDIA_UPLOAD_CATEGORY,
            "handoff": dict(handoff),
        },
        rationale="media upload receiver recovery exhausted; hand off visible assets to the user",
    )


def _display_resource(
    resource: Mapping[str, Any],
    *,
    source: str,
    user_id: str,
) -> Dict[str, str]:
    filename = str(resource.get("filename") or "").strip() or _filename(source)
    for key in ("signed_url", "url", "source_url"):
        value = str(resource.get(key) or "").strip()
        if _is_client_url(value):
            return {
                "filename": filename,
                "url": value,
                "object_path": str(resource.get("object_path") or "").strip(),
            }
    if _is_client_url(source):
        return {"filename": filename, "url": source, "object_path": ""}

    object_path = str(resource.get("object_path") or "").strip()
    try:
        storage = ObjectStorageClient()
        if object_path:
            url = str(storage.sign_url(object_path) or "").strip()
            if url:
                return {"filename": filename or _filename(object_path), "url": url, "object_path": object_path}
        local = Path(source).expanduser()
        if local.is_file():
            if storage.storage_backend == "local":
                try:
                    relative = local.resolve().relative_to(
                        storage.local_storage_path.resolve(),
                    ).as_posix()
                    return {"filename": filename, "url": storage.sign_url(relative), "object_path": relative}
                except ValueError:
                    pass
            url, uploaded_path = storage.upload_file_with_path(str(local), user_id)
            return {"filename": filename, "url": str(url or ""), "object_path": uploaded_path}
    except Exception:
        pass
    return {"filename": filename, "url": "", "object_path": ""}


def _is_client_url(value: str) -> bool:
    token = str(value or "").strip()
    if token.startswith("/") and not token.startswith("//"):
        return True
    return urlparse(token).scheme.lower() in {"http", "https"}


def _filename(value: str) -> str:
    token = urlparse(str(value or "")).path
    return Path(token).name or "image"


__all__ = [
    "MEDIA_UPLOAD_CATEGORY",
    "augment_form_assistance_handoff",
    "build_form_content_handoff",
    "build_media_upload_handoff",
    "completed_media_candidate_ids",
    "is_media_delivery_handoff_error",
    "is_media_upload_receiver_error",
    "media_upload_assistance_decision",
]
