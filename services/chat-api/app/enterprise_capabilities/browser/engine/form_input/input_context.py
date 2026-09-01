from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .artifact_scope import browser_publish_ancestor_artifacts
from .binding_authority import authority_metadata
from .publish_projection import project_browser_publish_payload
from .resource_projection import project_resource_artifact


_FILE_KEYS = {
    "attachment", "attachments", "file", "files", "document", "documents",
    "downloaded_files", "exported_file", "image", "images", "media", "visual_assets",
    "附件", "文件", "文档", "图片", "媒体",
}
_FILE_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".ppt", ".pptx",
    ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".zip",
}
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)


@dataclass(frozen=True)
class InputCandidate:
    candidate_id: str
    source_kind: str
    source_path: str
    semantic_name: str
    value: Any
    value_kind: str = "text"
    plain_text: str = ""
    rich_html: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def preview(self, limit: int = 1200) -> str:
        if isinstance(self.value, list):
            text = ", ".join(str(item) for item in self.value)
        else:
            text = str(self.value or "")
        return text[:limit]


@dataclass
class BrowserInputContext:
    original_request: str
    candidates: List[InputCandidate] = field(default_factory=list)

    @classmethod
    def from_runtime(
        cls,
        *,
        original_request: str,
        node: Any,
        output_spec: Dict[str, Any],
    ) -> "BrowserInputContext":
        spec = output_spec if isinstance(output_spec, dict) else {}
        graph_artifacts = spec.get("graph_artifacts") if isinstance(spec.get("graph_artifacts"), dict) else {}
        predecessor = spec.get("predecessor_artifacts") if isinstance(spec.get("predecessor_artifacts"), dict) else {}
        selected: Dict[str, Any] = {}
        for dep_id in list(getattr(node, "depends_on", None) or []):
            artifact = graph_artifacts.get(str(dep_id))
            if isinstance(artifact, dict):
                selected[str(dep_id)] = artifact
        for dep_id, artifact in predecessor.items():
            if isinstance(artifact, dict):
                selected.setdefault(str(dep_id), artifact)
        for source_id, artifact in browser_publish_ancestor_artifacts(
            node=node,
            output_spec=spec,
        ).items():
            selected.setdefault(source_id, artifact)

        candidates: List[InputCandidate] = []
        projection = project_browser_publish_payload(selected, output_spec=spec)
        if projection is not None:
            candidates.extend(_publish_payload_candidates(
                projection.payload,
                f"artifacts.{projection.source_id}.publish_payload",
            ))
            for dep_id, artifact in selected.items():
                candidates.extend(_walk_artifact_remainder(
                    artifact,
                    f"artifacts.{dep_id}",
                ))
        else:
            for dep_id, artifact in selected.items():
                candidates.extend(_walk_artifact_candidates(
                    artifact,
                    f"artifacts.{dep_id}",
                ))

        # Explicit user values are useful when there is no upstream node, but
        # only extract values whose shape is unambiguous. Free-form generation
        # remains the constrained model resolver's job.
        for index, email in enumerate(dict.fromkeys(_EMAIL_RE.findall(original_request or ""))):
            candidates.append(_candidate(
                source_kind="user_input",
                source_path=f"user_request.email.{index}",
                semantic_name="recipient_email",
                value=email,
            ))
        return cls(
            original_request=str(original_request or ""),
            candidates=_dedupe(candidates)[:120],
        )

    def by_id(self) -> Dict[str, InputCandidate]:
        return {item.candidate_id: item for item in self.candidates}

    def model_payload(self, *, limit: int = 60) -> List[Dict[str, Any]]:
        return [
            {
                "candidate_id": item.candidate_id,
                "source_kind": item.source_kind,
                "source_path": item.source_path,
                "semantic_name": item.semantic_name,
                "value_kind": item.value_kind,
                "has_rich_html": bool(item.rich_html),
                "binding_authority": str(
                    item.metadata.get("binding_authority") or ""
                ),
                "field_role": str(item.metadata.get("field_role") or ""),
                "preview": item.preview(),
            }
            for item in self.candidates[:limit]
        ]

    def authoritative_form_values(self) -> List[str]:
        """Return canonical text values that must be placed before publishing."""
        values: List[str] = []
        for item in self.candidates:
            if item.value_kind == "file":
                continue
            if item.metadata.get("binding_authority") != "publish_payload":
                continue
            if item.metadata.get("field_role") not in {"title", "body"}:
                continue
            value = str(item.plain_text or item.value or "")
            if value.strip():
                values.append(value)
        return values

    def requires_authoritative_form_input(self) -> bool:
        return bool(self.authoritative_form_values())


