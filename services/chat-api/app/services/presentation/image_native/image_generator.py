from __future__ import annotations

import logging
import uuid
from io import BytesIO
from typing import Any, Dict, Optional

from PIL import Image

from app.services.image_generation import generate_image
from app.utils.oss_uploader import AliyunOSSUploader

logger = logging.getLogger(__name__)


class FullSlideImageGenerator:
    """Generate and upload complete slide visuals with gpt-image-2."""

    async def generate(
        self,
        *,
        prompt: str,
        user_id: str,
        page_id: str,
        log_context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        result = await generate_image(
            prompt=prompt,
            user_id=user_id,
            log_hook=lambda event, payload: self._log_image_event(event, payload, log_context or {}),
        )
        image_bytes = self._normalize_png(result.image_bytes)
        uploader = AliyunOSSUploader()
        _public, object_path = uploader.upload_bytes_with_path(
            image_bytes,
            user_id=str(user_id or "anonymous").strip() or "anonymous",
            file_name=f"presentation_image_native_{page_id}_{uuid.uuid4().hex[:10]}.png",
            content_type="image/png",
        )
        return {
            "url": uploader.sign_url(object_path),
            "object_path": object_path,
            "bytes": image_bytes,
            "response": result.response,
            "model_id": result.model_id,
            "model_name": result.model_name,
            "model_source": result.model_source,
        }

    @staticmethod
    def _normalize_png(image_bytes: bytes) -> bytes:
        with Image.open(BytesIO(image_bytes)) as img:
            rgb = img.convert("RGB")
            if rgb.size != (1600, 900):
                rgb = rgb.resize((1600, 900), Image.Resampling.LANCZOS)
            out = BytesIO()
            rgb.save(out, format="PNG")
            return out.getvalue()

    def _log_image_event(self, event: str, payload: Dict[str, Any], context: Dict[str, Any]) -> None:
        log_payload = {
            "event": f"presentation_image_native.{event}",
            "image_payload": payload,
            "context": context,
        }
        if event.endswith("response") and int(payload.get("status_code") or 0) >= 400:
            logger.warning("presentation_image_native_image_event", extra=log_payload)
        else:
            logger.info("presentation_image_native_image_event", extra=log_payload)


class ImageNativeAssetGenerator:
    """Generate no-text assets requested by visual semantic analysis."""

    async def generate_assets(
        self,
        *,
        analysis: Dict[str, Any],
        user_id: str,
        page_id: str,
        max_assets: int = 4,
    ) -> Dict[str, str]:
        assets = []
        for item in list((analysis or {}).get("image_assets") or []):
            if not isinstance(item, dict):
                continue
            asset_id = str(item.get("id") or "").strip()
            prompt = str(item.get("prompt") or "").strip()
            if asset_id and prompt:
                assets.append((asset_id, prompt))
            if len(assets) >= max_assets:
                break
        if not assets:
            return {}

        uploader = AliyunOSSUploader()
        out: Dict[str, str] = {}
        for asset_id, prompt in assets:
            try:
                result = await generate_image(prompt=prompt, user_id=user_id)
                image_bytes = self._normalize_asset_bytes(result.image_bytes)
                _public, object_path = uploader.upload_bytes_with_path(
                    image_bytes,
                    user_id=str(user_id or "anonymous").strip() or "anonymous",
                    file_name=f"presentation_image_native_asset_{page_id}_{asset_id}_{uuid.uuid4().hex[:8]}.png",
                    content_type="image/png",
                )
                out[asset_id] = uploader.sign_url(object_path)
            except Exception:
                logger.warning(
                    "presentation_image_native_asset_failed page_id=%s asset_id=%s",
                    page_id,
                    asset_id,
                    exc_info=True,
                )
        return out

    @staticmethod
    def _normalize_asset_bytes(image_bytes: bytes) -> bytes:
        with Image.open(BytesIO(image_bytes)) as img:
            rgb = img.convert("RGB")
            out = BytesIO()
            rgb.save(out, format="PNG")
            return out.getvalue()
