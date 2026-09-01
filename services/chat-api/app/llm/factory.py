from typing import Any, Dict

from app.core.config import get_settings
from app.llm.capabilities import infer_structured_output_mode
from app.llm.model_router import get_model_router
from app.infrastructure.observability.execution_trace import ensure_trace_id, log_trace
from app.infrastructure.request_context import get_request_context

from app.llm.base import BaseLLMClient
from app.llm.configured_models import build_llm_client_from_config, get_configured_model_context
from app.llm.instrumented_client import InstrumentedLLMClient
from app.llm.providers.azure_openai import AzureOpenAIClient
from app.llm.providers.default_openai import DefaultOpenAIClient
from app.llm.providers.qwen import QwenClient


def _validate_api_key_ascii(*, api_key: str, provider: str) -> None:
    key = str(api_key or "")
    if key and not key.isascii():
        raise ValueError(
            f"Invalid {provider} API key: contains non-ASCII characters. "
            "Please set a real API key in backend/.env (do not use Chinese placeholder text)."
        )


def _resolve_azure_deployment(*, selected_model: str, intent: str | None, stage: str | None) -> tuple[str, str]:
    settings = get_settings()
    dep_chat = str(settings.AZURE_DEPLOYMENT_CHAT or "").strip()
    dep_general = str(settings.AZURE_DEPLOYMENT_GENERAL or "").strip()
    dep_coding = str(settings.AZURE_DEPLOYMENT_CODING or "").strip()
    dep_default = str(settings.AZURE_DEPLOYMENT_NAME or "").strip()

    model_chat = str(settings.OPENAI_MODEL_CHAT or "").strip().lower()
    model_general = str(settings.OPENAI_MODEL_GENERAL or "").strip().lower()
    model_coding = str(settings.OPENAI_MODEL_CODING or "").strip().lower()
    selected = str(selected_model or "").strip().lower()
    stage_s = str(stage or "").strip().lower()
    intent_s = str(intent or "").strip().lower()

    route_key = "general"
    if selected and selected == model_coding:
        route_key = "coding"
    elif selected and selected == model_chat:
        route_key = "chat"
    elif selected and selected == model_general:
        route_key = "general"
    elif "codex" in selected or "coding" in selected or stage_s == "coding" or intent_s == "coding":
        route_key = "coding"
    elif stage_s in {"browser_planning", "research_query_refine"} or intent_s in {"chat", "browser_automation"}:
        route_key = "chat"

    deployment = {
        "chat": dep_chat,
        "general": dep_general,
        "coding": dep_coding,
    }.get(route_key, "")

    if not deployment:
        deployment = dep_default or dep_general or dep_chat or dep_coding
    return deployment, route_key


