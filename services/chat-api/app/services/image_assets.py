from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.utils.oss_uploader import AliyunOSSUploader


def _one_line(value: Any, limit: int = 500) -> str:
    text = str(value or "").strip()
    text = " ".join(text.split())
    return text[:limit]


def _resolve_image_url(image: Dict[str, Any]) -> str:
    object_path = str(image.get("object_path") or "").strip()
    if object_path:
        try:
            return str(AliyunOSSUploader().sign_url(object_path) or "").strip()
        except Exception:
            pass
    for key in ("signed_url", "url"):
        value = str(image.get(key) or "").strip()
        if value:
            return value
    return ""


def _join_tokens(values: List[str], limit: int = 6) -> str:
    tokens: List[str] = []
    seen = set()
    for value in values:
        token = str(value or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
        if len(tokens) >= limit:
            break
    return " / ".join(tokens)


def _build_summary(*, image_no: int, fact: Dict[str, Any], filename: str) -> str:
    page_area = str(fact.get("page_area") or "").strip()
    flow = str(fact.get("flow_relationship") or "").strip()
    fields = [str(x or "").strip() for x in (fact.get("visible_fields") or []) if str(x or "").strip()]
    controls = [str(x or "").strip() for x in (fact.get("controls") or []) if str(x or "").strip()]
    status_tags = [str(x or "").strip() for x in (fact.get("status_tags") or []) if str(x or "").strip()]

    parts: List[str] = []
    if page_area:
        parts.append(f"页面：{page_area}")
    if fields:
        parts.append(f"字段：{_join_tokens(fields, limit=5)}")
    if controls:
        parts.append(f"控件：{_join_tokens(controls, limit=4)}")
    if status_tags:
        parts.append(f"状态：{_join_tokens(status_tags, limit=4)}")
    if flow and "not identified" not in flow.lower():
        parts.append(f"流程：{flow}")
    if not parts:
        title = filename or f"image_{image_no}"
        parts.append(f"截图：{title}")
    return "；".join(parts)


def build_uploaded_image_assets(
    *,
    images: List[Dict[str, Any]],
    image_facts: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    fact_items = (image_facts or {}).get("images") or []
    fact_by_index: Dict[int, Dict[str, Any]] = {}
    for item in fact_items:
        if not isinstance(item, dict):
            continue
        try:
            fact_by_index[int(item.get("image_index") or 0)] = item
        except Exception:
            continue

    global_subjects = [
        str(x or "").strip()
        for x in (((image_facts or {}).get("subject_candidates") or (image_facts or {}).get("entities") or []))
        if str(x or "").strip()
    ]
    global_ui_terms = [
        str(x or "").strip()
        for x in ((image_facts or {}).get("ui_terms") or [])
        if str(x or "").strip()
    ]
    assets: List[Dict[str, Any]] = []

    for idx, raw in enumerate(images or [], start=1):
        if not isinstance(raw, dict):
            continue
        path = _resolve_image_url(raw)
        object_path = str(raw.get("object_path") or "").strip()
        filename = str(raw.get("filename") or f"image_{idx}").strip()
        fact = fact_by_index.get(idx) or {}
        page_area = str(fact.get("page_area") or "").strip()
        flow = str(fact.get("flow_relationship") or "").strip()
        fields = [str(x or "").strip() for x in (fact.get("visible_fields") or []) if str(x or "").strip()]
        controls = [str(x or "").strip() for x in (fact.get("controls") or []) if str(x or "").strip()]
        status_tags = [str(x or "").strip() for x in (fact.get("status_tags") or []) if str(x or "").strip()]

        tags = []
        for token in global_subjects + [page_area, flow] + fields[:6] + controls[:4] + status_tags[:4] + global_ui_terms[:8]:
            value = str(token or "").strip()
            if value and value not in tags:
                tags.append(value)

        assets.append(
            {
                "asset_id": f"uploaded_image_{idx}",
                "image_index": idx,
                "source": "user_upload",
                "path": path or object_path,
                "signed_url": path,
                "object_path": object_path,
                "filename": filename,
                "content_type": raw.get("content_type"),
                "size": raw.get("size"),
                "page_area": page_area,
                "flow_relationship": flow,
                "visible_fields": fields,
                "controls": controls,
                "status_tags": status_tags,
                "tags": tags[:16],
                "summary": _build_summary(image_no=idx, fact=fact, filename=filename),
            }
        )

    return assets


def build_embedded_document_image_assets(
    *,
    embedded_images: List[Dict[str, Any]],
    source_document_id: str = "",
) -> List[Dict[str, Any]]:
    assets: List[Dict[str, Any]] = []
    for idx, raw in enumerate(embedded_images or [], start=1):
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("signed_url") or raw.get("url") or raw.get("object_path") or "").strip()
        if not path:
            continue
        image_id = str(raw.get("image_id") or f"embedded_image_{idx}").strip()
        near_text = _one_line(raw.get("near_text"), 900)
        before_text = _one_line(raw.get("before_text"), 450)
        after_text = _one_line(raw.get("after_text"), 450)
        caption_seed = _one_line(raw.get("caption_seed") or near_text or raw.get("filename") or image_id, 180)
        context = "\n".join([x for x in [before_text, after_text] if x]).strip()
        tags: List[str] = []
        for value in [
            raw.get("caption_seed"),
            raw.get("filename"),
            source_document_id,
            *near_text.replace("\n", " ").split(" ")[:12],
        ]:
            token = str(value or "").strip()
            if token and token not in tags:
                tags.append(token)
        assets.append(
            {
                "asset_id": f"docx_{image_id}",
                "image_index": int(raw.get("image_index") or idx),
                "source": "embedded_docx_image",
                "path": path,
                "signed_url": str(raw.get("signed_url") or raw.get("url") or "").strip(),
                "object_path": str(raw.get("object_path") or "").strip(),
                "filename": str(raw.get("filename") or image_id).strip(),
                "content_type": raw.get("content_type"),
                "size": raw.get("size"),
                "page_area": caption_seed[:120],
                "flow_relationship": near_text[:500],
                "visible_fields": [],
                "controls": [],
                "status_tags": [],
                "tags": tags[:16],
                "summary": (
                    f"原始Word内嵌图片；邻近文本：{near_text[:700]}"
                    if near_text
                    else f"原始Word内嵌图片：{caption_seed[:180]}"
                ),
                "source_document_id": source_document_id,
                "source_context": context[:1000],
                "paragraph_index": raw.get("paragraph_index"),
                "source_order": raw.get("source_order"),
            }
        )
    return assets
