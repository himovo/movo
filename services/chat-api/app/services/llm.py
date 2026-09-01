from typing import Any, Iterable, List

from app.llm.factory import get_llm_client
from app.llm.types import Message, Role


def _coerce_role(value: Any) -> Role:
    try:
        return value if isinstance(value, Role) else Role(str(value or "assistant"))
    except Exception:
        return Role.ASSISTANT


def _normalize_messages(messages: Iterable[Any]) -> List[Message]:
    normalized: List[Message] = []
    for item in list(messages or []):
        if isinstance(item, Message):
            normalized.append(item)
            continue
        if isinstance(item, dict):
            normalized.append(
                Message(
                    role=_coerce_role(item.get("role")),
                    content=item.get("content"),
                    name=item.get("name"),
                    tool_calls=item.get("tool_calls"),
                    tool_call_id=item.get("tool_call_id"),
                )
            )
            continue
        raise TypeError(f"Unsupported message type: {type(item)!r}")
    return normalized

class LLMService:
    def __init__(self, *, intent: str = "chat"):
        self.intent = intent

    async def chat_stream(self, messages: list, temperature: float | None = 0.2):
        """
        Stream chat completions from LLM.
        """
        try:
            client = get_llm_client(streaming=True, intent=self.intent)
            kwargs = {}
            if temperature is not None:
                kwargs["temperature"] = temperature
            async for chunk in client.astream(_normalize_messages(messages), **kwargs):
                if chunk.message.content is not None:
                    yield str(chunk.message.content)
        except Exception as e:
            yield f"Error: {str(e)}"

    async def chat_complete(self, messages: list, temperature: float | None = 0.2) -> str:
        try:
            client = get_llm_client(streaming=False, intent=self.intent)
            kwargs = {}
            if temperature is not None:
                kwargs["temperature"] = temperature
            resp = await client.ainvoke(_normalize_messages(messages), **kwargs)
            return str(resp.message.content or "")
        except Exception as e:
            return f"Error: {str(e)}"

llm_service = LLMService()
