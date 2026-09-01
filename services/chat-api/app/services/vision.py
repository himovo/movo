from __future__ import annotations
from app.infrastructure.observability.config import log_print

import base64
import re
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.llm.configured_models import build_llm_client_from_config, get_configured_model_context
from app.llm.factory import get_openai_compatible_client
from app.llm.types import Message, Role
from app.utils.oss_uploader import AliyunOSSUploader


class VisionService:
    def __init__(self) -> None:
        settings = get_settings()
        self._enabled = bool(settings.USE_MULTIMODAL)
        self._model = settings.VISION_MODEL
        self._enable_thinking = bool(settings.VISION_ENABLE_THINKING)
        self._thinking_budget = int(settings.VISION_THINKING_BUDGET or 81920)

    def _client(self, output_spec: Optional[Dict[str, Any]] = None):
        configured_model = get_configured_model_context()
        if configured_model:
            return build_llm_client_from_config(
                configured_model,
                streaming=False,
                intent="vision",
                stage="vision",
                output_spec=output_spec or {},
            )

        # Compatibility path for deployments that still configure the legacy
        # environment variables instead of tenant-scoped models.
        settings = get_settings()
        api_key = settings.DASHSCOPE_API_KEY or settings.QWEN_API_KEY or settings.OPENAI_API_KEY
        return get_openai_compatible_client(
            api_key=api_key,
            base_url=settings.VISION_BASE_URL,
            model_name=self._model,
            streaming=False,
            intent="vision",
            stage="vision",
            output_spec=output_spec or {},
        )

    def _resolve_image_url(self, image: Dict[str, Any]) -> Optional[str]:
        object_path = image.get("object_path")
        if object_path:
            try:
                uploader = AliyunOSSUploader()
                if uploader.storage_backend == "local":
                    data = uploader.read_bytes(str(object_path))
                    if data:
                        mime = uploader.guess_content_type(str(object_path))
                        encoded = base64.b64encode(data).decode("ascii")
                        return f"data:{mime};base64,{encoded}"
                return uploader.sign_url(str(object_path))
            except Exception:
                pass
        url = image.get("url")
        return str(url) if url else None

    async def describe_images(
        self,
        *,
        user_text: str,
        images: List[Dict[str, Any]],
        max_images: int = 6,
        output_spec: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not self._enabled:
            return ""
        if not images:
            return ""

        parts: List[Dict[str, Any]] = []
        for img in images[:max_images]:
            resolved = self._resolve_image_url(img)
            if not resolved:
                continue
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": resolved},
                }
            )
        if not parts:
            return ""

        parts.append(
            {
                "type": "text",
                "text": (
                    "You are a multimodal factual extractor. Extract objective, image-grounded facts from the provided images.\n"
                    "If information is unclear, explicitly write: 'Not identified from image'.\n"
                    "Return concise Markdown and strictly follow this structure:\n"
                    "## Image Facts\n"
                    "### Image 1\n"
                    "- Page/area:\n"
                    "- Visible fields and text labels:\n"
                    "- Visible buttons and controls:\n"
                    "- Visible status/toggles/tags:\n"
                    "- Visible flow relationship (or 'Not identified from image'):\n"
                    "### Image 2 ... (continue for all images)\n"
                    "## Cross-image Consistent Facts\n"
                    "- ...\n"
                    "## Subject Candidates\n"
                    "- Candidate 1: the dominant product/system/workflow/topic shown across images\n"
                    "- Candidate 2: optional secondary candidate if ambiguity remains\n"
                    "## UI Terms and Controls\n"
                    "- terms, buttons, toggles, field labels, statuses seen in the UI\n"
                    "## Not Identified or Uncertain\n"
                    "- ...\n\n"
                    f"Original user context (for terminology alignment only; do not infer image facts from this text): {user_text}"
                ),
            }
        )

        extra_body: Dict[str, Any] = {}
        if self._enable_thinking:
            extra_body = {
                "enable_thinking": True,
                "thinking_budget": self._thinking_budget,
            }
        try:
            kwargs: Dict[str, Any] = {}
            if extra_body:
                kwargs["extra_body"] = extra_body
            resp = await self._client(output_spec).ainvoke(
                [Message(role=Role.USER, content=parts)],
                **kwargs,
            )
            return str(resp.message.content or "").strip()
        except Exception as exc:
            log_print(f"[vision] describe_images failed: {exc}", flush=True)
            return ""

    async def describe_images_structured(
        self,
        *,
        user_text: str,
        images: List[Dict[str, Any]],
        max_images: int = 6,
        output_spec: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        summary = await self.describe_images(
            user_text=user_text,
            images=images,
            max_images=max_images,
            output_spec=output_spec,
        )
        return self._parse_image_facts(summary, len(images))

    async def describe_images_with_facts(
        self,
        *,
        user_text: str,
        images: List[Dict[str, Any]],
        max_images: int = 6,
        output_spec: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        summary = await self.describe_images(
            user_text=user_text,
            images=images,
            max_images=max_images,
            output_spec=output_spec,
        )
        return {
            "summary": summary,
            "facts": self._parse_image_facts(summary, len(images)),
        }

    def _parse_image_facts(self, summary: str, image_count: int) -> Dict[str, Any]:
        text = (summary or "").strip()
        result: Dict[str, Any] = {
            "images": [],
            "entities": [],
            "subject_candidates": [],
            "cross_image_facts": [],
            "ui_terms": [],
            "fields": [],
            "flows": [],
            "buttons": [],
            "page_titles": [],
            "uncertain": [],
            "raw_summary": text,
        }
        if not text:
            for idx in range(image_count):
                result["images"].append(
                    {
                        "image_index": idx + 1,
                        "page_area": "Not identified from image",
                        "visible_fields": [],
                        "controls": [],
                        "status_tags": [],
                        "flow_relationship": "Not identified from image",
                    }
                )
            return result

        image_facts_block = self._extract_markdown_section(text, "Image Facts")
        image_sections = re.split(r"(?m)^###\s*Image\s+\d+\s*$", image_facts_block)
        headers = re.findall(r"(?m)^###\s*Image\s+(\d+)\s*$", image_facts_block)
        for sec_idx, section in enumerate(image_sections[1:], start=0):
            image_no = int(headers[sec_idx]) if sec_idx < len(headers) else sec_idx + 1
            facts = {
                "image_index": image_no,
                "page_area": "",
                "visible_fields": [],
                "controls": [],
                "status_tags": [],
                "flow_relationship": "",
            }
            for raw_line in section.splitlines():
                line = raw_line.strip().lstrip("-").strip()
                if not line:
                    continue
                low = line.lower()
                if "page/area" in low or "页面" in line:
                    facts["page_area"] = line.split(":", 1)[-1].strip()
                elif "visible fields" in low or "字段" in line or "label" in low:
                    value = line.split(":", 1)[-1].strip()
                    if value:
                        facts["visible_fields"].append(value)
                        result["fields"].append(value)
                elif "buttons" in low or "controls" in low or "按钮" in line:
                    value = line.split(":", 1)[-1].strip()
                    if value:
                        facts["controls"].append(value)
                        result["buttons"].append(value)
                elif "status" in low or "tag" in low or "状态" in line:
                    value = line.split(":", 1)[-1].strip()
                    if value:
                        facts["status_tags"].append(value)
                elif "flow relationship" in low or "流程" in line:
                    value = line.split(":", 1)[-1].strip()
                    facts["flow_relationship"] = value
                    if value and "not identified" not in value.lower():
                        result["flows"].append(value)
            result["images"].append(facts)
            if facts.get("page_area"):
                result["page_titles"].append(facts["page_area"])

        result["cross_image_facts"] = self._extract_markdown_bullets(text, "Cross-image Consistent Facts")
        result["subject_candidates"] = self._extract_markdown_bullets(text, "Subject Candidates")
        result["ui_terms"] = self._extract_markdown_bullets(text, "UI Terms and Controls")
        result["uncertain"] = self._extract_markdown_bullets(text, "Not Identified or Uncertain")
        if not result["subject_candidates"]:
            result["subject_candidates"] = self._derive_subject_candidates(result)
        result["entities"] = list(result["subject_candidates"])

        # Dedupe long lists
        for key in ("subject_candidates", "cross_image_facts", "ui_terms", "fields", "flows", "buttons", "page_titles", "uncertain"):
            seen = set()
            unique = []
            for item in result.get(key) or []:
                item = str(item).strip()
                if not item or item in seen:
                    continue
                seen.add(item)
                unique.append(item)
            result[key] = unique

        return result

    @staticmethod
    def _extract_markdown_section(text: str, heading: str) -> str:
        if not text:
            return ""
        pattern = rf"(?ms)^##\s*{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s|\Z)"
        match = re.search(pattern, text)
        return str(match.group(1) or "") if match else ""

    @staticmethod
    def _extract_markdown_bullets(text: str, heading: str) -> List[str]:
        if not text:
            return []
        pattern = rf"(?ms)^##\s*{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s|\Z)"
        match = re.search(pattern, text)
        if not match:
            return []
        items: List[str] = []
        for raw_line in match.group(1).splitlines():
            line = raw_line.strip()
            if not line.startswith("-"):
                continue
            value = line.lstrip("-").strip()
            if ":" in value:
                _, rhs = value.split(":", 1)
                value = rhs.strip() or value
            if value and "not identified" not in value.lower():
                items.append(value)
        return items

    @staticmethod
    def _derive_subject_candidates(parsed: Dict[str, Any]) -> List[str]:
        candidates: List[str] = []
        for value in list(parsed.get("page_titles") or []):
            token = str(value or "").strip()
            if token and "not identified" not in token.lower() and token not in candidates:
                candidates.append(token)
        for item in list(parsed.get("images") or []):
            if not isinstance(item, dict):
                continue
            page_area = str(item.get("page_area") or "").strip()
            if page_area and "not identified" not in page_area.lower() and page_area not in candidates:
                candidates.append(page_area)
        for value in list(parsed.get("flows") or []):
            token = str(value or "").strip()
            if token and "not identified" not in token.lower() and token not in candidates:
                candidates.append(token)
        return candidates[:8]


vision_service = VisionService()
