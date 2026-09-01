from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Type

from pydantic import BaseModel

from app.llm.base import BaseLLMClient
from app.llm.types import LLMResponse, Message


class RequestScopedLLMClient(BaseLLMClient):
    """Resolve the concrete provider at invocation time from request context."""

    def __init__(
        self,
        *,
        streaming: bool = True,
        model_name: str | None = None,
        intent: str | None = None,
        stage: str | None = None,
        node_id: str | None = None,
        output_spec: Dict[str, Any] | None = None,
    ) -> None:
        self._streaming = bool(streaming)
        self._model_name = model_name
        self._intent = intent
        self._stage = stage
        self._node_id = node_id
        self._output_spec = dict(output_spec or {})
        # Never retain decrypted provider credentials or a request's selected
        # model inside a process-wide service instance.
        self._output_spec.pop("configured_model", None)

    def _resolve(self) -> BaseLLMClient:
        from app.llm.factory import get_llm_client

        return get_llm_client(
            streaming=self._streaming,
            model_name=self._model_name,
            intent=self._intent,
            stage=self._stage,
            node_id=self._node_id,
            output_spec=self._output_spec,
        )

    async def ainvoke(self, messages: List[Message], **kwargs: Any) -> LLMResponse:
        return await self._resolve().ainvoke(messages, **kwargs)

    async def astream(self, messages: List[Message], **kwargs: Any) -> AsyncGenerator[LLMResponse, None]:
        client = self._resolve()
        async for chunk in client.astream(messages, **kwargs):
            yield chunk

    async def ainvoke_structured(
        self,
        messages: List[Message],
        schema: Type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        return await self._resolve().ainvoke_structured(messages, schema, **kwargs)
