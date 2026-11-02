"""Availability governs profile admission independently from Skill execution."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services.presentation import availability as module
from app.dsh_runtime.profile.tools import ToolProfileCompiler
from app.enterprise_capabilities.runtime import InternalCapabilityCatalog


@pytest.mark.parametrize('settings', [None, {}, {'enabled': False}, {'enabled': True}])
def test_unconfigured_or_disabled_does_not_resolve_models(monkeypatch, settings):
    monkeypatch.setattr(module, 'get_presentation_generation_settings', AsyncMock(return_value=settings))
    resolver = AsyncMock()
    monkeypatch.setattr(module, 'get_model_config_by_capability', resolver)
    assert asyncio.run(module.presentation_available('tenant-a')) is False
    resolver.assert_not_awaited()


@pytest.mark.parametrize('missing', [None, 'chat', 'image_generation', 'vision'])
def test_all_selected_models_must_remain_available(monkeypatch, missing):
    monkeypatch.setattr(module, 'get_presentation_generation_settings', AsyncMock(return_value={
        'enabled': True, 'llm_model_id': 'content', 'image_model_id': 'image', 'vision_model_id': 'vision',
    }))
    async def resolve(model_id, tenant_id, *, capability):
        assert tenant_id == 'tenant-a'
        return None if capability == missing else {'id': model_id}
    monkeypatch.setattr(module, 'get_model_config_by_capability', resolve)
    assert asyncio.run(module.presentation_available('tenant-a')) is (missing is None)


def test_lookup_failure_is_closed(monkeypatch):
    monkeypatch.setattr(module, 'get_presentation_generation_settings', AsyncMock(side_effect=RuntimeError('offline')))
    assert asyncio.run(module.presentation_available('tenant-a')) is False


def test_profile_filters_only_builtin_presentation():
    class EmptyCatalog:
        async def list_enabled(self, tenant_id, user_id):
            return []
    async def compile_tools(available):
        return await ToolProfileCompiler(
            EmptyCatalog(), InternalCapabilityCatalog(),
            presentation_availability=AsyncMock(return_value=available),
        ).compile(tenant_id='tenant-a', user_id='user-a')
    enabled = {tool.name for tool in asyncio.run(compile_tools(True))}
    disabled = {tool.name for tool in asyncio.run(compile_tools(False))}
    assert enabled - disabled == {'presentation_create'}
    assert 'run_script' in disabled