def _walk_artifact_candidates(artifact: Dict[str, Any], path: str) -> List[InputCandidate]:
    payload = artifact.get("publish_payload")
    if not _is_publish_payload(payload):
        return _walk_resource_aware_candidates(artifact, path)

    out = _publish_payload_candidates(dict(payload), f"{path}.publish_payload")
    out.extend(_walk_artifact_remainder(artifact, path))
    return out


def _walk_artifact_remainder(artifact: Dict[str, Any], path: str) -> List[InputCandidate]:
    # The payload is the canonical projection of generated content. Preserve
    # unrelated values, but suppress sibling draft copies that would compete
    # with its title/body candidates.
    content_copies = {
        "answer", "article_markdown", "report_markdown", "draft_markdown",
        "dynamic_markdown", "edited_markdown", "final_answer",
        "final_markdown", "final_publish_markdown", "transformed_markdown",
        "markdown", "content", "document_source", "publish_assembly",
        "publish_payload",
    }
    remainder = {
        key: value for key, value in artifact.items()
        if str(key) not in content_copies
    }
    return _walk_resource_aware_candidates(remainder, path)


def _walk_resource_aware_candidates(
    artifact: Dict[str, Any],
    path: str,
) -> List[InputCandidate]:
    projection = project_resource_artifact(artifact, source_path=path)
    if projection is None:
        return _walk_candidates(artifact, path)

    out: List[InputCandidate] = []
    for batch in projection.batches:
        sources = list(dict.fromkeys(
            source
            for source in (_file_source(item) for item in batch.values)
            if source
        ))
        if not sources:
            continue
        out.append(_candidate(
            source_kind="upstream",
            source_path=batch.source_path,
            semantic_name=batch.semantic_name,
            value=sources,
            value_kind="file",
        ))
    out.extend(_walk_candidates(projection.remainder, path))
    return out


def _is_publish_payload(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and str(value.get("schema_version") or "").strip() == "1.0"
        and any(str(value.get(key) or "").strip() for key in (
            "title", "body_markdown", "body_plain_text", "body_html",
        ))
    )


def _publish_payload_candidates(payload: Dict[str, Any], path: str) -> List[InputCandidate]:
    out: List[InputCandidate] = []
    title = str(payload.get("title") or "").strip()
    if title:
        out.append(_candidate(
            source_kind="upstream",
            source_path=f"{path}.title",
            semantic_name="title",
            value=title,
            metadata=dict(authority_metadata("title")),
        ))

    markdown = str(payload.get("body_markdown") or "").strip()
    plain_text = str(payload.get("body_plain_text") or "").strip()
    rich_html = str(payload.get("body_html") or "").strip()
    # Browser editors consume either plain text or HTML. Markdown remains the
    # canonical generation artifact, but must not become the default field
    # value: if a rich editor is temporarily classified as a textarea (or a
    # model adopts the candidate), raw ``##``/``**`` markers would leak into
    # the published content.
    body_value = plain_text or markdown
    if body_value:
        out.append(_candidate(
            source_kind="upstream",
            source_path=f"{path}.body",
            semantic_name="body",
            value=body_value,
            value_kind="rich_text" if rich_html else "text",
            plain_text=plain_text or body_value,
            rich_html=rich_html,
            metadata=dict(authority_metadata("body")),
        ))

    for index, item in enumerate(list(payload.get("media") or [])):
        source = _file_source(item)
        if not source:
            continue
        out.append(_candidate(
            source_kind="upstream",
            source_path=f"{path}.media.{index}",
            semantic_name="media",
            value=[source],
            value_kind="file",
            metadata={
                **authority_metadata("attachment"),
                "handoff_resource": _handoff_resource(item, source),
                "media_anchor": {
                    "after_text": str(item.get("anchor_after_text") or "")
                    if isinstance(item, dict) else "",
                    "before_text": str(item.get("anchor_before_text") or "")
                    if isinstance(item, dict) else "",
                    "plain_offset": max(
                        0,
                        int(item.get("anchor_plain_offset") or 0),
                    ) if isinstance(item, dict) else 0,
                    "order": int(item.get("order") or index)
                    if isinstance(item, dict) else index,
                },
            },
        ))
    return out


def _handoff_resource(item: Any, source: str) -> Dict[str, str]:
    if not isinstance(item, dict):
        return {"filename": Path(str(source or "")).name}
    return {
        key: str(item.get(key) or "").strip()
        for key in ("filename", "signed_url", "url", "source_url", "object_path")
        if str(item.get(key) or "").strip()
    }


