import assert from 'node:assert/strict'
import test from 'node:test'

import { allowedPluginUiRequest, safePluginRoutes } from '../src/plugin-ui-route-policy.mjs'

test('plugin UI policy permits only native static assets and attributed plugin routes', () => {
  const routes = [{ kind: 'prefix', path: '/media-desk' }, { kind: 'exact', path: '/papers/report' }]
  const allow = (method, path) => allowedPluginUiRequest({ method, path, routes })
  assert.equal(allow('GET', '/'), true)
  assert.equal(allow('GET', '/plugins/media-desk/client.js'), true)
  assert.equal(allow('GET', '/assets/index.js'), true)
  assert.equal(allow('POST', '/media-desk/generate'), true)
  assert.equal(allow('GET', '/papers/report'), true)
  assert.equal(allow('GET', '/papers/report/export'), false)
  assert.equal(allow('POST', '/api/session.create'), false)
  assert.equal(allow('GET', '/v1/runtimes'), false)
  assert.equal(allow('GET', '/other-plugin/data'), false)
})

test('reserved and ambiguous paths cannot be claimed by a plugin', () => {
  const routes = [
    { kind: 'prefix', path: '/api' },
    { kind: 'prefix', path: '/assets/private' },
    { kind: 'prefix', path: '/media-desk/../api' },
    { kind: 'prefix', path: '/media-desk%2fapi' },
  ]
  assert.deepEqual(safePluginRoutes(routes), [])
  for (const path of ['/api/session.create', '/media-desk/../api', '/media-desk%2fapi', '//api']) {
    assert.equal(allowedPluginUiRequest({ method: 'POST', path, routes }), false)
  }
})

test('plugin UI permits only attributed unary Remote endpoints', () => {
  const allow = (method, path) => allowedPluginUiRequest({
    method, path, remoteEndpoints: ['mediaDesk/list', 'mediaDesk/create'],
  })
  assert.equal(allow('POST', '/api/mediaDesk/list'), true)
  assert.equal(allow('POST', '/api/session/list'), true)
  assert.equal(allow('POST', '/api/session/search'), true)
  assert.equal(allow('POST', '/api/session/follow'), true)
  assert.equal(allow('POST', '/api/session/control'), true)
  assert.equal(allow('POST', '/api/mediaDesk/create'), true)
  assert.equal(allow('GET', '/api/mediaDesk/list'), false)
  assert.equal(allow('POST', '/api/pluginManager/remove'), false)
  assert.equal(allow('POST', '/api/session/create'), false)
  assert.equal(allow('POST', '/api/mediaDesk/list/extra'), false)
  assert.equal(allow('POST', '/api/remote.mux'), false)
})

test('plugin UI confines generic API registrations to the selected package namespace', () => {
  const allow = (method, path) => allowedPluginUiRequest({
    method, path, pluginName: 'sample-plugin', hasGenericApiRoute: true,
  })
  assert.equal(allow('POST', '/api/sample-plugin/list'), true)
  assert.equal(allow('GET', '/api/sample-plugin/item'), true)
  assert.equal(allow('POST', '/api/other-plugin/list'), false)
  assert.equal(allow('POST', '/api/session.create'), false)
  assert.equal(allowedPluginUiRequest({ method: 'POST', path: '/api/sample-plugin/list',
    pluginName: 'sample-plugin' }), false)
})
