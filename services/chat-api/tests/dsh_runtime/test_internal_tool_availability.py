"""Dependency admission must filter tools without losing independent capabilities."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.enterprise_capabilities.availability import checks
from app.enterprise_capabilities.availability.service import DEPENDENCIES, LOCAL_CAPABILITIES, InternalToolAvailability
from app.enterprise_capabilities.runtime import InternalCapabilityCatalog
from app.dsh_runtime.profile.tools import ToolProfileCompiler


def test_every_builtin_has_an_explicit_policy():
    refs = {item.capability_ref for item in InternalCapabilityCatalog().definitions()}
    assert refs <= set(DEPENDENCIES) | LOCAL_CAPABILITIES


def test_unavailable_dependency_does_not_hide_independent_tools(monkeypatch):
    for name in set(DEPENDENCIES.values()):
        monkeypatch.setattr(checks, name, AsyncMock(return_value=False))
    class EmptyCatalog:
        async def list_enabled(self, *args):
            return []
    tools = asyncio.run(ToolProfileCompiler(
        EmptyCatalog(), InternalCapabilityCatalog(), internal_availability=InternalToolAvailability(),
    ).compile(tenant_id='tenant-a', user_id='user-a'))
    refs = {tool.capability_ref for tool in tools}
    assert refs == {item.capability_ref for item in InternalCapabilityCatalog().definitions()} & LOCAL_CAPABILITIES
    checks.search.assert_awaited_once_with('tenant-a', 'user-a')


def test_checks_are_concurrent_and_never_cached_across_users(monkeypatch):
    calls = []
    entered = 0
    async def check(tenant_id, user_id):
        nonlocal entered
        entered += 1
        calls.append((tenant_id, user_id))
        await asyncio.sleep(0)
        assert entered >= 2
        return user_id == 'allowed'
    monkeypatch.setattr(checks, 'images', check)
    monkeypatch.setattr(checks, 'browser', check)
    refs = ['image.generate@v1', 'browser.task@v1']
    async def run():
        policy = InternalToolAvailability()
        assert await policy.unavailable(refs, 'a', 'allowed') == set()
        assert await policy.unavailable(refs, 'a', 'denied') == set(refs)
    asyncio.run(run())
    assert len(calls) == 4


def test_check_error_and_unknown_tool_fail_closed(monkeypatch):
    monkeypatch.setattr(checks, 'images', AsyncMock(side_effect=PermissionError('denied')))
    policy = InternalToolAvailability()
    assert asyncio.run(policy.available('image.generate@v1', 'a', 'u')) is False
    assert asyncio.run(policy.unavailable(['future.tool@v1'], 'a', 'u')) == {'future.tool@v1'}


def test_image_check_uses_execution_resolver(monkeypatch):
    with patch('app.services.image_generation.resolve_image_generation_model', new=AsyncMock(return_value=None)) as resolver:
        assert asyncio.run(checks.images('tenant-a', 'user-a')) is False
        resolver.assert_awaited_once_with('tenant-a', 'user-a')


def test_browser_requires_current_user_connection(monkeypatch):
    monkeypatch.setattr(checks.agent_registry, 'get', lambda user_id: object() if user_id == 'connected' else None)
    assert asyncio.run(checks.browser('a', 'connected')) is True
    assert asyncio.run(checks.browser('a', 'other')) is False


def test_invocation_rechecks_dependencies_before_handler():
    from app.enterprise_capabilities.runtime.service import InternalCapabilityService
    from types import SimpleNamespace
    handler = AsyncMock()
    registry = SimpleNamespace(require=lambda ref: handler)
    service = InternalCapabilityService(registry, availability=AsyncMock(return_value=False))
    with pytest.raises(RuntimeError, match='dependency'):
        asyncio.run(service.execute('browser.task@v1', {}, SimpleNamespace(tenant_id='a', user_id='u')))
    handler.assert_not_awaited()


def test_slow_dependency_is_bounded(monkeypatch):
    from app.enterprise_capabilities.availability import service
    monkeypatch.setattr(service, 'CHECK_TIMEOUT_SECONDS', 0.01)
    async def slow(*args):
        await asyncio.sleep(10)
    monkeypatch.setattr(checks, 'images', slow)
    assert asyncio.run(service.capability_available('image.generate@v1', 'a', 'u')) is False


def test_vision_selection_passes_tenant_and_user_to_policy(monkeypatch):
    from types import SimpleNamespace
    policy = SimpleNamespace(resolve_model_id=AsyncMock(return_value='vision-for-user'))
    monkeypatch.setattr(checks, 'get_product_extension', lambda: SimpleNamespace(model_access_policy=policy))
    resolver = AsyncMock(return_value={'id': 'vision-for-user'})
    monkeypatch.setattr(checks, 'get_model_config_by_capability', resolver)
    assert asyncio.run(checks.vision_model('tenant-a', 'user-a'))['id'] == 'vision-for-user'
    policy.resolve_model_id.assert_awaited_once_with(main_id='tenant-a', user_id='user-a', model_id=None, capability='vision')
    resolver.assert_awaited_once_with('vision-for-user', 'tenant-a', capability='vision')


def test_sandbox_requires_configured_token(monkeypatch):
    monkeypatch.setenv('MOVO_SANDBOX_MANAGER_URL', 'http://manager:8300')
    monkeypatch.delenv('MOVO_SANDBOX_MANAGER_TOKEN', raising=False)
    assert asyncio.run(checks.scripts('a', 'u')) is False
