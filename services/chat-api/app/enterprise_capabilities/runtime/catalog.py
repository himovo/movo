from __future__ import annotations

import hashlib
import json
from typing import Any

from .contracts import CapabilityDefinition
from app.enterprise_capabilities.spreadsheets import workbook_input_schema
from app.enterprise_capabilities.content import (
    content_production_input_schema,
    content_production_output_schema,
)
from app.enterprise_capabilities.images import (
    image_generation_input_schema,
    image_generation_output_schema,
)
from app.enterprise_capabilities.presentation import (
    presentation_create_input_schema,
    presentation_create_output_schema,
)
from app.enterprise_capabilities.pdf_editing import (
    pdf_retain_pages_input_schema,
    pdf_retain_pages_output_schema,
)
from .timeouts import (
    CONTENT_PRODUCTION_INACTIVITY_TIMEOUT_MS,
    CONTENT_PRODUCTION_TOTAL_TIMEOUT_MS,
    IMAGE_GENERATION_INACTIVITY_TIMEOUT_MS,
    IMAGE_GENERATION_TOTAL_TIMEOUT_MS,
    PRESENTATION_CREATION_INACTIVITY_TIMEOUT_MS,
    PRESENTATION_CREATION_TOTAL_TIMEOUT_MS,
)


def _object(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = list(required)
    return schema


def _capability_result() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"success": {"type": "boolean"}},
        "required": ["success"],
        "additionalProperties": True,
    }


def _definition(
    *,
    capability_ref: str,
    tool_name: str,
    domain: str,
    display_name: str,
    description: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any] | None = None,
    risk_level: str = "read",
    approval_required: bool = False,
    approval_argument: str = "",
    approval_values: tuple[str, ...] = (),
    timeout_ms: int = 30_000,
    timeout_mode: str = "fixed",
    inactivity_timeout_ms: int = 0,
    idempotent: bool = True,
    delivery_mode: str = "model_synthesized",
    consumes_execution_evidence: bool = False,
) -> CapabilityDefinition:
    payload = {
        "capability_ref": capability_ref,
        "tool_name": tool_name,
        "domain": domain,
        "display_name": display_name,
        "description": description,
        "input_schema": input_schema,
        "output_schema": output_schema or _capability_result(),
        "risk_level": risk_level,
        "approval_required": approval_required,
        "approval_argument": approval_argument,
        "approval_values": approval_values,
        "timeout_ms": timeout_ms,
        "timeout_mode": timeout_mode,
        "inactivity_timeout_ms": inactivity_timeout_ms,
        "idempotent": idempotent,
        "delivery_mode": delivery_mode,
        "consumes_execution_evidence": consumes_execution_evidence,
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]
    scopes = ("capabilities:read",) if risk_level == "read" else ("capabilities:write",)
    return CapabilityDefinition(version=f"cap-{digest}", required_scopes=scopes, **payload)


