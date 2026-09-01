from __future__ import annotations
from app.infrastructure.observability.config import log_print

import asyncio
import json
import re
from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field

from app.llm.factory import get_llm_client
from app.llm.types import Message, Role
from app.llm.decision_turn import DecisionOutput, DecisionTurnSpec, invoke_structured_decision
from app.enterprise_capabilities.content.body_projection import (
    strip_inline_visual_suggestions,
    strip_unrenderable_markdown_images,
    strip_visual_or_production_clauses,
)
from app.enterprise_capabilities.content.planning.contracts import ContentPlanSpec
from app.enterprise_capabilities.content.publish_assembly.alt_text_generator import AltTextGenerator
from app.enterprise_capabilities.content.publish_assembly.contracts import GeneratedVisualAssetSpec, PublishAssemblySpec
from app.enterprise_capabilities.content.publish_assembly.section_locator import final_markdown_section_ranges, normalize_heading_token
from app.tools.infographic import generate_infographic_asset


class VisualSlotGenerationDecision(DecisionOutput):
    should_generate: bool = False
    reason: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class PublishAssembler:
    _MARKDOWN_IMAGE_RE = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<url>[^)]+)\)\s*$")

    @staticmethod
    def _is_renderable_image_url(value: str) -> bool:
        url = str(value or "").strip()
        if not url or any(ch in url for ch in (" ", "\n", "\r", "\t", "\"", "'")):
            return False
        if url.startswith(("http://", "https://")):
            return True
        return url.startswith(("/askai-api/api/files/", "/askai-api/files/", "/api/files/"))

    @staticmethod
    def _log(message: str) -> None:
        try:
            log_print(f"[publish_assembly] {message}", flush=True)
        except Exception:
            pass

    @staticmethod
    def _requests_pptx(output_spec: Dict[str, Any] | None) -> bool:
        spec = dict(output_spec or {})
        formats = spec.get("formats") or spec.get("requested_formats") or []
        if isinstance(formats, str):
            formats = [formats]
        for item in list(formats or []):
            if str(item or "").strip().lower() == "pptx":
                return True
        if str(spec.get("type") or "").strip().lower() in {"ppt", "pptx"}:
            return True
        return False

    @staticmethod
    def extract_body_markdown(
        final_markdown: str,
        *,
        removable_image_urls: List[str] | None = None,
    ) -> str:
        text = str(final_markdown or "")
        if not text.strip():
            return ""
        removable = {
            str(url or "").strip()
            for url in list(removable_image_urls or [])
            if PublishAssembler._is_renderable_image_url(str(url or "").strip())
        }
        lines = text.splitlines()
        kept: List[str] = []
        for line in lines:
            raw = str(line or "")
            stripped = raw.strip()
            match = PublishAssembler._MARKDOWN_IMAGE_RE.match(stripped)
            if match:
                url = str(match.group("url") or "").strip()
                if url in removable:
                    continue
            kept.append(raw)
        body = "\n".join(kept)
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        return body + ("\n" if body else "")

    @staticmethod
    def _strip_editorial_visual_lines(markdown: str) -> str:
        text = strip_unrenderable_markdown_images(strip_inline_visual_suggestions(str(markdown or "")))
        if not text.strip():
            return text
        lines = text.splitlines()
        kept: List[str] = []
        skip_visual_block = False
        for line in lines:
            stripped = str(line or "").strip()
            if re.match(r"^[\[【(（]?\s*配图", stripped):
                skip_visual_block = True
                continue
            if skip_visual_block:
                if not stripped:
                    skip_visual_block = False
                    continue
                if re.match(r"^(主标题|副标题|画面元素|画面|图示目标|旁边标注|说明|文案)[:：]", stripped):
                    continue
                skip_visual_block = False
            kept.append(str(line or ""))
        cleaned = strip_unrenderable_markdown_images(strip_inline_visual_suggestions("\n".join(kept)))
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned + ("\n" if cleaned else "")

    @classmethod
    def _strip_unresolvable_asset_lines(cls, markdown: str) -> str:
        text = strip_unrenderable_markdown_images(str(markdown or ""))
        if not text.strip():
            return text
        kept: List[str] = []
        removed_image = False
        for raw in text.splitlines():
            stripped = str(raw or "").strip()
            if removed_image:
                if not stripped:
                    continue
                if stripped.startswith("*图注："):
                    removed_image = False
                    continue
                removed_image = False
            match = cls._MARKDOWN_IMAGE_RE.match(stripped)
            if match:
                url = str(match.group("url") or "").strip()
                if not cls._is_renderable_image_url(url) and not url.startswith("data:"):
                    removed_image = True
                    continue
            kept.append(str(raw or ""))
        cleaned = "\n".join(kept)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned + ("\n" if cleaned else "")

    async def assemble(
        self,
        *,
        body_markdown: str,
        content_plan: Dict[str, Any],
        user_query: str,
        language: str,
        user_id: str,
        output_spec: Dict[str, Any] | None = None,
        existing_assets: List[Dict[str, Any]] | None = None,
    ) -> PublishAssemblySpec:
        text = str(body_markdown or "").strip()
        if not text:
            return PublishAssemblySpec(body_markdown="", final_markdown="")
        if self._requests_pptx(output_spec):
            return PublishAssemblySpec(body_markdown=text, final_markdown=text)
        text = self._strip_editorial_visual_lines(text)
        text = self._strip_unresolvable_asset_lines(text)

        plan = ContentPlanSpec.model_validate(dict(content_plan or {}) or {})
        assets: List[GeneratedVisualAssetSpec] = []
        missing_reasons: List[str] = []
        reusable_assets = {
            str(item.get("slot_id") or "").strip(): dict(item)
            for item in list(existing_assets or [])
            if isinstance(item, dict) and str(item.get("slot_id") or "").strip()
        }

        for idx, slot in enumerate(list(plan.visual_slots or []), start=1):
            slot_id = str(slot.slot_id or f"v{idx}")
            section_title = self._section_title(plan=plan, section_id=str(slot.anchor_section_id or ""))

            # Generate reader-friendly alt text with systematic fallback
            alt_text = AltTextGenerator.generate(
                section_title=section_title,
                slot_role=str(slot.role or ""),
                slot_description=str(slot.description or ""),
                fallback_index=idx,
            )

            reused = reusable_assets.get(slot_id) or {}
            reused_url = str(reused.get("image_url") or "").strip()
            reused_ok = self._is_renderable_image_url(reused_url)
            if reused_ok:
                asset = GeneratedVisualAssetSpec(
                    slot_id=slot_id,
                    role=str(slot.role or "visual"),
                    anchor_section_id=str(slot.anchor_section_id or ""),
                    alt_text=alt_text[:120],
                    image_url=reused_url,
                    status="generated",
                    reason="reused_existing_asset",
                )
                assets.append(asset)
                self._log(
                    "slot reused | slot=%s role=%s section=%s"
                    % (asset.slot_id, asset.role or "visual", section_title or "-")
                )
                continue
            url, reason = await self._generate_for_slot(
                user_query=user_query,
                role=str(slot.role or "visual"),
                section_title=section_title,
                description=str(slot.description or ""),
                language=language,
                user_id=user_id,
            )
            status = "generated" if url else "missing"
            asset = GeneratedVisualAssetSpec(
                slot_id=slot_id,
                role=str(slot.role or "visual"),
                anchor_section_id=str(slot.anchor_section_id or ""),
                alt_text=alt_text[:120],
                image_url=url,
                status=status,
                reason=reason,
            )
            assets.append(asset)
            if url:
                self._log(
                    "slot generated | slot=%s role=%s section=%s reason=%s"
                    % (asset.slot_id, asset.role or "visual", section_title or "-", reason)
                )
                await asyncio.sleep(0.8)
            else:
                self._log(
                    "slot missing | slot=%s role=%s section=%s reason=%s"
                    % (asset.slot_id, asset.role or "visual", section_title or "-", reason)
                )
                missing_reasons.append(f"{asset.slot_id}:{reason}")

        final_markdown = self._inline_assets(
            body_markdown=text,
            plan=plan,
            assets=assets,
        )
        missing = [item.slot_id for item in assets if item.status != "generated"]
        return PublishAssemblySpec(
            body_markdown=text,
            final_markdown=final_markdown,
            generated_assets=assets,
            missing_slot_ids=missing,
            missing_slot_reasons=missing_reasons,
        )

    @staticmethod
    def _section_title(*, plan: ContentPlanSpec, section_id: str) -> str:
        sid = str(section_id or "").strip()
        for sec in list(plan.sections or []):
            if str(sec.section_id or "").strip() == sid:
                return strip_visual_or_production_clauses(str(sec.title or "").strip())
        return ""

    async def _generate_for_slot(
        self,
        *,
        user_query: str,
        role: str,
        section_title: str,
        description: str,
        language: str,
        user_id: str,
    ) -> Tuple[str, str]:
        skip_reason = self._weak_visual_prompt_skip_reason(
            user_query=user_query,
            role=role,
            section_title=section_title,
            description=description,
        )
        if skip_reason:
            self._log(
                "slot skipped | role=%s section=%s reason=%s"
                % (role or "visual", section_title or "-", skip_reason)
            )
            return "", skip_reason
        if self._visual_slot_needs_llm_review(
            user_query=user_query,
            role=role,
            section_title=section_title,
            description=description,
        ):
            should_generate, reason = await self._judge_visual_slot_generation(
                user_query=user_query,
                role=role,
                section_title=section_title,
                description=description,
                language=language,
            )
            if not should_generate:
                self._log(
                    "slot skipped | role=%s section=%s reason=%s"
                    % (role or "visual", section_title or "-", reason or "llm_visual_slot_rejected")
                )
                return "", reason or "llm_visual_slot_rejected"
        attempts = self._build_retry_attempts(
            user_query=user_query,
            role=role,
            section_title=section_title,
            description=description,
            language=language,
        )
        last_error = "generate_failed"
        for idx, attempt in enumerate(attempts, start=1):
            prompt = str(attempt.get("prompt") or "").strip()
            size = str(attempt.get("size") or "1664*928").strip()
            label = str(attempt.get("label") or f"attempt_{idx}")
            if not prompt:
                continue
            try:
                result = await generate_infographic_asset(
                    prompt=prompt,
                    user_id=str(user_id or "anonymous"),
                    size=size,
                )
                url = str(result.get("image_url") or "").strip()
                if self._is_renderable_image_url(url):
                    return url, label
                err = str(result.get("error") or "missing_image_url").strip()
                last_error = f"{label}:{err}"
                self._log(
                    "slot retry failed | attempt=%s role=%s section=%s size=%s error=%s"
                    % (label, role or "visual", section_title or "-", size, err)
                )
                if "429" in err:
                    await asyncio.sleep(min(2.0 * idx, 8.0))
            except Exception as exc:
                last_error = f"{label}:{str(exc)[:120]}"
                self._log(
                    "slot retry exception | attempt=%s role=%s section=%s size=%s error=%s"
                    % (label, role or "visual", section_title or "-", size, str(exc)[:120])
                )
                if "429" in str(exc):
                    await asyncio.sleep(min(2.0 * idx, 8.0))
        return "", last_error

    def _build_retry_attempts(
        self,
        *,
        user_query: str,
        role: str,
        section_title: str,
        description: str,
        language: str,
    ) -> List[Dict[str, str]]:
        primary = self._build_slot_prompt(
            user_query=user_query,
            role=role,
            section_title=section_title,
            description=description,
            language=language,
        )
        fallback = self._build_fallback_prompt(
            user_query=user_query,
            role=role,
            section_title=section_title,
            language=language,
        )
        compact = self._build_compact_prompt(
            user_query=user_query,
            role=role,
            section_title=section_title,
            description=description,
            language=language,
        )
        return [
            {"label": "primary_wide", "prompt": primary, "size": "1664*928"},
            {"label": "primary_square", "prompt": primary, "size": "1328*1328"},
            {"label": "fallback_wide", "prompt": fallback, "size": "1664*928"},
            {"label": "fallback_square", "prompt": fallback, "size": "1328*1328"},
            {"label": "compact_wide", "prompt": compact, "size": "1664*928"},
            {"label": "compact_square", "prompt": compact, "size": "1328*1328"},
        ]

    @staticmethod
    def _build_slot_prompt(
        *,
        user_query: str,
        role: str,
        section_title: str,
        description: str,
        language: str,
    ) -> str:
        topic = strip_visual_or_production_clauses(section_title or role or user_query or "核心主题")
        focus = PublishAssembler._sanitize_visual_brief(section_title or role or "核心信息")
        detail = PublishAssembler._sanitize_visual_brief(description or "突出该段核心概念与关系")
        banned_tail = PublishAssembler._non_cta_visual_ban(role=role, section_title=section_title, language=language)
        return (
            f"Create a clear publishable infographic for: {topic}. "
            f"Visual role: {role}. Anchor section: {focus or 'general context'}. "
            f"Goal: {detail}. "
            "Use a clean information-design layout, readable labels, and no watermark. "
            "The visual must stay tightly grounded in the topic itself: show domain-specific entities, relationships, workflows, or scenes rather than generic futuristic AI decoration. "
            "Avoid repeated labels, repeated modules, and overly dense text. Use one short title and only a few stable labels instead of paragraph-like copy. "
            "All text inside the image must read like final audience-facing copy. "
            "Do not include planning notes, prompt-like instructions, creator guidance, or intermediate editorial wording."
            f"{banned_tail}"
        )

    @staticmethod
    def _build_fallback_prompt(
        *,
        user_query: str,
        role: str,
        section_title: str,
        language: str,
    ) -> str:
        topic = strip_visual_or_production_clauses(section_title or role or user_query or "核心主题")
        focus = PublishAssembler._sanitize_visual_brief(section_title or role or "核心信息")
        banned_tail = PublishAssembler._non_cta_visual_ban(role=role, section_title=section_title, language=language)
        return (
            f"Create one technical infographic for {topic}. "
            f"Focus on {focus}. "
            "Landscape layout, concise labels, suitable for inline article placement. "
            "Keep the image tightly topic-specific instead of using generic AI decoration. Avoid repeated labels and avoid dense paragraph-like text. "
            "Image text must be final audience-facing copy, not assignment notes, prompt fragments, or creator instructions."
            f"{banned_tail}"
        )

    @staticmethod
    def _build_compact_prompt(
        *,
        user_query: str,
        role: str,
        section_title: str,
        description: str,
        language: str,
    ) -> str:
        topic = strip_visual_or_production_clauses(section_title or role or user_query or "核心主题")
        focus = PublishAssembler._sanitize_visual_brief(section_title or role or "核心信息")
        detail = PublishAssembler._sanitize_visual_brief(description or "突出核心关系、关键术语和结论")
        banned_tail = PublishAssembler._non_cta_visual_ban(role=role, section_title=section_title, language=language)
        return (
            f"Create a minimal technical visual for {topic}. Focus: {focus}. "
            f"Content: {detail}. Use one clear title, 2-4 labels, one main relationship, white background, medium density, inline-article friendly. "
            "Keep it topic-specific, avoid generic futuristic AI decoration, repeated labels, and dense paragraph text. "
            "The text inside the image must address the final audience as finished publishable copy. "
            "Do not include planning language, requirement phrasing, prompt fragments, or creator-facing notes."
            f"{banned_tail}"
        )

    @staticmethod
    def _sanitize_visual_brief(value: str) -> str:
        text = strip_visual_or_production_clauses(str(value or "").strip())
        text = re.sub(r"(?:\+|/|｜|\|)\s*(结尾互动|结尾引导|cta|互动|标签|hashtags?)", "", text, flags=re.IGNORECASE)
        text = re.sub(r"(结尾互动|结尾引导|评论区互动|评论引导|标签墙|技术标签|hashtags?)", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s{2,}", " ", text).strip(" ，。；;、+|/｜")
        return text or "核心信息"

    @staticmethod
    def _non_cta_visual_ban(*, role: str, section_title: str, language: str) -> str:
        raw = f"{str(role or '').lower()} {str(section_title or '').lower()}"
        allow_cta = any(marker in raw for marker in ("cta", "结尾", "互动", "封面", "cover"))
        if allow_cta:
            return ""
        if language == "zh":
            return (
                " 这张图不要出现结尾引导、立即尝试、评论区互动、关注点赞、收藏转发、标签墙、"
                "话题标签或任何促进行动的发布口号。只保留与当前主题直接相关的信息。"
            )
        return (
            " Do not include closing guidance, try-now copy, comment prompts, follow/like/share prompts, "
            "hashtag walls, or any publishing CTA language. Keep only topic-relevant information."
        )

    @classmethod
    def _weak_visual_prompt_skip_reason(
        cls,
        *,
        user_query: str,
        role: str,
        section_title: str,
        description: str,
    ) -> str:
        user_text = str(user_query or "").strip()
        role_text = cls._normalize_visual_text(role)
        title_text = cls._normalize_visual_text(section_title)
        desc_text = cls._normalize_visual_text(description)
        combined = cls._normalize_visual_text(" ".join([role_text, title_text, desc_text]))
        explicit_visual_request = cls._has_explicit_visual_request(user_text)
        has_specific_subject = cls._has_specific_visual_subject(
            role_text=role_text,
            title_text=title_text,
            desc_text=desc_text,
            combined=combined,
        )

        if cls._has_strong_visual_slot_signal(role_text=role_text, title_text=title_text, desc_text=desc_text):
            return ""
        if explicit_visual_request:
            return ""
        if cls._is_formatting_or_layout_only_request(user_text):
            return "formatting_layout_is_not_visual_request"
        if cls._is_weak_visual_brief(role_text=role_text, title_text=title_text, desc_text=desc_text) and not has_specific_subject:
            return "weak_visual_prompt"
        if not has_specific_subject:
            return "insufficient_visual_specificity"
        return ""

    @staticmethod
    def _normalize_visual_text(value: str) -> str:
        text = strip_visual_or_production_clauses(str(value or "").strip()).lower()
        text = re.sub(r"https?://\S+", " ", text)
        text = re.sub(r"[_\-#/|｜+]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _has_explicit_visual_request(text: str) -> bool:
        raw = str(text or "").lower()
        if not raw.strip():
            return False
        explicit_tokens = (
            "配图",
            "插图",
            "图片",
            "图像",
            "图文",
            "图表",
            "示意图",
            "流程图",
            "架构图",
            "关系图",
            "对比图",
            "信息图",
            "海报",
            "封面",
            "可视化",
            "image",
            "visual",
            "illustration",
            "infographic",
            "diagram",
            "chart",
            "cover image",
            "poster",
        )
        return any(token in raw for token in explicit_tokens)

    @staticmethod
    def _is_formatting_or_layout_only_request(text: str) -> bool:
        raw = str(text or "").lower()
        if not raw.strip():
            return False
        formatting_tokens = (
            "保留原文件",
            "保留原文档",
            "保留原格式",
            "保留格式",
            "保持格式",
            "保留布局",
            "保持布局",
            "表格布局",
            "原表格",
            "原模板",
            "模板样式",
            "文档结构",
            "版式",
            "排版",
            "source file appearance",
            "original layout",
            "table layout",
            "document structure",
            "template style",
            "formatting",
        )
        return any(token in raw for token in formatting_tokens)

    @staticmethod
    def _has_strong_visual_slot_signal(*, role_text: str, title_text: str, desc_text: str) -> bool:
        raw = " ".join([role_text, title_text, desc_text])
        strong_role_tokens = (
            "architecture_diagram",
            "comparison_chart",
            "process_diagram",
            "flowchart",
            "timeline",
            "data_chart",
            "map",
            "流程图",
            "架构图",
            "关系图",
            "对比图",
            "时间线",
            "地图",
        )
        if any(token in raw for token in strong_role_tokens):
            return True
        if any(token in raw for token in ("chart", "diagram", "timeline", "flow", "architecture")):
            return True
        return False

    @classmethod
    def _has_specific_visual_subject(
        cls,
        *,
        role_text: str,
        title_text: str,
        desc_text: str,
        combined: str,
    ) -> bool:
        meaningful_count = cls._meaningful_visual_token_count(combined)
        if meaningful_count < 1:
            return False
        if cls._is_generic_visual_phrase(title_text) and cls._is_generic_visual_phrase(desc_text):
            return False
        if cls._is_generic_visual_phrase(title_text) and role_text in {"", "visual", "image", "illustration", "asset", "visual requirement", "visual_requirement"}:
            return False
        return True

    @classmethod
    def _visual_slot_needs_llm_review(
        cls,
        *,
        user_query: str,
        role: str,
        section_title: str,
        description: str,
    ) -> bool:
        user_text = str(user_query or "").strip()
        role_text = cls._normalize_visual_text(role)
        title_text = cls._normalize_visual_text(section_title)
        desc_text = cls._normalize_visual_text(description)
        combined = cls._normalize_visual_text(" ".join([role_text, title_text, desc_text]))
        if cls._has_explicit_visual_request(user_text):
            return False
        if cls._has_strong_visual_slot_signal(role_text=role_text, title_text=title_text, desc_text=desc_text):
            return False
        if cls._is_formatting_or_layout_only_request(user_text):
            return False
        if not cls._has_specific_visual_subject(
            role_text=role_text,
            title_text=title_text,
            desc_text=desc_text,
            combined=combined,
        ):
            return False
        weak_role = role_text in {"", "visual", "image", "illustration", "asset", "visual requirement", "visual_requirement"}
        generic_detail = cls._is_generic_visual_phrase(desc_text) or cls._is_generic_visual_phrase(title_text)
        low_specificity = cls._meaningful_visual_token_count(combined) <= 2
        return bool(weak_role or generic_detail or low_specificity)

    async def _judge_visual_slot_generation(
        self,
        *,
        user_query: str,
        role: str,
        section_title: str,
        description: str,
        language: str,
    ) -> Tuple[bool, str]:
        system = (
            "You are a strict gate before an image-generation model. "
            "Decide whether a proposed visual slot has a concrete, drawable, task-relevant subject. "
            "Allow useful visuals even if the user did not explicitly ask for images. "
            "Reject slots that only contain generic labels, formatting/layout instructions, or vague placeholders that may cause unrelated image generation. "
            "Return should_generate=false when the slot is likely to produce an arbitrary or off-topic image."
        )
        payload = {
            "user_request": str(user_query or "")[:1200],
            "visual_slot": {
                "role": str(role or ""),
                "section_title": str(section_title or ""),
                "description": str(description or ""),
                "language": str(language or ""),
            },
            "decision_policy": {
                "allow_examples": [
                    "大模型技术演进路径 / show key stages",
                    "供应链协同流程 / show process",
                    "客户流失原因分布 / show categories",
                ],
                "reject_examples": [
                    "表格内容填写",
                    "核心信息",
                    "突出该段核心概念与关系",
                    "保留原文件表格布局",
                ],
            },
        }
        try:
            llm = get_llm_client(streaming=False, stage="visual_slot_gate", intent="task")
            decision = await invoke_structured_decision(
                llm,
                VisualSlotGenerationDecision,
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
                ],
                spec=DecisionTurnSpec(locale=language, turn_id="visual.slot_gate"),
            )
            should_generate = bool(getattr(decision, "should_generate", False))
            confidence = float(getattr(decision, "confidence", 0.0) or 0.0)
            reason = str(getattr(decision, "reason", "") or "").strip()[:180]
            self._log(
                "slot llm_gate | generate=%s confidence=%.2f role=%s section=%s reason=%s"
                % (should_generate, confidence, role or "visual", section_title or "-", reason or "-")
            )
            if should_generate:
                return True, "llm_visual_slot_approved"
            return False, f"llm_visual_slot_rejected:{reason or 'not_concrete'}"
        except Exception as exc:
            self._log(
                "slot llm_gate_failed | role=%s section=%s error=%s"
                % (role or "visual", section_title or "-", str(exc)[:160])
            )
            return True, "llm_visual_slot_gate_unavailable"

    @classmethod
    def _is_weak_visual_brief(cls, *, role_text: str, title_text: str, desc_text: str) -> bool:
        weak_roles = {
            "",
            "visual",
            "image",
            "illustration",
            "asset",
            "visual requirement",
            "visual_requirement",
        }
        weak_titles = (
            "",
            "表格内容填写",
            "内容填写",
            "填写内容",
            "内容生成",
            "正文",
            "结果",
            "输出结果",
            "任务结果",
            "总结",
            "核心信息",
            "主要内容",
            "文档内容",
            "报告内容",
            "general context",
        )
        weak_descriptions = (
            "",
            "突出该段核心概念与关系",
            "突出核心关系、关键术语和结论",
            "突出核心概念与关系",
            "突出核心信息",
            "核心信息",
            "核心概念",
            "可视化呈现",
            "配图",
            "插图",
        )
        role_is_weak = role_text in weak_roles
        title_is_weak = cls._is_generic_visual_phrase(title_text) or any(token == title_text for token in weak_titles)
        desc_is_weak = cls._is_generic_visual_phrase(desc_text) or any(token == desc_text for token in weak_descriptions)
        return (role_is_weak and (title_is_weak or desc_is_weak)) or (title_is_weak and desc_is_weak)

    @staticmethod
    def _is_generic_visual_phrase(value: str) -> bool:
        text = str(value or "").strip().lower()
        if not text:
            return True
        generic_phrases = (
            "表格内容填写",
            "内容填写",
            "填写内容",
            "内容生成",
            "正文",
            "结果",
            "输出结果",
            "任务结果",
            "总结",
            "核心信息",
            "主要内容",
            "文档内容",
            "报告内容",
            "general context",
            "突出该段核心概念与关系",
            "突出核心关系、关键术语和结论",
            "突出核心概念与关系",
            "突出核心信息",
            "核心概念",
            "可视化呈现",
        )
        return text in generic_phrases

    @staticmethod
    def _meaningful_visual_token_count(text: str) -> int:
        raw = str(text or "").strip().lower()
        if not raw:
            return 0
        stopwords = {
            "visual",
            "image",
            "illustration",
            "asset",
            "requirement",
            "core",
            "main",
            "content",
            "summary",
            "result",
            "general",
            "context",
            "核心",
            "信息",
            "内容",
            "主要",
            "总结",
            "结果",
            "表格",
            "填写",
            "文档",
            "报告",
        }
        ascii_tokens = re.findall(r"[a-z0-9]{3,}", raw)
        chinese_tokens = re.findall(r"[\u4e00-\u9fff]{2,}", raw)
        tokens = [
            token
            for token in ascii_tokens + chinese_tokens
            if token not in stopwords and len(token) >= 2
        ]
        return len(set(tokens))

    def _inline_assets(
        self,
        *,
        body_markdown: str,
        plan: ContentPlanSpec,
        assets: List[GeneratedVisualAssetSpec],
    ) -> str:
        text = str(body_markdown or "")
        if not text.strip():
            return text

        lines = text.splitlines()
        ranges = self._final_markdown_section_ranges(text)
        preamble_range = self._leading_markdown_range(markdown=text, ranges=ranges)
        section_range_by_id = self._map_plan_sections_to_markdown_ranges(
            plan=plan,
            ranges=ranges,
            preamble_range=preamble_range,
        )
        first_h2_line = int(ranges[0]["start_line"]) if ranges else 0
        planned_visuals_per_section: Dict[str, int] = {}
        for slot in list(plan.visual_slots or []):
            sid = str(slot.anchor_section_id or "").strip()
            if not sid:
                continue
            planned_visuals_per_section[sid] = int(planned_visuals_per_section.get(sid, 0)) + 1

        def _norm_title(value: str) -> str:
            raw = str(value or "").strip().lower()
            raw = re.sub(r"^\d+(?:\.\d+)*\s*", "", raw)
            raw = re.sub(r"[^\w\u4e00-\u9fff]+", "", raw)
            return raw

        insertions: List[Tuple[int, str]] = []
        per_section_inserted: Dict[str, int] = {}
        figure_index = 0
        for asset in assets:
            if asset.status != "generated" or not str(asset.image_url or "").strip():
                continue
            anchor_section_id = str(asset.anchor_section_id or "").strip()
            per_section_cap = max(1, int(planned_visuals_per_section.get(anchor_section_id, 0) or 1))
            if int(per_section_inserted.get(anchor_section_id, 0)) >= per_section_cap:
                continue
            figure_index += 1
            insert_line = None
            if insert_line is None:
                expected_range = section_range_by_id.get(anchor_section_id)
                if expected_range:
                    insert_line = self._find_contextual_insert_line(
                        lines=lines,
                        expected_range=expected_range,
                        prefer_preamble=bool(str(asset.role or "").strip().lower() == "cover_illustration"),
                    )
            if insert_line is None:
                insert_line = len(lines)
            caption = self._build_neutral_caption(
                figure_index=figure_index,
                asset=asset,
                plan=plan,
            )
            insertions.append(
                (
                    insert_line,
                    (
                        f"\n![{str(asset.alt_text or 'visual')}]({str(asset.image_url or '').strip()})\n"
                        f"\n*图注：{caption}*\n"
                    ),
                )
            )
            per_section_inserted[anchor_section_id] = int(per_section_inserted.get(anchor_section_id, 0)) + 1

        if not insertions:
            return text
        for line_no, md in sorted(insertions, key=lambda x: x[0], reverse=True):
            idx = max(0, min(int(line_no), len(lines)))
            lines.insert(idx, md)
        return self._strip_unresolvable_asset_lines(
            self._strip_editorial_visual_lines("\n".join(lines).strip() + "\n")
        )

    @classmethod
    def _find_contextual_insert_line(
        cls,
        *,
        lines: List[str],
        expected_range: Dict[str, Any],
        prefer_preamble: bool = False,
    ) -> int:
        start_line = max(1, int(expected_range.get("start_line") or 1))
        end_line = max(start_line, int(expected_range.get("end_line") or start_line))
        start_idx = start_line - 1
        end_idx = min(len(lines), end_line)
        paragraph_starts: List[int] = []
        for idx in range(start_idx, end_idx):
            if cls._line_is_inside_fenced_code(lines=lines, line_idx=idx):
                continue
            stripped = str(lines[idx] or "").strip()
            if not stripped:
                continue
            if stripped.startswith("#") or stripped.startswith("![") or stripped.startswith("*图注："):
                continue
            if paragraph_starts and idx == paragraph_starts[-1] + 1:
                continue
            paragraph_starts.append(idx)
        if paragraph_starts:
            preferred_idx = paragraph_starts[0] if prefer_preamble else paragraph_starts[min(1, len(paragraph_starts) - 1)]
            return cls._next_non_fenced_insert_line(lines=lines, insert_idx=preferred_idx + 1, end_idx=end_idx)
        return cls._next_non_fenced_insert_line(lines=lines, insert_idx=start_idx, end_idx=end_idx)

    @staticmethod
    def _is_fence_line(line: str) -> bool:
        return bool(re.match(r"^\s*(```|~~~)", str(line or "")))

    @classmethod
    def _line_is_inside_fenced_code(cls, *, lines: List[str], line_idx: int) -> bool:
        open_fence = False
        for idx, line in enumerate(list(lines or [])[: max(0, int(line_idx)) + 1]):
            if cls._is_fence_line(str(line or "")):
                if idx == int(line_idx):
                    return True
                open_fence = not open_fence
        return open_fence

    @classmethod
    def _insert_position_is_inside_fenced_code(cls, *, lines: List[str], insert_idx: int) -> bool:
        open_fence = False
        for line in list(lines or [])[: max(0, int(insert_idx))]:
            if cls._is_fence_line(str(line or "")):
                open_fence = not open_fence
        return open_fence

    @classmethod
    def _next_non_fenced_insert_line(cls, *, lines: List[str], insert_idx: int, end_idx: int) -> int:
        upper = max(0, min(len(lines), int(end_idx)))
        idx = max(0, min(int(insert_idx), len(lines)))
        while idx <= len(lines):
            if not cls._insert_position_is_inside_fenced_code(lines=lines, insert_idx=idx):
                return idx
            idx += 1
            if idx > upper:
                upper = len(lines)
        return len(lines)

    @staticmethod
    def _humanize_role(role: str) -> str:
        raw = str(role or "").strip().replace("_", " ")
        raw = re.sub(r"\s+", " ", raw).strip()
        if not raw:
            return "配图"
        zh_map = {
            "cover illustration": "头图",
            "framework diagram": "框架图",
            "process diagram": "流程图",
            "architecture diagram": "架构图",
            "comparison chart": "对比图",
            "workflow map": "流程图",
            "application scenarios map": "场景图",
            "infographic": "信息图",
            "visual requirement": "界面示意",
        }
        low = raw.lower()
        return zh_map.get(low, raw)

    @classmethod
    def _build_neutral_caption(
        cls,
        *,
        figure_index: int,
        asset: GeneratedVisualAssetSpec,
        plan: ContentPlanSpec,
    ) -> str:
        section_title = ""
        anchor = str(asset.anchor_section_id or "").strip()
        for sec in list(plan.sections or []):
            if str(sec.section_id or "").strip() == anchor:
                section_title = strip_visual_or_production_clauses(str(sec.title or "").strip())
                break
        role_text = cls._humanize_role(str(asset.role or ""))
        if section_title:
            return f"图{figure_index} {section_title}{role_text if role_text and role_text not in section_title else '示意'}"
        return f"图{figure_index} {role_text}示意"

    @staticmethod
    def _normalize_heading_token(value: str) -> str:
        return normalize_heading_token(value)

    @classmethod
    def _final_markdown_section_ranges(cls, markdown: str) -> List[Dict[str, Any]]:
        return final_markdown_section_ranges(markdown)

    @staticmethod
    def _leading_markdown_range(*, markdown: str, ranges: List[Dict[str, Any]]) -> Dict[str, Any] | None:
        first_start = int(ranges[0].get("start_line") or 0) if ranges else 0
        if first_start <= 1:
            return None
        lines = str(markdown or "").splitlines()
        preamble = "\n".join(lines[: max(0, first_start - 1)]).strip()
        if not preamble:
            return None
        return {
            "index": 0,
            "title": "__preamble__",
            "title_token": "__preamble__",
            "start_line": 1,
            "end_line": max(1, first_start - 1),
        }

    @classmethod
    def _map_plan_sections_to_markdown_ranges(
        cls,
        *,
        plan: ContentPlanSpec,
        ranges: List[Dict[str, Any]],
        preamble_range: Dict[str, Any] | None,
    ) -> Dict[str, Dict[str, Any]]:
        sections = [sec for sec in list(plan.sections or []) if str(sec.section_id or "").strip()]
        mapped: Dict[str, Dict[str, Any]] = {}
        if not sections:
            return mapped

        def _title_score(left: str, right: str) -> float:
            a = cls._normalize_heading_token(left)
            b = cls._normalize_heading_token(right)
            if not a or not b:
                return 0.0
            if a == b:
                return 1.0
            if a in b or b in a:
                return 0.82
            aset = set(a)
            bset = set(b)
            return float(len(aset & bset)) / float(max(len(aset), len(bset))) if aset and bset else 0.0

        range_cursor = 0
        for idx, section in enumerate(sections):
            section_id = str(section.section_id or "").strip()
            title = str(section.title or "").strip()
            if idx == 0 and preamble_range is not None:
                first_range_score = _title_score(title, str((ranges[0] or {}).get("title") or "")) if ranges else 0.0
                if first_range_score < 0.45:
                    mapped[section_id] = dict(preamble_range)
                    continue
            best_idx = -1
            best_score = -1.0
            for ridx in range(range_cursor, len(ranges)):
                score = _title_score(title, str(ranges[ridx].get("title") or ""))
                if score > best_score:
                    best_score = score
                    best_idx = ridx
            if best_idx >= 0:
                mapped[section_id] = dict(ranges[best_idx])
                range_cursor = best_idx + 1
        return mapped
