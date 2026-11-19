import assert from 'node:assert/strict'
import test from 'node:test'

import { buildAskaiHostOverlay } from '../src/official-host/overlay.mjs'

const options = {
  storageRoot: '/tmp/movo-overlay-test',
  askaiPresetRoot: '/tmp/movo-overlay-test/presets',
}

test('native DSH web services are composed only for plugin runtimes', () => {
  const base = buildAskaiHostOverlay(options)
  const plugin = buildAskaiHostOverlay({ ...options, pluginWeb: true })
  const rows = overlay => new Map(overlay.flatMap(patch => patch.insert ?? []).map(row => [row.id, row]))

  assert.equal(rows(base).has('plugin-web-server'), false)
  assert.equal(rows(base).has('plugin-client-modules'), false)
  assert.equal(rows(plugin).get('plugin-web-server').name, '@deepseek-ai/dsh-host-webserver')
  assert.equal(rows(plugin).get('plugin-web-server').config.host, '127.0.0.1')
  assert.equal(new URL(rows(plugin).get('plugin-web-startup').name).protocol, 'file:')
  assert.equal(rows(plugin).get('plugin-client-modules').name, '@deepseek-ai/dsh-client-modules')
  assert.equal([...rows(plugin).values()].filter(row => row.name === '@deepseek-ai/dsh-api-session-controller').length, 0)
  assert.equal([...rows(plugin).values()].filter(row => row.name === '@deepseek-ai/dsh-api-workspace-controller').length, 0)
  assert.equal([...rows(plugin).values()].filter(row => row.name === '@deepseek-ai/dsh-client-connection').length, 0)
  const model = buildAskaiHostOverlay({ ...options, pluginWeb: true, pluginModelName: 'configured-model' })
  assert.deepEqual(model.find(patch => patch.id === 'agent-default-model').config, {
    provider: 'askai-model-gateway', model: 'configured-model',
  })
})