def _walk_candidates(value: Any, path: str, *, depth: int = 0) -> List[InputCandidate]:
    if depth > 6 or value is None:
        return []
    if isinstance(value, (str, int, float, bool)):
        text = str(value).strip()
        if not text:
            return []
        return [_candidate(
            source_kind="upstream",
            source_path=path,
            semantic_name=_last_semantic_name(path),
            value=value,
            value_kind="text",
        )]
    if isinstance(value, list):
        files = [_file_source(item) for item in value]
        files = [item for item in files if item]
        semantic_name = _last_semantic_name(path).casefold()
        if (
            files
            and len(files) == len(value)
            and (
                semantic_name in _FILE_KEYS
                or all(_looks_like_file(item) for item in files)
            )
        ):
            return [_candidate(
                source_kind="upstream",
                source_path=path,
                semantic_name=_last_semantic_name(path),
                value=files,
                value_kind="file",
            )]
        out: List[InputCandidate] = []
        for index, item in enumerate(value[:50]):
            out.extend(_walk_candidates(item, f"{path}.{index}", depth=depth + 1))
        return out
    if not isinstance(value, dict):
        return []

    source = _file_source(value)
    if source and (_last_semantic_name(path).casefold() in _FILE_KEYS or _looks_like_file(source)):
        return [_candidate(
            source_kind="upstream",
            source_path=path,
            semantic_name=_last_semantic_name(path),
            value=[source],
            value_kind="file",
        )]

    out: List[InputCandidate] = []
    for key, item in list(value.items())[:80]:
        if str(key).startswith("_") or key in {"browser_receipt", "skill_state", "skill_finalize"}:
            continue
        out.extend(_walk_candidates(item, f"{path}.{key}", depth=depth + 1))
    return out


def _candidate(
    *,
    source_kind: str,
    source_path: str,
    semantic_name: str,
    value: Any,
    value_kind: str = "text",
    plain_text: str = "",
    rich_html: str = "",
    metadata: Dict[str, Any] | None = None,
) -> InputCandidate:
    digest = hashlib.sha1(f"{source_kind}\0{source_path}".encode("utf-8")).hexdigest()[:12]
    return InputCandidate(
        candidate_id=f"in_{digest}",
        source_kind=source_kind,
        source_path=source_path,
        semantic_name=semantic_name,
        value=value,
        value_kind=value_kind,
        plain_text=plain_text,
        rich_html=rich_html,
        metadata=dict(metadata or {}),
    )


def _dedupe(items: Iterable[InputCandidate]) -> List[InputCandidate]:
    candidates = list(items)
    anchored_file_identities = {
        _file_identity(item)
        for item in candidates
        if item.value_kind == "file"
        and _has_media_anchor(item)
        and _file_identity(item)
    }
    out: List[InputCandidate] = []
    seen = set()
    for item in candidates:
        file_identity = _file_identity(item)
        if file_identity:
            if not _has_media_anchor(item) and file_identity in anchored_file_identities:
                continue
            key = (
                "file",
                file_identity,
                _media_anchor_identity(item) if _has_media_anchor(item) else (),
            )
        else:
            key = ("value", item.source_path, item.preview(limit=300))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _file_identity(item: InputCandidate) -> tuple[str, ...]:
    if item.value_kind != "file":
        return ()
    return tuple(
        str(source).strip()
        for source in list(item.value or [])
        if str(source).strip()
    )


def _has_media_anchor(item: InputCandidate) -> bool:
    anchor = item.metadata.get("media_anchor")
    return isinstance(anchor, dict) and any(
        anchor.get(key) not in {None, ""}
        for key in ("after_text", "before_text", "plain_offset")
    )


def _media_anchor_identity(item: InputCandidate) -> tuple[str, str, int, int]:
    anchor = item.metadata.get("media_anchor")
    if not isinstance(anchor, dict):
        return ("", "", 0, 0)
    return (
        str(anchor.get("after_text") or "").strip(),
        str(anchor.get("before_text") or "").strip(),
        max(0, int(anchor.get("plain_offset") or 0)),
        int(anchor.get("order") or 0),
    )


def _last_semantic_name(path: str) -> str:
    parts = [part for part in str(path or "").split(".") if part and not part.isdigit()]
    return parts[-1] if parts else "value"


def _file_source(value: Any) -> str:
    if isinstance(value, str):
        return value.strip() if _looks_like_file(value) else ""
    if not isinstance(value, dict):
        return ""
    for key in ("local_path", "path_or_url", "signed_url", "url", "path", "source_url"):
        candidate = str(value.get(key) or "").strip()
        if candidate:
            return candidate
    return ""


def _looks_like_file(value: str) -> bool:
    token = str(value or "").split("?", 1)[0].split("#", 1)[0]
    return Path(token).suffix.casefold() in _FILE_EXTENSIONS
