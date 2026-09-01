from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from app.enterprise_capabilities.data import MetricsEngine, run_script
from app.enterprise_capabilities.artifacts import artifact_export, document_fill, document_transform, table_generate
from app.enterprise_capabilities.artifacts.references import require_owned_artifacts
from app.enterprise_capabilities.artifacts.document_result import public_document_parse_result
from app.enterprise_capabilities.artifacts.resource_result import (
    own_parsed_document_images,
    parser_artifacts,
    public_resource_result,
)
from app.enterprise_capabilities.browser import browser_task
from app.knowledge.retrieval.retrieval_client import knowledge_retrieval_client
from app.knowledge.retrieval.retrieval_client import KnowledgeRetrievalError
from app.enterprise_capabilities.knowledge_result import available_result, unavailable_result
from app.services.runtime_parse_service import runtime_parse_service
from app.enterprise_capabilities.research.progressive.provider_router import ProviderRouter
from app.enterprise_capabilities.research.progressive.agent import ProgressiveResearchAgent
from app.infrastructure.request_context import reset_request_context, set_request_context
from app.llm.configured_models import (
    get_default_model_config,
    get_default_model_config_by_capability,
    get_model_config,
    reset_configured_model_context,
    set_configured_model_context,
)
from app.enterprise_capabilities.research import (
    ResearchTimelineProjector,
    UrlResourceCollector,
    build_research_evidence_bundle,
    public_evidence_bundle,
)
from app.enterprise_capabilities.content import content_production
from app.enterprise_capabilities.images import generate_images
from app.enterprise_capabilities.presentation import presentation_create
from app.enterprise_capabilities.pdf_editing import pdf_retain_pages
from app.enterprise_capabilities.evidence import (
    admit_knowledge_evidence,
    build_document_evidence_bundle,
    build_knowledge_evidence_bundle,
    public_capability_evidence,
)

from .contracts import CapabilityExecutionContext
from .registry import CapabilityHandlerRegistry


def _node(arguments: dict[str, Any], capability_id: str) -> SimpleNamespace:
    resource_types = list(arguments.get("resource_types") or [])
    return SimpleNamespace(
        node_id=f"dsh:{capability_id}", depends_on=[], goal=str(arguments.get("purpose") or arguments.get("question") or ""),
        meta={"capability_id": capability_id, "semantic_config": {"resource_types": resource_types}},
    )


def _artifact_output_spec(arguments: dict[str, Any], key: str) -> dict[str, Any]:
    artifacts = [dict(item) for item in list(arguments.get(key) or []) if isinstance(item, dict)]
    semantic_key = "images" if key == "images" else "documents"
    return {
        "input_artifacts": {semantic_key: artifacts},
        "multimodal": {"uploaded_assets": artifacts} if key == "images" else {},
        "documents": {"uploaded_assets": artifacts} if key == "artifacts" else {},
    }


