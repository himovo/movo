import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import test from 'node:test'

import { NativePluginWeb } from '../src/native-plugin-web.mjs'
import { pluginSettingsView } from '../src/plugin-ui-settings.mjs'

function fixture() {
  const plugin = { installation_id: 'owned', name: 'example-bundle', version: '1.0.0', client_modules: [{ id: 'example-client' }], remote_endpoints: ['settings/update', 'settings/describe'] }
  const services = {
    configEditor: { configuration: () => [
      { entry: { options: { id: 'ui-settings', name: '@deepseek-ai/dsh-client-ui-settings' } } },
      { entry: { options: { id: 'model-gateway', name: 'private-model-gateway' } } },
    ] },
    pluginManager: { listBundles: async () => [
      { name: plugin.name, version: plugin.version, enabled: true, rows: [{ entryId: 'owned-settings' }], overrides: ['model-gateway'] },
      { name: 'another-bundle', version: '1.0.0', enabled: true, rows: [{ entryId: 'other-settings' }] },
    ] },
    settings: { describe: options => {
      assert.equal(options.redactSecrets, true)
      return [
        { ns: 'ui-settings', value: { enabled: true } },
        { ns: 'owned-settings', value: { enabled: true }, secrets: [{ path: ['apiKey'], set: true }] },
        { ns: 'other-settings', value: { private: 'OTHER_PLUGIN_VALUE' } },
        { ns: 'model-gateway', value: { private: 'HOST_CONFIGURATION' } },
      ]
    } },
    webServer: { port: 1 }, connection: {},
  }
  return { plugin, services, ctx: { get: name => services[name] } }
}

test('settings bootstrap reads only common UI and the active bundle namespaces', async () => {
  const { plugin, ctx } = fixture()
  const result = await pluginSettingsView(ctx, plugin)
  assert.deepEqual(result.namespaces.map(item => item.ns), ['ui-settings', 'owned-settings'])
  assert.equal(result.writable, false)
  assert.equal(result.hasDocument, false)
  assert.ok(!JSON.stringify(result).includes('MUST_NOT_LEAK'))
  assert.ok(!JSON.stringify(result).includes('OTHER_PLUGIN_VALUE'))
  assert.ok(!JSON.stringify(result).includes('HOST_CONFIGURATION'))
  assert.deepEqual(result.namespaces[1].secrets, [{ path: ['apiKey'], set: true }])
})

test('a stale or disabled bundle cannot read its former settings', async () => {
  const { plugin, ctx, services } = fixture()
  for (const state of [{ version: '2.0.0', enabled: true }, { version: '1.0.0', enabled: false }]) {
    services.pluginManager.listBundles = async () => [{ name: plugin.name, ...state, rows: [{ entryId: 'owned-settings' }] }]
    assert.deepEqual((await pluginSettingsView(ctx, plugin)).namespaces.map(item => item.ns), ['ui-settings'])
  }
})

test('HTTP bootstrap preserves native RPC correlation and rejects writes and malformed requests', async () => {
  const { plugin, ctx } = fixture()
  const bridge = new NativePluginWeb(ctx, [plugin])
  const server = createServer((request, response) => {
    bridge.proxy('owned', request.url, request, response).catch(() => { response.writeHead(500); response.end() })
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const base = `http://127.0.0.1:${server.address().port}`
  const post = (path, value) => fetch(`${base}${path}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(value) })
  const envelope = { type: 'client-request', rpcId: 'request-42', method: 'settings/describe', payload: [] }
  try {
    const response = await post('/api/settings/describe', envelope)
    assert.equal(response.status, 200)
    const body = await response.json()
    assert.equal(body.type, 'server-response')
    assert.equal(body.rpcId, 'request-42')
    assert.equal(body.result.ok, true)
    assert.deepEqual(body.result.value.namespaces.map(item => item.ns), ['ui-settings', 'owned-settings'])
    assert.equal(response.headers.get('set-cookie'), null)
    assert.equal((await post('/api/settings/describe', { ...envelope, method: 'settings/update' })).status, 400)
    assert.equal((await post('/api/settings/describe', { ...envelope, rpcId: '' })).status, 400)
    assert.equal((await post('/api/settings/update', envelope)).status, 403)
    assert.equal((await post('/api/settings/replace', envelope)).status, 403)
    assert.equal((await post('/api/settings/describe', { ...envelope, padding: 'x'.repeat(70_000) })).status, 413)
  } finally { await new Promise(resolve => server.close(resolve)) }
})
