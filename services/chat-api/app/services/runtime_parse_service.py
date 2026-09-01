from __future__ import annotations

import base64
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any, Dict, List

from app.services.document_context import document_context_service
from app.services.document_parse_error_presenter import user_facing_parse_error
from app.services.document_parser import document_parser_service
from app.services.image_assets import build_embedded_document_image_assets, build_uploaded_image_assets
from app.services.vision import vision_service

logger = logging.getLogger(__name__)


class RuntimeParseService:
    """Graph-time wrappers around the existing upload parse services.

    Upload preprocessing remains the owner of user-upload parsing. This service
    only normalizes graph artifacts produced by upstream nodes, then calls the
    same document and vision services so downstream consumers see familiar
    ``output_spec.documents`` / ``output_spec.multimodal`` shapes.
    """

    _IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif", "bmp"}
    _DOCUMENT_EXTS = {
        "pdf",
        "pptx",
        "docx",
        "xlsx",
        "xlsm",
        "xls",
        "csv",
        "tsv",
        "md",
        "markdown",
        "txt",
    }

    @staticmethod
    def _payload_from_inputs(*, node: Any, output_spec: Dict[str, Any]) -> Dict[str, Any]:
        graph_artifacts = dict((output_spec or {}).get("graph_artifacts") or {})
        predecessor_artifacts: Dict[str, Any] = {
            str(key): dict(value)
            for key, value in dict((output_spec or {}).get("predecessor_artifacts") or {}).items()
            if isinstance(value, dict)
        }
        flattened: Dict[str, Any] = {
            str(key): value
            for key, value in dict((output_spec or {}).get("input_artifacts") or {}).items()
            if not str(key).startswith("_")
        }
        for dep_id in list(getattr(node, "depends_on", None) or []):
            artifact = graph_artifacts.get(str(dep_id))
            if not isinstance(artifact, dict):
                continue
            predecessor_artifacts.setdefault(str(dep_id), artifact)
            for key, value in artifact.items():
                if str(key).startswith("_"):
                    continue
                flattened.setdefault(str(key), value)
        for artifact in predecessor_artifacts.values():
            if not isinstance(artifact, dict):
                continue
            for key, value in artifact.items():
                if str(key).startswith("_"):
                    continue
                flattened.setdefault(str(key), value)
        return {
            "predecessor_artifacts": predecessor_artifacts,
            "input_artifacts": flattened,
            **flattened,
        }

    @staticmethod
    def _ext(value: str) -> str:
        token = str(value or "").split("?", 1)[0].split("#", 1)[0].strip().lower()
        if "." not in token:
            return ""
        return token.rsplit(".", 1)[-1]

    @classmethod
    def _looks_like_image(cls, item: Dict[str, Any]) -> bool:
        content_type = str(item.get("content_type") or "").strip().lower()
        if content_type.startswith("image/"):
            return True
        source = str(item.get("filename") or item.get("object_path") or item.get("path_or_url") or item.get("url") or item.get("source_url") or item.get("path") or "").strip()
        return cls._ext(source) in cls._IMAGE_EXTS

    @classmethod
    def _looks_like_document(cls, item: Dict[str, Any]) -> bool:
        content_type = str(item.get("content_type") or "").strip().lower()
        if content_type and not content_type.startswith("image/"):
            return True
        source = str(item.get("filename") or item.get("object_path") or item.get("path_or_url") or item.get("url") or item.get("source_url") or item.get("path") or "").strip()
        return cls._ext(source) in cls._DOCUMENT_EXTS

    @staticmethod
    def _normalize_file(value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        path_or_url = str(value.get("path_or_url") or value.get("url") or value.get("source_url") or value.get("path") or value.get("local_path") or "").strip()
        object_path = str(value.get("object_path") or "").strip()
        signed_url = str(value.get("signed_url") or "").strip()
        filename = str(value.get("filename") or "").strip()
        if not filename and (path_or_url or object_path):
            filename = Path((path_or_url or object_path).split("?", 1)[0]).name
        out = {
            "filename": filename,
            "content_type": str(value.get("content_type") or "").strip(),
            "size": value.get("size"),
            "object_path": object_path,
            "signed_url": signed_url,
        }
        raw_url = str(value.get("url") or value.get("source_url") or value.get("path_or_url") or "").strip()
        if signed_url:
            out["url"] = signed_url
        elif raw_url.startswith(("http://", "https://", "data:", "/api/", "api/")):
            out["url"] = raw_url
        elif path_or_url.startswith(("http://", "https://", "data:", "/api/", "api/")):
            out["url"] = path_or_url
        local_path = str(value.get("local_path") or value.get("path") or "").strip()
        if local_path and not local_path.startswith(("http://", "https://", "data:", "/api/", "api/")):
            out["local_path"] = local_path
        elif path_or_url and not out.get("url") and not object_path and not signed_url:
            out["local_path"] = path_or_url
        return {k: v for k, v in out.items() if v not in ("", None)}

    @staticmethod
    def _resource_types_from_node(node: Any) -> List[str]:
        meta = getattr(node, "meta", None) or {}
        semantic_config = meta.get("semantic_config") if isinstance(meta.get("semantic_config"), dict) else {}
        raw = (
            semantic_config.get("resourceTypes")
            or semantic_config.get("resource_types")
            or semantic_config.get("categories")
            or semantic_config.get("types")
            or meta.get("resource_types")
            or meta.get("resourceTypes")
        )
        if isinstance(raw, str):
            tokens = [item.strip() for item in re.split(r"[,，/、\s]+", raw) if item.strip()]
        elif isinstance(raw, list):
            tokens = [str(item or "").strip() for item in raw if str(item or "").strip()]
        else:
            tokens = []
        alias = {
            "image": "images",
            "images": "images",
            "图片": "images",
            "图像": "images",
            "url": "urls",
            "urls": "urls",
            "link": "urls",
            "links": "urls",
            "链接": "urls",
            "网址": "urls",
            "attachment": "attachments",
            "attachments": "attachments",
            "附件": "attachments",
            "文件": "attachments",
        }
        out: List[str] = []
        for token in tokens:
            key = alias.get(token.lower()) or alias.get(token)
            if key and key not in out:
                out.append(key)
        return out or ["images", "urls", "attachments"]

    @staticmethod
    def _dedupe_dicts(items: List[Dict[str, Any]], keys: List[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            marker = "|".join(str(item.get(key) or "").strip() for key in keys)
            if not marker.strip("|"):
                marker = str(item)
            if marker in seen:
                continue
            seen.add(marker)
            out.append(dict(item))
        return out

    @staticmethod
    def _extract_urls_from_text(text: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for match in re.finditer(r"https?://[^\s<>'\"）)】]+", str(text or "")):
            url = match.group(0).rstrip(".,;:!?。；：！？")
            if url:
                out.append({"url": url, "source": "parsed_text"})
        return out

    @classmethod
    def _extract_urls_from_value(cls, value: Any, *, source: str, depth: int = 0) -> List[Dict[str, Any]]:
        if depth > 8:
            return []
        urls: List[Dict[str, Any]] = []
        if isinstance(value, str):
            for item in cls._extract_urls_from_text(value):
                urls.append({**item, "source": source})
        elif isinstance(value, dict):
            for key, nested in value.items():
                if str(key).startswith("_"):
                    continue
                child_source = f"{source}.{key}" if source else str(key)
                urls.extend(cls._extract_urls_from_value(nested, source=child_source, depth=depth + 1))
        elif isinstance(value, list):
            for idx, nested in enumerate(value[:200]):
                urls.extend(cls._extract_urls_from_value(nested, source=f"{source}[{idx}]", depth=depth + 1))
        return urls

    @staticmethod
    def _asset_to_image_candidate(asset: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(asset, dict):
            return {}
        path = str(asset.get("path") or asset.get("signed_url") or asset.get("url") or asset.get("local_path") or "").strip()
        out = {
            "filename": str(asset.get("filename") or "").strip(),
            "content_type": str(asset.get("content_type") or "").strip(),
            "size": asset.get("size"),
            "object_path": str(asset.get("object_path") or "").strip(),
            "signed_url": str(asset.get("signed_url") or "").strip(),
        }
        if path.startswith(("http://", "https://", "data:")):
            out["url"] = path
        elif path:
            out["local_path"] = path
        return {k: v for k, v in out.items() if v not in ("", None)}

    def _collect_uploaded_asset_images(self, *, output_spec: Dict[str, Any], payload: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        containers: List[Dict[str, Any]] = []
        multimodal = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
        if isinstance(multimodal, dict):
            containers.append(multimodal)
        resources = output_spec.get("resources") if isinstance(output_spec.get("resources"), dict) else {}
        if isinstance(resources, dict):
            containers.append(resources)
        for artifact in ((payload or {}).get("predecessor_artifacts") or {}).values():
            if not isinstance(artifact, dict):
                continue
            containers.append(artifact)
            nested = artifact.get("multimodal") if isinstance(artifact.get("multimodal"), dict) else {}
            if nested:
                containers.append(nested)
            bundle = artifact.get("resource_bundle") if isinstance(artifact.get("resource_bundle"), dict) else {}
            if bundle:
                containers.append(bundle)
        for container in containers:
            parsed_documents = container.get("parsed_documents")
            if isinstance(parsed_documents, list):
                for doc in parsed_documents:
                    if not isinstance(doc, dict):
                        continue
                    embedded_assets = build_embedded_document_image_assets(
                        embedded_images=[dict(x) for x in list(doc.get("embedded_images") or []) if isinstance(x, dict)],
                        source_document_id=str(doc.get("asset_id") or doc.get("filename") or "").strip(),
                    )
                    for asset in embedded_assets:
                        normalized = self._asset_to_image_candidate(asset)
                        if normalized and self._looks_like_image(normalized):
                            candidates.append(normalized)
            for key in ("uploaded_assets", "images"):
                raw = container.get(key)
                if not isinstance(raw, list):
                    continue
                for item in raw:
                    normalized = self._asset_to_image_candidate(item) or self._normalize_file(item)
                    if normalized and self._looks_like_image(normalized):
                        candidates.append(normalized)
        return self._dedupe_dicts(candidates, ["object_path", "signed_url", "url", "local_path", "filename"])

    def _collect_source_files(self, *, node: Any, output_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        payload = self._payload_from_inputs(node=node, output_spec=output_spec)
        candidates: List[Dict[str, Any]] = []

        file_obj = self._normalize_file(payload.get("file"))
        if file_obj:
            candidates.append(file_obj)

        for key in ("files", "downloaded_files", "documents", "images", "map_items", "map_results"):
            raw = payload.get(key)
            if isinstance(raw, dict):
                normalized = self._normalize_file(raw)
                if normalized:
                    candidates.append(normalized)
            elif isinstance(raw, list):
                for item in raw:
                    normalized = self._normalize_file(item)
                    if normalized:
                        candidates.append(normalized)

        deduped: List[Dict[str, Any]] = []
        seen = set()
        for item in candidates:
            marker = "|".join(
                [
                    str(item.get("object_path") or ""),
                    str(item.get("signed_url") or ""),
                    str(item.get("url") or ""),
                    str(item.get("local_path") or ""),
                    str(item.get("filename") or ""),
                ]
            )
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(item)
        return deduped

    @staticmethod
    def _existing_parsed_documents(output_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        documents = output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}
        parsed = list((documents or {}).get("parsed_documents") or [])
        return [dict(item) for item in parsed if isinstance(item, dict)]

    def _hydrate_existing_documents(self, *, output_spec: Dict[str, Any]) -> Dict[str, Any]:
        existing = output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}
        parsed_documents = self._existing_parsed_documents(output_spec)
        successful = [item for item in parsed_documents if str(item.get("parse_status") or "") == "parsed"]

        active_document_context = str(
            output_spec.get("active_document_context")
            or (existing or {}).get("active_document_context")
            or ""
        ).strip()
        if not active_document_context:
            active_contexts: List[str] = []
            for item in successful[:3]:
                profile = dict(item.get("profile") or {})
                brief = str(profile.get("active_context_brief") or profile.get("summary") or "").strip()
                if brief:
                    active_contexts.append(brief)
            active_document_context = "\n".join(active_contexts).strip()

        active_document_markdown = str(
            output_spec.get("active_document_markdown")
            or (existing or {}).get("active_document_markdown")
            or ""
        ).strip()
        if not active_document_markdown and successful:
            active_document_markdown = str((successful[0] or {}).get("markdown") or "").strip()

        documents = dict(existing) if isinstance(existing, dict) else {}
        documents.update(
            {
                "enabled": True,
                "count": int(documents.get("count") or len(parsed_documents)),
                "parsed_documents": parsed_documents,
                "active_document_context": active_document_context,
                "active_document_markdown": active_document_markdown,
                "source": str(documents.get("source") or "chat_preparse"),
            }
        )
        output_spec["documents"] = documents
        if active_document_context:
            output_spec["active_document_context"] = active_document_context
        if active_document_markdown:
            output_spec["active_document_markdown"] = active_document_markdown

        embedded_assets: List[Dict[str, Any]] = []
        for item in successful:
            embedded_assets.extend(
                build_embedded_document_image_assets(
                    embedded_images=[dict(x) for x in list(item.get("embedded_images") or []) if isinstance(x, dict)],
                    source_document_id=str(item.get("asset_id") or item.get("filename") or "").strip(),
                )
            )
        if embedded_assets:
            multimodal = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
            existing_assets = [dict(x) for x in list(multimodal.get("uploaded_assets") or []) if isinstance(x, dict)]
            merged_assets = self._merge_uploaded_assets(existing_assets, embedded_assets)
            multimodal = dict(multimodal)
            multimodal["enabled"] = True
            multimodal["uploaded_assets"] = merged_assets
            multimodal["embedded_document_image_count"] = len(
                [item for item in merged_assets if str(item.get("source") or "") == "embedded_docx_image"]
            )
            multimodal["artifact_images"] = [
                str(item.get("path") or "").strip()
                for item in merged_assets
                if str(item.get("path") or "").strip()
            ]
            multimodal["artifact_image_urls"] = list(multimodal["artifact_images"])
            multimodal["source"] = str(multimodal.get("source") or "chat_preparse")
            output_spec["multimodal"] = multimodal

        return {
            "parsed_documents": parsed_documents,
            "documents": documents,
            "active_document_context": active_document_context,
            "active_document_markdown": active_document_markdown,
        }

    @staticmethod
    def _merge_uploaded_assets(existing_assets: List[Dict[str, Any]], new_assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen = set()
        for asset in [*existing_assets, *new_assets]:
            if not isinstance(asset, dict):
                continue
            key = (
                str(asset.get("asset_id") or "").strip(),
                str(asset.get("object_path") or "").strip(),
                str(asset.get("path") or "").strip(),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(dict(asset))
        return merged

    async def _parse_local_document(self, *, item: Dict[str, Any]) -> Dict[str, Any]:
        local_path = str(item.get("local_path") or "").strip()
        filename = str(item.get("filename") or Path(local_path).name).strip()
        if not local_path:
            return {}
        path = Path(local_path)
        if not path.exists() or not path.is_file():
            return {"ok": False, "error": "local_file_missing", "markdown": "", "filename": filename, "source_url": local_path, "parser": "local_runtime"}
        ext = self._ext(filename or local_path)
        content = path.read_bytes()
        markdown = ""
        parser = "local_runtime"
        if ext in {"md", "markdown", "txt"}:
            markdown = content.decode("utf-8-sig", errors="replace").strip()
        elif ext == "pdf":
            pdf_result = document_parser_service._build_pdf_parse_from_bytes(content, filename=filename)
            markdown = str(pdf_result.get("markdown") or "").strip()
            embedded_images = [dict(x) for x in list(pdf_result.get("embedded_images") or []) if isinstance(x, dict)]
            structured_content = dict(pdf_result.get("structured_content") or {})
            parse_quality = dict(pdf_result.get("parse_quality") or {})
            parser = str(pdf_result.get("parser") or parser).strip() or parser
        elif ext == "docx":
            docx_result = document_parser_service._build_docx_parse_from_bytes(
                content,
                filename=filename,
                upload_images=True,
                user_id="runtime-document-parser",
            )
            markdown = str(docx_result.get("markdown") or "").strip()
            embedded_images = [dict(x) for x in list(docx_result.get("embedded_images") or []) if isinstance(x, dict)]
        elif ext == "pptx":
            markdown = document_parser_service._build_markdown_from_local_pptx_bytes(content)
            embedded_images = []
        elif ext in {"xlsx", "xlsm"}:
            markdown = document_parser_service._build_markdown_from_local_xlsx_bytes(content, filename=filename)
            embedded_images = []
        elif ext == "xls":
            markdown = document_parser_service._build_markdown_from_local_xls_bytes(content, filename=filename)
            embedded_images = []
        elif ext in {"csv", "tsv"}:
            delimiter = "\t" if ext == "tsv" else ","
            markdown = document_parser_service._build_markdown_from_local_delimited_bytes(content, filename=filename, delimiter=delimiter)
            embedded_images = []
        else:
            return {"ok": False, "error": "unsupported_local_document", "markdown": "", "filename": filename, "source_url": local_path, "parser": parser}
        if ext in {"md", "markdown", "txt"}:
            embedded_images = []
        if ext != "pdf":
            structured_content = {}
            parse_quality = {}
        return {
            "ok": bool(markdown),
            "error": "" if markdown else "empty_content",
            "markdown": markdown,
            "embedded_images": embedded_images,
            "structured_content": structured_content,
            "parse_quality": parse_quality,
            "filename": filename,
            "source_url": local_path,
            "parser": parser,
        }

    async def parse_documents(
        self,
        *,
        node: Any,
        output_spec: Dict[str, Any],
        user_text: str,
    ) -> Dict[str, Any]:
        sources = [item for item in self._collect_source_files(node=node, output_spec=output_spec) if self._looks_like_document(item)]
        logger.info(
            "runtime_parse_documents_sources node_id=%s source_count=%s filenames=%s",
            str(getattr(node, "node_id", "") or ""),
            len(sources),
            [str(item.get("filename") or item.get("url") or item.get("source_url") or "")[:120] for item in sources[:6]],
        )
        if not sources:
            existing_payload = self._hydrate_existing_documents(output_spec=output_spec)
            if any(str(item.get("parse_status") or "") == "parsed" for item in list(existing_payload.get("parsed_documents") or [])):
                existing_payload["reused_existing_parse"] = True
                return existing_payload
            existing_payload["skipped"] = True
            existing_payload["skip_reason"] = "no_runtime_document_artifacts"
            return existing_payload
        parsed_documents: List[Dict[str, Any]] = []
        active_contexts: List[str] = []

        for idx, item in enumerate(sources[:8], start=1):
            local_path = str(item.get("local_path") or "").strip()
            if local_path and Path(local_path).exists():
                parsed = await self._parse_local_document(item=item)
            else:
                if local_path:
                    logger.info(
                        "runtime_parse_local_path_ignored node_id=%s filename=%s local_path=%s has_object_path=%s has_url=%s",
                        str(getattr(node, "node_id", "") or ""),
                        str(item.get("filename") or "")[:120],
                        local_path[:200],
                        bool(str(item.get("object_path") or "").strip()),
                        bool(str(item.get("url") or item.get("signed_url") or "").strip()),
                    )
                parsed = await document_parser_service.parse_document(document=item, enable_ocr=False)

            filename = str(parsed.get("filename") or item.get("filename") or f"document_{idx}").strip()
            resolved_object_path = document_parser_service.resolve_document_object_path(item)
            if not parsed.get("ok"):
                raw_error = str(parsed.get("error") or "").strip()
                display_error = user_facing_parse_error(
                    parse_error=raw_error,
                    filename=filename,
                    has_object_path=bool(resolved_object_path),
                    has_signed_url=bool(str(item.get("signed_url") or "").strip()),
                )
                parsed_documents.append(
                    {
                        "asset_id": f"runtime_document_{idx}",
                        "filename": filename,
                        "source_url": str(parsed.get("source_url") or item.get("url") or item.get("local_path") or "").strip(),
                        "object_path": resolved_object_path,
                        "signed_url": str(item.get("signed_url") or "").strip(),
                        "content_type": str(item.get("content_type") or "").strip(),
                        "parser": str(parsed.get("parser") or "runtime_parse").strip(),
                        "parse_status": "failed",
                        "parse_error": raw_error,
                        "user_parse_error": display_error,
                        "markdown": "",
                        "profile": {},
                        "chunk_briefs": [],
                        "embedded_images": [],
                    }
                )
                continue

            markdown = str(parsed.get("markdown") or "").strip()
            embedded_images = [dict(x) for x in list(parsed.get("embedded_images") or []) if isinstance(x, dict)]
            structured_content = dict(parsed.get("structured_content") or {})
            parse_quality = dict(parsed.get("parse_quality") or {})
            context = await document_context_service.build_context(markdown=markdown, filename=filename, user_text=user_text)
            profile = dict(context.get("profile") or {})
            active_brief = str(profile.get("active_context_brief") or profile.get("summary") or "").strip()
            if active_brief:
                active_contexts.append(active_brief)
            parsed_documents.append(
                {
                    "asset_id": f"runtime_document_{idx}",
                    "filename": filename,
                    "source_url": str(parsed.get("source_url") or item.get("url") or item.get("local_path") or "").strip(),
                    "object_path": resolved_object_path,
                    "signed_url": str(item.get("signed_url") or "").strip(),
                    "content_type": str(item.get("content_type") or "").strip(),
                    "parser": str(parsed.get("parser") or "runtime_parse").strip(),
                    "parse_status": "parsed",
                    "parse_error": "",
                    "markdown": markdown,
                    "markdown_chars": int(context.get("markdown_chars") or len(markdown)),
                    "inline_markdown": str(context.get("inline_markdown") or "").strip(),
                    "inline_mode": str(context.get("inline_mode") or "summary_only").strip(),
                    "profile": profile,
                    "chunk_briefs": list(context.get("chunk_briefs") or []),
                    "chunk_count": int(context.get("chunk_count") or 0),
                    "embedded_images": embedded_images,
                    "structured_content": structured_content,
                    "parse_quality": parse_quality,
                }
            )

        successful = [item for item in parsed_documents if str(item.get("parse_status") or "") == "parsed"]
        failed = [item for item in parsed_documents if str(item.get("parse_status") or "") != "parsed"]
        logger.info(
            "runtime_parse_documents_finished node_id=%s parsed=%s failed=%s markdown_chars=%s errors=%s",
            str(getattr(node, "node_id", "") or ""),
            len(successful),
            len(failed),
            [int(item.get("markdown_chars") or len(str(item.get("markdown") or ""))) for item in successful[:6]],
            [str(item.get("parse_error") or "")[:160] for item in failed[:6]],
        )
        if successful:
            active_document_context = "\n".join(active_contexts[:3]).strip()
        else:
            active_document_context = "\n".join(
                f"- 文件《{str(item.get('filename') or item.get('asset_id') or 'document').strip()}》解析失败；错误：{str(item.get('user_parse_error') or item.get('parse_error') or '文件解析失败').strip()}"
                for item in failed[:6]
            ).strip()
        active_document_markdown = str((successful[0] or {}).get("markdown") or "").strip() if successful else ""
        documents = {
            "enabled": True,
            "count": len(parsed_documents),
            "parsed_documents": parsed_documents,
            "active_document_context": active_document_context,
            "active_document_markdown": active_document_markdown,
            "source": "runtime_graph_parse",
        }
        output_spec["documents"] = documents
        if active_document_context:
            output_spec["active_document_context"] = active_document_context
        if active_document_markdown:
            output_spec["active_document_markdown"] = active_document_markdown
        embedded_assets: List[Dict[str, Any]] = []
        for item in successful:
            embedded_assets.extend(
                build_embedded_document_image_assets(
                    embedded_images=[dict(x) for x in list(item.get("embedded_images") or []) if isinstance(x, dict)],
                    source_document_id=str(item.get("asset_id") or item.get("filename") or "").strip(),
                )
            )
        if embedded_assets:
            multimodal = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
            existing_assets = [dict(x) for x in list(multimodal.get("uploaded_assets") or []) if isinstance(x, dict)]
            merged_assets = self._merge_uploaded_assets(existing_assets, embedded_assets)
            multimodal = dict(multimodal)
            multimodal["enabled"] = True
            multimodal["uploaded_assets"] = merged_assets
            multimodal["embedded_document_image_count"] = len(embedded_assets)
            multimodal["artifact_images"] = [
                str(item.get("path") or "").strip()
                for item in merged_assets
                if str(item.get("path") or "").strip()
            ]
            multimodal["artifact_image_urls"] = list(multimodal["artifact_images"])
            multimodal["source"] = str(multimodal.get("source") or "runtime_graph_parse")
            output_spec["multimodal"] = multimodal
        return {
            "parsed_documents": parsed_documents,
            "documents": documents,
            "active_document_context": active_document_context,
            "active_document_markdown": active_document_markdown,
        }

    async def extract_resources(
        self,
        *,
        node: Any,
        output_spec: Dict[str, Any],
        user_text: str,
    ) -> Dict[str, Any]:
        requested = self._resource_types_from_node(node)
        existing_payload = self._hydrate_existing_documents(output_spec=output_spec)
        parsed_documents = [
            item for item in list(existing_payload.get("parsed_documents") or [])
            if isinstance(item, dict) and str(item.get("parse_status") or "") == "parsed"
        ]
        if not parsed_documents and any(self._looks_like_document(item) for item in self._collect_source_files(node=node, output_spec=output_spec)):
            parsed_payload = await self.parse_documents(node=node, output_spec=output_spec, user_text=user_text)
            parsed_documents = [
                item for item in list(parsed_payload.get("parsed_documents") or [])
                if isinstance(item, dict) and str(item.get("parse_status") or "") == "parsed"
            ]

        payload = self._payload_from_inputs(node=node, output_spec=output_spec)
        images: List[Dict[str, Any]] = []
        if "images" in requested:
            images.extend(self._collect_uploaded_asset_images(output_spec=output_spec, payload=payload))

        urls: List[Dict[str, Any]] = []
        if "urls" in requested:
            urls.extend(self._extract_urls_from_value(user_text, source="user_request"))
            for doc in parsed_documents:
                for item in self._extract_urls_from_text(str(doc.get("markdown") or "")):
                    item["source_document_id"] = str(doc.get("asset_id") or doc.get("filename") or "").strip()
                    urls.append(item)
            for key in ("urls", "links", "artifact_image_urls"):
                raw = payload.get(key)
                if isinstance(raw, list):
                    for value in raw:
                        text = str(value.get("url") if isinstance(value, dict) else value or "").strip()
                        if text.startswith(("http://", "https://")):
                            urls.append({"url": text, "source": f"upstream_{key}"})
            for key in (
                "source_material",
                "research_bundle",
                "collected_pages",
                "results",
                "image_facts",
                "vision_summary",
                "multimodal",
                "resources",
                "resource_bundle",
                "predecessor_artifacts",
            ):
                if key in payload:
                    urls.extend(self._extract_urls_from_value(payload.get(key), source=f"upstream_{key}"))

        attachments: List[Dict[str, Any]] = []
        if "attachments" in requested:
            for item in self._collect_source_files(node=node, output_spec=output_spec):
                if self._looks_like_document(item):
                    attachments.append({**item, "source": "runtime_source_file"})
            for doc in parsed_documents:
                attachments.append(
                    {
                        "filename": str(doc.get("filename") or "").strip(),
                        "object_path": str(doc.get("object_path") or "").strip(),
                        "signed_url": str(doc.get("signed_url") or "").strip(),
                        "source_url": str(doc.get("source_url") or "").strip(),
                        "content_type": str(doc.get("content_type") or "").strip(),
                        "source": "parsed_document",
                    }
                )

        images = self._dedupe_dicts(images, ["object_path", "signed_url", "url", "local_path", "filename"])
        urls = self._dedupe_dicts(urls, ["url"])
        attachments = self._dedupe_dicts(attachments, ["object_path", "signed_url", "source_url", "local_path", "filename"])
        resource_bundle = {
            "requested_types": requested,
            "images": images if "images" in requested else [],
            "urls": urls if "urls" in requested else [],
            "attachments": attachments if "attachments" in requested else [],
            "resource_counts": {
                "images": len(images) if "images" in requested else 0,
                "urls": len(urls) if "urls" in requested else 0,
                "attachments": len(attachments) if "attachments" in requested else 0,
            },
            "source": "runtime_graph_parse",
        }
        output_spec["resources"] = resource_bundle
        return {
            "resource_bundle": resource_bundle,
            "resources": resource_bundle,
            "images": resource_bundle["images"],
            "urls": resource_bundle["urls"],
            "attachments": resource_bundle["attachments"],
            "resource_counts": resource_bundle["resource_counts"],
        }

    @staticmethod
    def _local_image_to_data_url(item: Dict[str, Any]) -> Dict[str, Any]:
        local_path = str(item.get("local_path") or "").strip()
        if not local_path:
            return item
        path = Path(local_path)
        if not path.exists() or not path.is_file():
            return item
        content_type = str(item.get("content_type") or mimetypes.guess_type(str(path))[0] or "image/png").strip()
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        out = dict(item)
        out["url"] = f"data:{content_type};base64,{encoded}"
        out.setdefault("filename", path.name)
        out["content_type"] = content_type
        return out

    async def extract_image_facts(
        self,
        *,
        node: Any,
        output_spec: Dict[str, Any],
        user_text: str,
    ) -> Dict[str, Any]:
        payload = self._payload_from_inputs(node=node, output_spec=output_spec)
        image_candidates = [
            item for item in self._collect_source_files(node=node, output_spec=output_spec)
            if self._looks_like_image(item)
        ]
        image_candidates.extend(self._collect_uploaded_asset_images(output_spec=output_spec, payload=payload))
        image_candidates = self._dedupe_dicts(image_candidates, ["object_path", "signed_url", "url", "local_path", "filename"])
        images = [self._local_image_to_data_url(item) for item in image_candidates]
        if not images:
            existing = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
            uploaded_assets = list((existing or {}).get("uploaded_assets") or []) if isinstance(existing, dict) else []
            return {
                "vision_summary": str((existing or {}).get("vision_summary") or "").strip(),
                "image_facts": dict((existing or {}).get("image_facts") or {}) if isinstance((existing or {}).get("image_facts"), dict) else {},
                "uploaded_assets": uploaded_assets,
                "multimodal": dict(existing) if isinstance(existing, dict) else {},
                "image_count": int((existing or {}).get("embedded_document_image_count") or len(uploaded_assets) or 0),
                "skipped": True,
                "skip_reason": "no_runtime_image_artifacts",
            }
        compact_images = []
        for item in images[:8]:
            raw_url = str(item.get("url") or "").strip()
            compact_images.append(
                {
                    "filename": str(item.get("filename") or "").strip(),
                    "object_path": str(item.get("object_path") or "").strip(),
                    "signed_url": str(item.get("signed_url") or "").strip(),
                    "url": "" if raw_url.startswith("data:") else raw_url,
                    "local_path": str(item.get("local_path") or "").strip(),
                    "content_type": str(item.get("content_type") or "").strip(),
                    "size": item.get("size"),
                }
            )

        vision_payload = await vision_service.describe_images_with_facts(user_text=user_text, images=images, output_spec=output_spec)
        vision_summary = str(vision_payload.get("summary") or "").strip()
        image_facts = vision_payload.get("facts") if isinstance(vision_payload.get("facts"), dict) else {}
        uploaded_assets = build_uploaded_image_assets(images=images, image_facts=image_facts or {})
        for idx, asset in enumerate(uploaded_assets):
            if not isinstance(asset, dict):
                continue
            local_path = str((images[idx] if idx < len(images) else {}).get("local_path") or "").strip()
            if local_path and str(asset.get("path") or "").startswith("data:"):
                asset["path"] = local_path
                asset["signed_url"] = ""
        multimodal = {
            "enabled": True,
            "image_count": len(images),
            "vision_summary": vision_summary,
            "vision_summary_chars": len(str(vision_summary or "")),
            "image_facts": image_facts or {},
            "images": compact_images,
            "uploaded_assets": uploaded_assets,
            "artifact_images": [str(item.get("path") or "").strip() for item in uploaded_assets if str(item.get("path") or "").strip()],
            "source": "runtime_graph_parse",
        }
        multimodal["artifact_image_urls"] = list(multimodal["artifact_images"])
        output_spec["multimodal"] = multimodal
        return {
            "vision_summary": vision_summary,
            "image_facts": image_facts or {},
            "uploaded_assets": uploaded_assets,
            "multimodal": multimodal,
        }


runtime_parse_service = RuntimeParseService()
