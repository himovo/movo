from __future__ import annotations
from app.infrastructure.observability.config import log_print

import os
import re
from typing import Any, Dict, Optional

from app.tools.pdf import render_pdf_from_markdown
from app.utils.markdown_assets import render_markdown_assets
from app.utils.oss_uploader import AliyunOSSUploader
from app.utils.i18n import get as i18n_get
from app.services.document_title import extract_reliable_markdown_h1


def _extract_title(markdown: str) -> str:
    candidate = extract_reliable_markdown_h1(markdown)
    if candidate:
        return candidate
    # 正确使用 Unicode 范围匹配中日韩字符（\u 在 raw string 里仍会被正则解析为 Unicode）
    language = "zh" if re.search(r"[\u4e00-\u9fff]", markdown or "") else "en"
    return i18n_get("report_title_default", language)


def _safe_filename(title: str, ext: str) -> str:
    cleaned = re.sub(r"[\\/]+", "_", title).strip() or "report"
    cleaned = re.sub(r"\s+", "_", cleaned)
    if not cleaned.endswith(ext):
        cleaned = f"{cleaned}{ext}"
    return cleaned


class DocumentService:
    async def render(
        self,
        markdown: str,
        *,
        user_id: str,
        format: str,
        filename: Optional[str] = None,
        title: Optional[str] = None,
        skip_cover: bool = False,
        skip_toc: bool = False,
    ) -> Dict[str, Any]:
        title = title or _extract_title(markdown)
        format = format.lower()

        if format == "pdf":
            filename = filename or _safe_filename(title, ".pdf")
            public_url = await render_pdf_from_markdown(markdown, user_id, filename)
            uploader = AliyunOSSUploader()
            object_path = uploader.object_path_from_url(public_url)
            signed_url = uploader.sign_url(object_path)
            return {
                "type": "pdf",
                "url": signed_url,
                "filename": filename,
                "title": title,
                "object_path": object_path,
            }

        if format == "docx":
            filename = filename or _safe_filename(title, ".docx")
            rendered_markdown = await render_markdown_assets(markdown, user_id)
            try:
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                debug_dir = os.path.join(base_dir, "static", "docx_debug")
                os.makedirs(debug_dir, exist_ok=True)
                debug_path = os.path.join(debug_dir, f"{user_id}_last_rendered.md")
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(rendered_markdown)
                log_print(f"[docx] debug_markdown_saved path={debug_path}", flush=True)
            except Exception:
                pass
            log_print(
                "[docx] rendered markdown",
                "orig_len=",
                len(markdown),
                "rendered_len=",
                len(rendered_markdown),
                "images=",
                rendered_markdown.count("!["), 
            )
            from app.skills_specs.docx.markdown_to_docx import render_from_markdown
            docx_result = render_from_markdown(
                rendered_markdown,
                filename,
                return_metadata=True,
                cover_title=title,
                skip_cover=skip_cover,
                skip_toc=skip_toc,
            )
            if isinstance(docx_result, dict):
                file_path = str(docx_result.get("file_path") or "")
                render_stats = dict(docx_result.get("render_stats") or {})
            else:
                file_path = str(docx_result or "")
                render_stats = {}
            uploader = AliyunOSSUploader()
            _, object_path = uploader.upload_file_with_path(file_path, user_id)
            signed_url = uploader.sign_url(object_path)
            return {
                "type": "docx",
                "url": signed_url,
                "filename": filename,
                "title": title,
                "object_path": object_path,
                "render_stats": render_stats,
            }

        if format == "md" or format == "markdown":
            filename = filename or _safe_filename(title, ".md")
            uploader = AliyunOSSUploader()
            
            # If a file path is provided, upload it directly; otherwise create a temp file.
            file_path = None
            if hasattr(self, '_temp_file_path'):
                file_path = self._temp_file_path
            
            if file_path and os.path.exists(file_path):
                _, object_path = uploader.upload_file_with_path(file_path, user_id)
            else:
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as tmp:
                    tmp.write(markdown)
                    tmp_path = tmp.name
                _, object_path = uploader.upload_file_with_path(tmp_path, user_id)
                os.unlink(tmp_path)
            
            signed_url = uploader.sign_url(object_path)
            return {
                "type": "markdown",
                "url": signed_url,
                "filename": filename,
                "title": title,
                "object_path": object_path,
            }

        raise ValueError(f"Unsupported document format: {format}")

    async def render_presentation_pptx(
        self,
        *,
        user_id: str,
        blueprint_object_path: str,
        filename: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Load a FreeformDeckBlueprint from the configured storage backend and compile to PPTX."""
        import json
        from app.services.presentation.contracts import FreeformDeckBlueprint
        from app.services.presentation.pptx_compiler import PptxCompiler

        uploader = AliyunOSSUploader()
        blueprint_dict = json.loads(uploader.read_bytes(blueprint_object_path).decode("utf-8"))

        blueprint = FreeformDeckBlueprint.model_validate(blueprint_dict)
        compiler = PptxCompiler()
        return await compiler.compile_and_upload(
            blueprint=blueprint,
            user_id=user_id,
            filename=filename or "",
        )


document_service = DocumentService()
