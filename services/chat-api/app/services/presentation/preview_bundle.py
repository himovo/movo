from __future__ import annotations

import json
import logging

from app.services.presentation.contracts import (
    FrontendPresentationDocument,
    HtmlCompileResult,
    PresentationPreviewBundle,
    PreviewArtifactRef,
)
from app.utils.oss_uploader import AliyunOSSUploader

logger = logging.getLogger(__name__)


class PreviewBundleBuilder:
    def _empty_ref(self, *, filename: str) -> PreviewArtifactRef:
        return PreviewArtifactRef(url="", object_path="", filename=filename)

    def _safe_upload_ref(
        self,
        *,
        uploader: AliyunOSSUploader,
        content: bytes,
        user_id: str,
        file_name: str,
        content_type: str,
        failure_messages: list[str],
    ) -> PreviewArtifactRef:
        try:
            _url, object_path = uploader.upload_bytes_with_path(
                content,
                user_id=user_id,
                file_name=file_name,
                content_type=content_type,
            )
            return PreviewArtifactRef(
                url=uploader.sign_url(object_path),
                object_path=object_path,
                filename=file_name,
            )
        except Exception as exc:
            failure_messages.append(f"{file_name}: {exc}")
            logger.warning("presentation_preview_upload_failed file=%s error=%s", file_name, exc, exc_info=True)
            return self._empty_ref(filename=file_name)

    def build(
        self,
        *,
        blueprint: dict,
        compile_result: HtmlCompileResult,
        user_id: str,
        task_id: str,
    ) -> tuple[PresentationPreviewBundle, FrontendPresentationDocument]:
        uploader = AliyunOSSUploader()
        safe_task_id = str(task_id or blueprint.get("deck_id") or "presentation").strip() or "presentation"
        safe_user_id = str(user_id or "anonymous").strip() or "anonymous"
        failures: list[str] = []

        html_ref = self._safe_upload_ref(
            uploader=uploader,
            content=compile_result.html.encode("utf-8"),
            user_id=safe_user_id,
            file_name=f"presentation_preview_v5_{safe_task_id}.html",
            content_type="text/html; charset=utf-8",
            failure_messages=failures,
        )
        blueprint_ref = self._safe_upload_ref(
            uploader=uploader,
            content=json.dumps(blueprint, ensure_ascii=False, indent=2).encode("utf-8"),
            user_id=safe_user_id,
            file_name=f"presentation_blueprint_v5_{safe_task_id}.json",
            content_type="application/json; charset=utf-8",
            failure_messages=failures,
        )
        bundle = PresentationPreviewBundle(
            pipeline_version="current",
            deck_ir=blueprint,
            page_ir_refs=[
                {
                    "page_id": page.get("page_id"),
                    "page_index": idx + 1,
                    "page_ir_state": "freeform_blueprint",
                }
                for idx, page in enumerate(list(blueprint.get("pages") or []))
            ],
            html_preview=html_ref,
            deck_ir_artifact=blueprint_ref,
            slide_count=int(compile_result.slide_count or 0),
            preview_metadata={
                **dict(compile_result.metadata or {}),
                "delivery_mode": "artifact_preview" if html_ref.url else "artifact_preview_degraded",
                "preview_upload_failed": bool(failures),
                "preview_upload_failures": list(failures),
                "blueprint_artifact_path": blueprint_ref.object_path,
            },
        )
        document = FrontendPresentationDocument(
            title="PPT HTML 预览",
            url=html_ref.url,
            object_path=html_ref.object_path,
            filename=html_ref.filename,
            bundle=bundle.model_dump(),
            summary={
                "planning_version": "current",
                "slide_count": bundle.slide_count,
                "preview_upload_failed": bool(failures),
                "preview_upload_failures": list(failures),
            },
        )
        logger.info(
            "presentation_preview_bundle_ready deck_id=%s slide_count=%s html_uploaded=%s blueprint_uploaded=%s upload_failed=%s",
            str(blueprint.get("deck_id") or "").strip(),
            int(bundle.slide_count or 0),
            bool(html_ref.url),
            bool(blueprint_ref.url),
            bool(failures),
        )
        return bundle, document
