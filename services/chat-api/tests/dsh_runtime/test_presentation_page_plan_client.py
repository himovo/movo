"""Image-native page planning must work with a chat-only content model."""
import asyncio
from unittest.mock import AsyncMock

from app.services.presentation.image_native import page_plan_client as module
from app.llm.types import LLMResponse, Message, Role
from app.llm.configured_models import set_configured_model_context, reset_configured_model_context


def test_text_planning_uses_selected_content_model_without_vision(monkeypatch):
    selected = {'id': 'content-model', 'capabilities': ['chat']}
    client = AsyncMock()
    client.ainvoke.return_value = LLMResponse(message=Message(role=Role.ASSISTANT, content='{"page_id":"p1"}'))
    captured = []
    def build(config, **kwargs):
        captured.append(config)
        return client
    monkeypatch.setattr('app.llm.factory.build_llm_client_from_config', build)
    token = set_configured_model_context(selected)
    try:
        result = asyncio.run(module.PagePlanClient().call_json(prompt='Plan slide', stage='page-plan'))
    finally:
        reset_configured_model_context(token)
    assert captured == [selected]
    assert result == {'page_id': 'p1'}
    assert client.ainvoke.call_args.args[0][0].content == 'Plan slide'