def get_llm_client(
    *,
    streaming: bool = True,
    model_name: str | None = None,
    intent: str | None = None,
    stage: str | None = None,
    node_id: str | None = None,
    output_spec: Dict[str, Any] | None = None,
) -> BaseLLMClient:
    merged_output_spec: Dict[str, Any] = {}
    merged_output_spec.update(get_request_context())
    if isinstance(output_spec, dict):
        merged_output_spec.update(output_spec)
    output_spec = merged_output_spec
    configured_model = output_spec.get("configured_model") if isinstance(output_spec, dict) else None
    if not isinstance(configured_model, dict) or not configured_model:
        configured_model = get_configured_model_context()
    if isinstance(configured_model, dict) and configured_model:
        return build_llm_client_from_config(
            configured_model,
            streaming=streaming,
            intent=intent,
            stage=stage,
            node_id=node_id,
            output_spec=output_spec,
        )
    settings = get_settings()
    selection = get_model_router().resolve(
        explicit_model=model_name,
        intent=intent,
        stage=stage,
        node_id=node_id,
        output_spec=output_spec or {},
    )
    trace_id = ensure_trace_id(output_spec or {})
    selected_model = selection.model
    
    if isinstance(output_spec, dict) and output_spec:
        log_trace(
            trace_id=trace_id,
            scope="llm.factory",
            event="model_routed",
            stage=str(stage or ""),
            intent=str(intent or ""),
            node_id=str(node_id or ""),
            model=str(selected_model or ""),
            source=str(selection.source or ""),
        )
        
    if settings.USE_AZURE:
        _validate_api_key_ascii(api_key=settings.OPENAI_API_KEY, provider="Azure OpenAI")
        azure_deployment, route_key = _resolve_azure_deployment(
            selected_model=selected_model,
            intent=intent,
            stage=stage,
        )
        
        if isinstance(output_spec, dict) and output_spec:
            log_trace(
                trace_id=trace_id,
                scope="llm.factory",
                event="azure_deployment_resolved",
                route_key=route_key,
                deployment=azure_deployment,
            )
            
        client = AzureOpenAIClient(
            api_key=settings.OPENAI_API_KEY,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_deployment=azure_deployment,
            streaming=streaming,
        )
        return InstrumentedLLMClient(
            client,
            model_name=selected_model,
            model_id=azure_deployment or selected_model,
            stage=stage,
            intent=intent,
            node_id=node_id,
            output_spec=output_spec,
        )
        
    if settings.USE_QWEN:
        _validate_api_key_ascii(api_key=(settings.QWEN_API_KEY or settings.OPENAI_API_KEY), provider="Qwen")
        client = QwenClient(
            api_key=settings.QWEN_API_KEY or settings.OPENAI_API_KEY,
            base_url=settings.QWEN_BASE_URL,
            model=settings.QWEN_MODEL,
            streaming=streaming,
            structured_output_mode="prompt_json",
        )
        return InstrumentedLLMClient(
            client,
            model_name=selected_model or settings.QWEN_MODEL,
            model_id=settings.QWEN_MODEL,
            stage=stage,
            intent=intent,
            node_id=node_id,
            output_spec=output_spec,
        )
        
    _validate_api_key_ascii(api_key=settings.OPENAI_API_KEY, provider="OpenAI")
    base_url = str(settings.OPENAI_BASE_URL or "").strip()
    structured_output_mode = (
        "native"
        if not base_url or "openai.com" in base_url.lower()
        else infer_structured_output_mode(
            provider_type="openai_compatible",
            provider_name=base_url,
            model_name=selected_model,
        )
    )
    client = DefaultOpenAIClient(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        model=selected_model,
        streaming=streaming,
        structured_output_mode=structured_output_mode,
    )
    return InstrumentedLLMClient(
        client,
        model_name=selected_model,
        model_id=selected_model,
        stage=stage,
        intent=intent,
        node_id=node_id,
        output_spec=output_spec,
    )


def get_request_scoped_llm_client(
    *,
    streaming: bool = True,
    model_name: str | None = None,
    intent: str | None = None,
    stage: str | None = None,
    node_id: str | None = None,
    output_spec: Dict[str, Any] | None = None,
) -> BaseLLMClient:
    """Proxy for long-lived services; resolves the current request model per call."""
    from app.llm.request_scoped_client import RequestScopedLLMClient

    return RequestScopedLLMClient(
        streaming=streaming,
        model_name=model_name,
        intent=intent,
        stage=stage,
        node_id=node_id,
        output_spec=output_spec,
    )


def get_openai_compatible_client(
    *,
    api_key: str,
    base_url: str,
    model_name: str,
    streaming: bool = True,
    intent: str | None = None,
    stage: str | None = None,
    node_id: str | None = None,
    output_spec: Dict[str, Any] | None = None,
) -> BaseLLMClient:
    merged_output_spec: Dict[str, Any] = {}
    merged_output_spec.update(get_request_context())
    if isinstance(output_spec, dict):
        merged_output_spec.update(output_spec)
    _validate_api_key_ascii(api_key=api_key, provider="OpenAI Compatible")
    client = DefaultOpenAIClient(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        streaming=streaming,
        structured_output_mode=(
            str((merged_output_spec.get("configured_model") or {}).get("structured_output_mode") or "").strip()
            if isinstance(merged_output_spec.get("configured_model"), dict)
            and str((merged_output_spec.get("configured_model") or {}).get("structured_output_mode") or "").strip()
            else infer_structured_output_mode(
                provider_type="openai_compatible",
                model_name=model_name,
                settings=(merged_output_spec.get("configured_model") or {}).get("settings")
                if isinstance(merged_output_spec.get("configured_model"), dict)
                else None,
            )
        ),
    )
    return InstrumentedLLMClient(
        client,
        model_name=model_name,
        model_id=model_name,
        stage=stage,
        intent=intent,
        node_id=node_id,
        output_spec=merged_output_spec,
    )

def supports_json_schema() -> bool:
    # This means "the LLM layer can return a Pydantic-shaped result", not
    # necessarily native OpenAI/Azure response_format support.  Non-native
    # providers are handled by prompt-json fallback inside ainvoke_structured().
    return True
