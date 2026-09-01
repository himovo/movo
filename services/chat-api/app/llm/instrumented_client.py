from __future__ import annotations

import time
import uuid
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Type

from pydantic import BaseModel

from app.core.config import get_settings
from app.core.tenant import resolve_main_id
from app.llm.base import BaseLLMClient
from app.llm.types import LLMResponse, Message
from app.infrastructure.observability.execution_trace import ensure_trace_id
from app.infrastructure.observability.spans import log_span
from app.infrastructure.request_context import get_request_context
from app.token_usage.models import TokenUsageRecord
from app.token_usage.sanitize import (
    build_request_payload,
    build_request_titles,
    build_response_payload,
    coerce_user_id,
    extract_prompt,
)


logger = logging.getLogger(__name__)


class InstrumentedLLMClient(BaseLLMClient):
    def __init__(
        self,
        inner: BaseLLMClient,
        *,
        model_name: str,
        model_id: str,
        stage: str | None = None,
        intent: str | None = None,
        node_id: str | None = None,
        output_spec: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._inner = inner
        self._model_name = str(model_name or "")
        self._model_id = str(model_id or model_name or "")
        self._stage = str(stage or "")
        self._intent = str(intent or "")
        self._node_id = str(node_id or "")
        self._output_spec = output_spec if isinstance(output_spec, dict) else {}

    async def ainvoke(self, messages: List[Message], **kwargs) -> LLMResponse:
        started_at = _now_ms()
        call_output_spec = self._resolved_output_spec()
        status = "completed"
        response: LLMResponse | None = None
        error_text = ""
        try:
            async with log_span("llm.request", stage=self._stage or "ainvoke", model=self._model_name, method="ainvoke", slow_ms=get_settings().LLM_SLOW_MS if hasattr(get_settings(), "LLM_SLOW_MS") else None):
                response = await self._inner.ainvoke(messages, **kwargs)
            return response
        except Exception as exc:
            status = "failed"
            error_text = str(exc)
            raise
        finally:
            self._submit_record(
                method="ainvoke",
                messages=messages,
                kwargs=kwargs,
                started_at=started_at,
                finished_at=_now_ms(),
                status=status,
                response=response,
                error_text=error_text,
                structured_output=None,
                output_spec=call_output_spec,
            )

    async def astream(self, messages: List[Message], **kwargs) -> AsyncGenerator[LLMResponse, None]:
        started_at = _now_ms()
        call_output_spec = self._resolved_output_spec()
        status = "completed"
        final_response: LLMResponse | None = None
        error_text = ""
        try:
            async with log_span("llm.stream", stage=self._stage or "astream", model=self._model_name, method="astream"):
                async for chunk in self._inner.astream(messages, **kwargs):
                    if chunk.usage or chunk.raw_response:
                        final_response = chunk
                    yield chunk
        except Exception as exc:
            status = "failed"
            error_text = str(exc)
            raise
        finally:
            self._submit_record(
                method="astream",
                messages=messages,
                kwargs=kwargs,
                started_at=started_at,
                finished_at=_now_ms(),
                status=status,
                response=final_response,
                error_text=error_text,
                structured_output=None,
                output_spec=call_output_spec,
            )

    async def ainvoke_structured(
        self,
        messages: List[Message],
        schema: Type[BaseModel],
        **kwargs,
    ) -> BaseModel:
        started_at = _now_ms()
        call_output_spec = self._resolved_output_spec()
        status = "completed"
        data: BaseModel | None = None
        error_text = ""
        try:
            async with log_span("llm.request", stage=self._stage or "ainvoke_structured", model=self._model_name, method="ainvoke_structured", schema=getattr(schema, "__name__", "")):
                data = await self._inner.ainvoke_structured(messages, schema, **kwargs)
            return data
        except Exception as exc:
            status = "failed"
            error_text = str(exc)
            raise
        finally:
            self._submit_record(
                method="ainvoke_structured",
                messages=messages,
                kwargs=kwargs,
                started_at=started_at,
                finished_at=_now_ms(),
                status=status,
                response=None,
                error_text=error_text,
                structured_output=data.model_dump() if data is not None and hasattr(data, "model_dump") else None,
                output_spec=call_output_spec,
            )

    def consume_invocation_record(self) -> Dict[str, Any] | None:
        return self._inner.consume_invocation_record()

    def _submit_record(
        self,
        *,
        method: str,
        messages: List[Message],
        kwargs: Dict[str, Any],
        started_at: int,
        finished_at: int,
        status: str,
        response: LLMResponse | None,
        error_text: str,
        structured_output: Dict[str, Any] | None,
        output_spec: Dict[str, Any],
    ) -> None:
        try:
            provider_meta = self._inner.consume_invocation_record() or {}
            response_usage = response.usage if response is not None else None
            usage = dict(provider_meta.get("usage") or response_usage or {})
            response_payload = provider_meta.get("response_payload")
            title_zh, title_en = build_request_titles(self._stage, self._intent)
            if structured_output is not None and response_payload is None:
                response_payload = structured_output
            if status != "completed" and error_text:
                response_payload = {"error": error_text}
            raw_response = response.raw_response if response is not None else None
            user_request_id = str(output_spec.get("message_id") or output_spec.get("request_id") or "").strip()
            record = TokenUsageRecord(
                request_id="llm_%s" % uuid.uuid4().hex[:20],
                user_request_id=user_request_id,
                main_id=resolve_main_id(output_spec.get("main_id") or output_spec.get("mainId")),
                user_id=coerce_user_id(output_spec.get("user_id")),
                session_id=str(output_spec.get("session_id") or output_spec.get("task_id") or "").strip(),
                trace_id=ensure_trace_id(output_spec),
                stage=self._stage or method,
                intent=self._intent,
                node_id=self._node_id or str(output_spec.get("current_task_node_id") or ""),
                status=status,
                model_name=str(provider_meta.get("model_name") or self._model_name),
                model_id=str(provider_meta.get("model_id") or self._model_id),
                prompt=extract_prompt(messages),
                request_title_zh=title_zh,
                request_title_en=title_en,
                request_payload=build_request_payload(messages=messages, kwargs=kwargs),
                response_payload=build_response_payload(response_payload or raw_response),
                start_time=started_at,
                end_time=finished_at,
                total_tokens=int(usage.get("total_tokens") or 0),
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
            )
            from app.infrastructure.runtime_services import token_usage_dispatcher

            submitted = token_usage_dispatcher.submit(record)
            if not submitted:
                logger.warning(
                    "token usage submit skipped",
                    extra={
                        "event": "token_usage.submit_skipped",
                        "llm_request_id": record.request_id,
                        "stage": record.stage,
                        "user_id": record.user_id,
                        "session_id": record.session_id,
                    },
                )
            elif get_settings().DEBUG:
                logger.debug(
                    "token usage submitted",
                    extra={
                        "event": "token_usage.submitted",
                        "llm_request_id": record.request_id,
                        "stage": record.stage,
                        "trace_id": record.trace_id,
                        "user_id": record.user_id,
                        "total_tokens": record.total_tokens,
                    },
                )
        except Exception as exc:
            logger.warning("token usage submit failed", extra={"event": "token_usage.submit_failed", "error": str(exc)})

    def _resolved_output_spec(self) -> Dict[str, Any]:
        resolved = dict(self._output_spec or {})
        dynamic = get_request_context()
        for key, value in dynamic.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            resolved[key] = value
        return resolved


def _now_ms() -> int:
    return int(time.time() * 1000)