async def knowledge_search(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    selected = [str(item) for item in list(context.turn_context.get("knowledge_base_ids") or []) if str(item)]
    query = str(arguments.get("query") or "")
    try:
        result = await knowledge_retrieval_client.search(
            query=query, main_id=context.tenant_id,
            knowledge_base_ids=selected or None, top_n=int(arguments.get("top_n") or 8), rerank=arguments.get("rerank"),
        )
    except KnowledgeRetrievalError as exc:
        return unavailable_result(query=query, error=exc)
    items = []
    for item in result.items:
        row = item.model_dump(mode="json")
        row["citation_ref"] = f"kb://{row.get('documentId', '')}/{row.get('chunkId', '')}"
        items.append(row)
    admission = admit_knowledge_evidence(items)
    admitted_items = list(admission.admitted)
    bundle = build_knowledge_evidence_bundle(query=result.query, items=admitted_items)
    payload = available_result(
        query=result.query,
        retrieval_mode=result.retrievalMode,
        total=result.total,
        items=items,
    )
    # Keep the wider candidate set available to the agent, but do not claim
    # that every retrieval candidate is reliable user-visible evidence.
    payload["retrieved_total"] = len(items)
    payload["evidence_total"] = len(admitted_items)
    payload["evidence_available"] = bool(admitted_items)
    if items and not admitted_items:
        payload["message"] = "内部知识检索完成，但候选内容未达到可靠证据准入标准。"
    if bundle:
        payload["evidence_bundle"] = public_capability_evidence(bundle)
        payload["_execution_evidence_bundle"] = bundle
    return payload


async def document_parse(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    safe_arguments = {**arguments, "artifacts": parser_artifacts(list(arguments.get("artifacts") or []), user_id=context.user_id)}
    output_spec = _artifact_output_spec(safe_arguments, "artifacts")
    result = await runtime_parse_service.parse_documents(
        node=_node(arguments, "document.parse"), output_spec=output_spec, user_text=str(arguments.get("purpose") or ""),
    )
    owned_result = await asyncio.to_thread(
        own_parsed_document_images,
        result,
        user_id=context.user_id,
    )
    public_result = public_document_parse_result(owned_result)
    bundle = build_document_evidence_bundle(
        purpose=str(arguments.get("purpose") or ""),
        parse_result=owned_result,
    )
    payload = {"success": True, **public_result}
    if bundle:
        payload["evidence_bundle"] = public_capability_evidence(bundle)
        payload["_execution_evidence_bundle"] = bundle
    return payload


async def document_extract_resources(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    safe_arguments = {**arguments, "artifacts": parser_artifacts(list(arguments.get("artifacts") or []), user_id=context.user_id)}
    output_spec = _artifact_output_spec(safe_arguments, "artifacts")
    result = await runtime_parse_service.extract_resources(
        node=_node(arguments, "document.extract_resources"), output_spec=output_spec,
        user_text=str(arguments.get("purpose") or ""),
    )
    public_result = await asyncio.to_thread(
        public_resource_result,
        result,
        user_id=context.user_id,
    )
    return {"success": True, **public_result}


async def image_extract_facts(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    vision_model = await get_default_model_config_by_capability(context.tenant_id, capability="vision")
    if vision_model is None:
        return {
            "success": False,
            "ok": False,
            "error": "vision_model_unavailable",
            "message": "No active Vision model is configured for this organization.",
        }

    safe_arguments = {**arguments, "images": require_owned_artifacts(list(arguments.get("images") or []), user_id=context.user_id)}
    output_spec = _artifact_output_spec(safe_arguments, "images")
    previous_model = set_configured_model_context(vision_model)
    try:
        result = await runtime_parse_service.extract_image_facts(
            node=_node(arguments, "vision.extract_facts"), output_spec=output_spec,
            user_text=str(arguments.get("question") or "请提取图片中的可验证事实"),
        )
    finally:
        reset_configured_model_context(previous_model)

    if not result.get("skipped") and not str(result.get("vision_summary") or "").strip():
        return {
            "success": False,
            "ok": False,
            "error": "vision_extraction_failed",
            "message": "The configured Vision model could not extract facts. Test its API key and model ID in the admin console.",
        }
    return {"success": True, **result}


async def web_collect(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    collected = await UrlResourceCollector().collect(
        urls=[str(item) for item in list(arguments.get("urls") or [])],
        tenant_id=context.tenant_id,
        user_id=context.user_id,
    )
    public_result = UrlResourceCollector.public_result(collected)
    bundle = build_research_evidence_bundle(
        tool_name="web_collect",
        query="\n".join(str(item) for item in list(arguments.get("urls") or [])),
        results=list(public_result.get("results") or []),
        raw_result=public_result,
    )
    if bundle:
        public_result["evidence_bundle"] = public_evidence_bundle(bundle)
        public_result["_execution_evidence_bundle"] = bundle
    return public_result


async def external_search(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    previous = set_request_context({"main_id": context.tenant_id, "user_id": context.user_id})
    try:
        candidates, trace = await ProviderRouter().search(
            [str(item) for item in list(arguments.get("queries") or []) if str(item).strip()],
            max_results_per_query=int(arguments.get("max_results_per_query") or 8),
        )
    finally:
        reset_request_context(previous)
    results = [item.model_dump(mode="json") for item in candidates]
    query = "\n".join(str(item) for item in list(arguments.get("queries") or []) if str(item).strip())
    raw_result = {"results": results, "provider_trace": trace, "total": len(results)}
    bundle = build_research_evidence_bundle(
        tool_name="external_search", query=query, results=results, raw_result=raw_result,
    )
    return {
        "success": bool(results), **raw_result,
        "evidence_bundle": public_evidence_bundle(bundle),
        "_execution_evidence_bundle": bundle,
    }


async def progressive_research(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    model_config = None
    if context.model_instance_id:
        model_config = await get_model_config(context.model_instance_id, context.tenant_id)
    if model_config is None:
        model_config = await get_default_model_config(context.tenant_id)
    if model_config is None:
        return {"success": False, "ok": False, "error": "research_model_unavailable"}

    projector = ResearchTimelineProjector(
        outer_action_id=context.action_id,
        message_id=context.message_id,
    )

    async def publish_native(event: dict[str, Any]) -> None:
        for row in projector.project(event):
            await context.publish_progress(row)

    previous_request = set_request_context({
        "main_id": context.tenant_id,
        "user_id": context.user_id,
        "configured_model": model_config,
        "model_instance_id": context.model_instance_id,
    })
    previous_model = set_configured_model_context(model_config)
    try:
        agent = ProgressiveResearchAgent(
            max_rounds=int(arguments.get("max_rounds") or 3),
            max_results_per_query=int(arguments.get("max_results_per_query") or 8),
            freshness_days=int(arguments.get("freshness_days") or 30),
            progress_callback=publish_native,
        )
        result = await agent.run(
            query=str(arguments.get("query") or "").strip(),
            user_query=str(arguments.get("query") or "").strip(),
            language=str(arguments.get("language") or context.turn_context.get("language") or "zh"),
        )
        result_payload = result.model_dump(mode="json")
        bundle = build_research_evidence_bundle(
            tool_name="progressive_research",
            query=str(result.query or arguments.get("query") or ""),
            results=[dict(item) for item in list(result.results or []) if isinstance(item, dict)],
            raw_result=result_payload,
            evidence_sufficient=result.evidence_sufficient,
            budget_exhausted=result.budget_exhausted,
            stop_reason=result.stop_reason,
        )
        return {
            "success": result.ok, **result_payload,
            "evidence_bundle": public_evidence_bundle(bundle),
            "_execution_evidence_bundle": bundle,
        }
    finally:
        reset_configured_model_context(previous_model)
        reset_request_context(previous_request)


async def compute_metrics(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    del context
    return MetricsEngine.compute(arguments)


def build_default_registry() -> CapabilityHandlerRegistry:
    registry = CapabilityHandlerRegistry()
    registry.register("knowledge.search@v1", knowledge_search)
    registry.register("document.parse@v1", document_parse)
    registry.register("document.extract_resources@v1", document_extract_resources)
    registry.register("document.pdf_retain_pages@v1", pdf_retain_pages)
    registry.register("vision.extract_facts@v1", image_extract_facts)
    registry.register("research.collect_url@v1", web_collect)
    registry.register("research.search_web@v1", external_search)
    registry.register("research.progressive@v1", progressive_research)
    registry.register("data.compute_metrics@v1", compute_metrics)
    registry.register("artifact.table_generate@v1", table_generate)
    registry.register("presentation.create@v1", presentation_create)
    registry.register("artifact.export@v1", artifact_export)
    registry.register("content.produce@v1", content_production)
    registry.register("image.generate@v1", generate_images)
    registry.register("document.transform@v1", document_transform)
    registry.register("document.fill_form@v1", document_fill)
    registry.register("browser.task@v1", browser_task)
    registry.register("data.run_script@v1", run_script)
    return registry