class InternalCapabilityCatalog:
    """Product capability inventory. It contains no legacy agent or graph objects."""

    def __init__(self) -> None:
        artifact = _object({
            "object_path": {"type": "string"}, "url": {"type": "string"},
            "signed_url": {"type": "string"}, "filename": {"type": "string"},
            "content_type": {"type": "string"}, "size": {"type": "integer", "minimum": 0},
        })
        calculation = _object({
            "name": {"type": "string", "minLength": 1},
            "type": {"type": "string", "enum": [
                "count", "sum", "avg", "min", "max", "count_where",
                "share_where", "ratio", "subtract", "rank",
            ]},
            "field": {"type": "string"},
            "condition": {"type": "object"},
            "numerator": {}, "denominator": {}, "left": {}, "right": {},
            "order": {"type": "string", "enum": ["asc", "desc"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        }, ("name", "type"))
        per_item_calculation = _object({
            "name": {"type": "string", "minLength": 1},
            "type": {"type": "string", "enum": ["subtract", "ratio", "rank"]},
            "field": {"type": "string"},
            "left": {}, "right": {}, "numerator": {}, "denominator": {},
            "order": {"type": "string", "enum": ["asc", "desc"]},
        }, ("name", "type"))
        self._definitions = (
            _definition(
                capability_ref="knowledge.search@v1", tool_name="knowledge_search", domain="knowledge",
                display_name="内部知识检索",
                description="Search MOVO's server-authorized internal knowledge for enterprise-specific facts, policies, documents, or prior internal context. Use web_search for a bounded public lookup, progressive_research for multi-source public research, and combine internal and public evidence only when the user asks for a comparison. Tenant and knowledge-base scope are injected by MOVO; never ask for or supply them as arguments.",
                input_schema=_object({
                    "query": {"type": "string", "minLength": 1},
                    "top_n": {"type": "integer", "minimum": 1, "maximum": 20},
                    "rerank": {"type": "boolean"},
                }, ("query",)),
            ),
            _definition(
                capability_ref="document.parse@v1", tool_name="document_parse", domain="document",
                display_name="读取材料", description="Parse referenced PDF, DOCX, XLSX, PPTX, CSV, Markdown or text documents through MOVO's document service.",
                input_schema=_object({"artifacts": {"type": "array", "items": artifact, "minItems": 1}, "purpose": {"type": "string"}}, ("artifacts",)),
                timeout_ms=120_000,
            ),
            _definition(
                capability_ref="document.extract_resources@v1", tool_name="document_extract_resources", domain="document",
                display_name="提取材料资源", description="Extract stable image, URL and attachment references from uploaded or parsed material.",
                input_schema=_object({
                    "artifacts": {"type": "array", "items": artifact, "minItems": 1},
                    "resource_types": {"type": "array", "items": {"type": "string", "enum": ["images", "urls", "attachments"]}},
                    "purpose": {"type": "string"},
                }, ("artifacts",)), timeout_ms=120_000,
            ),
            _definition(
                capability_ref="document.pdf_retain_pages@v1",
                tool_name="pdf_retain_pages",
                domain="document",
                display_name="精简 PDF 页面",
                description=(
                    "Create a new PDF containing only explicitly selected one-based source pages. "
                    "First inspect the source with document_parse and decide keep_pages yourself from the user's audience and content requirements; "
                    "this Tool performs no semantic selection. It preserves selected pages in their original source order, never rewrites page content, "
                    "never overwrites the source PDF, and returns the single final derived PDF artifact."
                ),
                input_schema=pdf_retain_pages_input_schema(artifact),
                output_schema=pdf_retain_pages_output_schema(),
                timeout_ms=120_000,
            ),
            _definition(
                capability_ref="vision.extract_facts@v1", tool_name="image_extract_facts", domain="vision",
                display_name="图片事实提取", description="Use MOVO's governed vision service to extract facts from referenced images.",
                input_schema=_object({"images": {"type": "array", "items": artifact, "minItems": 1}, "question": {"type": "string"}}, ("images",)),
                timeout_ms=120_000,
            ),
            _definition(
                capability_ref="research.collect_url@v1", tool_name="web_collect", domain="research",
                display_name="网页采集", description="Collect explicit HTTP(S) URLs with MOVO's bounded direct fetcher. It reads ordinary HTML/text, downloads remote documents and images as governed artifacts, and uses Firecrawl only as an optional fallback for blocked, JavaScript-only, or empty pages.",
                input_schema=_object({"urls": {"type": "array", "items": {"type": "string", "format": "uri"}, "minItems": 1, "maxItems": 10}}, ("urls",)),
                timeout_ms=120_000,
            ),
            _definition(
                capability_ref="research.search_web@v1", tool_name="external_search", domain="research",
                display_name="外部搜索 Provider", description="Internal MOVO search-provider primitive used by DSH native web_search. It is not exposed as a second model-facing search tool.",
                input_schema=_object({
                    "queries": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "maxItems": 8},
                    "max_results_per_query": {"type": "integer", "minimum": 1, "maximum": 20},
                }, ("queries",)), timeout_ms=120_000,
            ),
            _definition(
                capability_ref="research.progressive@v1", tool_name="progressive_research", domain="research",
                display_name="渐进式深度研究",
                description="Use for complex public-web research that needs multiple sources, comparison across dimensions, coverage-gap analysis, or an explicit judgment that the evidence is sufficient. This capability plans search queries, evaluates evidence after every round, and continues with refined queries until the evidence is sufficient or the bounded research budget is reached. For one bounded factual or current lookup, use web_search instead.",
                input_schema=_object({
                    "query": {"type": "string", "minLength": 1},
                    "max_rounds": {"type": "integer", "minimum": 1, "maximum": 6},
                    "max_results_per_query": {"type": "integer", "minimum": 1, "maximum": 20},
                    "freshness_days": {"type": "integer", "minimum": 1, "maximum": 3650},
                    "language": {"type": "string"},
                }, ("query",)), timeout_ms=300_000,
            ),
            _definition(
                capability_ref="data.compute_metrics@v1", tool_name="compute_metrics", domain="data",
                display_name="确定性指标计算", description="Compute deterministic aggregate and per-record metrics over structured records; do not estimate missing values. For per-record subtract or ratio, pass operands as field references such as {field: actual_amount}; these are accepted in either calculations or per_item_calculations.",
                input_schema=_object({
                    "records": {"type": "array", "items": {}},
                    "calculations": {"type": "array", "items": calculation},
                    "per_item_calculations": {"type": "array", "items": per_item_calculation},
                }, ("records", "calculations")),
            ),
            _definition(
                capability_ref="artifact.table_generate@v1", tool_name="table_generate", domain="artifact",
                display_name="生成电子表格", description="Render a governed XLSX artifact from a structured workbook specification using MOVO's spreadsheet service. Set delivery_scope=final only when the user explicitly requests a spreadsheet/data attachment; set delivery_scope=intermediate when a downstream workflow needs XLSX but the user did not request it as a separate attachment. Tables or charts embedded inside a report, article, presentation, or ordinary answer do not authorize a separate spreadsheet artifact.",
                input_schema=_object({
                    "workbook": workbook_input_schema(), "filename": {"type": "string"},
                    "delivery_scope": {"type": "string", "enum": ["final", "intermediate"]},
                }, ("workbook", "delivery_scope")), timeout_ms=120_000,
            ),
            _definition(
                capability_ref="presentation.create@v1", tool_name="presentation_create", domain="presentation",
                display_name="生成PPT",
                description="Create one complete, editable presentation through MOVO's governed PresentationPipeline. Pass only the business brief, exact slide count when explicitly requested, audience and design intent; never construct, guess, export, or trial internal Blueprint JSON yourself. The Tool owns story planning, page composition, visuals, quality checks, HTML preview and editable Blueprint persistence. When accepted=true, use the single returned presentation artifact and do not call artifact_export to create another deck.",
                input_schema=presentation_create_input_schema(),
                output_schema=presentation_create_output_schema(),
                timeout_ms=PRESENTATION_CREATION_TOTAL_TIMEOUT_MS,
                timeout_mode="activity",
                inactivity_timeout_ms=PRESENTATION_CREATION_INACTIVITY_TIMEOUT_MS,
                consumes_execution_evidence=True,
            ),
            _definition(
                capability_ref="artifact.export@v1", tool_name="artifact_export", domain="artifact",
                display_name="导出交付物", description="Export an already-authored deliverable: render final Markdown to DOCX, PDF or Markdown; render a structured workbook to XLSX; or compile an existing MOVO presentation Blueprint to PPTX. Never use this Tool to create a presentation, invent a Blueprint, probe Blueprint schemas, or generate intermediate files; use presentation_create for every user request to create a deck.",
                input_schema=_object({
                    "format": {"type": "string", "enum": ["docx", "pdf", "md", "pptx", "xlsx"]},
                    "markdown": {"type": "string"}, "blueprint_object_path": {"type": "string"},
                    "workbook": workbook_input_schema(),
                    "filename": {"type": "string"}, "title": {"type": "string"},
                    "skip_cover": {"type": "boolean"}, "skip_toc": {"type": "boolean"},
                }, ("format",)), timeout_ms=300_000,
            ),
            _definition(
                capability_ref="content.produce@v1", tool_name="content_production", domain="content",
                display_name="内容生产",
                description="Use MOVO's governed long-form production pipeline only when the requested deliverable needs document-scale structure, writing-style governance, illustrations, validation/rewrite, or long-form assembly. Decide semantically from the complete delivery requirements, never from keywords such as email, report, article, or summary. Produce ordinary short content yourself without this tool. The pipeline supports only single-pass long-form and sectional ultra-long-form production, and automatically consumes research evidence produced earlier in the same execution. Return its Markdown faithfully; do not rewrite it. When accepted=true, the governed deliverable is final for this user message and must not be independently re-measured or regenerated. When accepted=false, use acceptance.reasons and retry only when retry_allowed=true.",
                input_schema=content_production_input_schema(),
                output_schema=content_production_output_schema(),
                timeout_ms=CONTENT_PRODUCTION_TOTAL_TIMEOUT_MS,
                timeout_mode="activity",
                inactivity_timeout_ms=CONTENT_PRODUCTION_INACTIVITY_TIMEOUT_MS,
                delivery_mode="authoritative_markdown",
                consumes_execution_evidence=True,
            ),
            _definition(
                capability_ref="image.generate@v1", tool_name="generate_images", domain="image",
                display_name="生成图片",
                description="Generate and persist real image assets through MOVO's administrator-configured image model. This is one provider-neutral capability: never choose or name Qwen, OpenAI, Azure, or another provider. Use it whenever the user asks for actual images, illustrations, or article visuals; do not substitute image suggestions or prompts. Submit one distinct image specification per requested image, then embed each returned Markdown image reference at its intended placement. If the user asks only for image ideas or prompts, answer directly without this tool.",
                input_schema=image_generation_input_schema(),
                output_schema=image_generation_output_schema(),
                timeout_ms=IMAGE_GENERATION_TOTAL_TIMEOUT_MS,
                timeout_mode="activity",
                inactivity_timeout_ms=IMAGE_GENERATION_INACTIVITY_TIMEOUT_MS,
            ),
            _definition(
                capability_ref="document.transform@v1", tool_name="document_transform", domain="document",
                display_name="文档保真翻译", description="Translate an existing DOCX or XLSX artifact while preserving its structure and formatting through MOVO's tested in-place translation service.",
                input_schema=_object({
                    "artifact": artifact, "source_language": {"type": "string"},
                    "target_language": {"type": "string"}, "filename": {"type": "string"},
                }, ("artifact", "source_language", "target_language")), timeout_ms=300_000,
            ),
            _definition(
                capability_ref="document.fill_form@v1", tool_name="table_fill", domain="document",
                display_name="填写文档表单", description="Fill an existing DOCX or XLSX template with user-provided facts while preserving formatting through MOVO's tested form service.",
                input_schema=_object({
                    "artifact": artifact, "facts": {"type": "string", "minLength": 1},
                    "overwrite": {"type": "boolean"}, "filename": {"type": "string"},
                }, ("artifact", "facts")), risk_level="write", approval_required=True, timeout_ms=300_000, idempotent=False,
            ),
            _definition(
                capability_ref="browser.task@v1", tool_name="browser_task", domain="browser",
                display_name="浏览器任务", description="Delegate one bounded public website mission to MOVO's native-CDP Browser Agent. Use read when page content is needed, including when target_url is supplied; use navigate only when the requested outcome is opening a page. Internal MOVO artifact URLs are not browser targets: pass their object_path to the matching document or image tool. The Browser Agent owns navigation, interaction, recovery, human assistance and effect verification.",
                input_schema=_object({
                    "objective": {"type": "string", "minLength": 1},
                    "operation": {"type": "string", "enum": ["read", "navigate", "submit", "modify", "delete", "file_transfer", "publish"], "description": "Requested outcome. A target_url does not imply navigate: choose read whenever information must be returned."},
                    "target_name": {"type": "string"}, "target_url": {"type": "string"},
                    "inputs": {"type": "object"},
                }, ("objective", "operation")), risk_level="dangerous", approval_required=False,
                approval_argument="operation", approval_values=("submit", "modify", "delete", "file_transfer", "publish"),
                timeout_ms=300_000, idempotent=False,
            ),
            _definition(
                capability_ref="data.run_script@v1", tool_name="run_script", domain="data",
                display_name="受控脚本处理", description="Run ordinary Python or a run(inputs, context) plugin in MOVO's isolated subprocess sandbox. Current-turn attachments are mounted on every invocation. In ordinary Python use input_files[0]['local_path'] (or input_dir) instead of searching the filesystem. UTF-8 stdout is supported directly; do not Base64-wrap text. Network is disabled; CPU, memory, files and artifact upload are governed. Set delivery_scope=final only when the user explicitly requested the generated file; use intermediate when the file only carries data into later workflow steps.",
                input_schema=_object({
                    "code": {"type": "string", "minLength": 1, "description": "Ordinary Python is accepted directly. Use input_files for mounted attachments, inputs for supplied data, and output_dir for generated files. UTF-8 print output is returned directly."},
                    "data": {"type": "object"},
                    "files": {"type": "array", "items": artifact},
                    "delivery_scope": {"type": "string", "enum": ["final", "intermediate"]},
                }, ("code", "delivery_scope")), risk_level="dangerous", approval_required=True,
                timeout_ms=90_000, idempotent=False,
            ),
        )

    async def list_enabled(self, tenant_id: str, user_id: str) -> list[CapabilityDefinition]:
        del tenant_id, user_id
        return list(self._definitions)

    def definitions(self) -> tuple[CapabilityDefinition, ...]:
        return self._definitions
