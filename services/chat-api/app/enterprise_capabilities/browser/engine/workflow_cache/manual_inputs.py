from __future__ import annotations

import hashlib
import html
import re
from typing import Any, Dict

from app.enterprise_capabilities.browser.engine.form_input.input_context import InputCandidate

from .control_semantics import infer_control_semantic


def recording_candidates(
    events: list[Dict[str, Any]],
    variable_names: Dict[int, str],
) -> list[InputCandidate]:
    output: list[InputCandidate] = []
    media_index = 0
    for index, event in enumerate(events):
        kind = str(event.get("type") or "").strip().lower()
        if bool(event.get("value_redacted")):
            continue
        sequence = int(event.get("sequence") or index)
        target = event.get("target") if isinstance(event.get("target"), dict) else {}
        semantic = _safe_semantic_name(
            variable_names.get(sequence) or infer_recorded_semantic(target, kind, index),
        )
        if kind in {"fill", "select"}:
            output.append(_candidate(sequence, semantic, str(event.get("value") or ""), "text"))
        elif kind in {"upload", "paste_image"}:
            semantic = semantic if semantic != f"field_{index + 1}" else "media"
            output.append(_candidate(
                sequence, semantic, [f"recording://{semantic}/{media_index}"], "file",
            ))
            media_index += 1
    return output


def infer_capability(operation: str, events: list[Dict[str, Any]]) -> str:
    text = str(operation or "").casefold()
    if any(token in text for token in ("发布", "发表", "publish", "post")):
        return "browser.publish"
    if any(token in text for token in ("删除", "delete", "remove")):
        return "browser.delete"
    if any(token in text for token in ("编辑", "修改", "update", "edit")):
        return "browser.modify"
    if any(token in text for token in ("提交", "保存", "草稿", "submit", "save", "send")):
        return "browser.submit"
    if any(token in text for token in ("上传", "附件", "upload", "attach")):
        return "browser.file_transfer"
    if any(token in text for token in ("选择", "设置", "切换", "select", "configure", "change")):
        return "browser.modify"
    if any(token in text for token in ("搜索", "查询", "search", "query")):
        return "browser.search"
    if any(str(item.get("type") or "") in {"fill", "select", "upload", "paste_image"} for item in events):
        return "browser.submit"
    return "browser.navigate"


def _candidate(sequence: int, semantic: str, value: Any, kind: str) -> InputCandidate:
    source_path = f"manual.{semantic}.{sequence}"
    text_value = str(value) if kind == "text" else ""
    plain_text = _plain_text(text_value)
    return InputCandidate(
        candidate_id=hashlib.sha256(source_path.encode("utf-8")).hexdigest()[:20],
        source_kind="human_recording",
        source_path=source_path,
        semantic_name=semantic,
        value=value,
        value_kind=kind,
        plain_text=plain_text,
        rich_html=(text_value if kind == "text" and "<" in text_value else ""),
    )


def infer_recorded_semantic(target: Dict[str, Any], kind: str, index: int = 0) -> str:
    return infer_control_semantic(target, action=kind, fallback_index=index)


def _safe_semantic_name(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip()).strip("_").lower()
    return name[:64] or "input"


def _plain_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", html.unescape(str(value or "")))
    return " ".join(without_tags.replace("\u200b", "").split())


__all__ = ["infer_capability", "infer_recorded_semantic", "recording_candidates"]
