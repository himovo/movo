import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import test from 'node:test'

import { ContainerPluginRuntimePool, rewritePluginProfile } from '../src/container-plugin-runtime.mjs'
import { preparePluginCredentialRefresh } from '../src/plugin-credential-relay.mjs'

test('container profile only receives scoped relay credentials', () => {
  const original = {
    gatewayUrl: 'http://chat-api:8000/internal/dsh/model/generate',
    accessToken: 'original-secret',
    toolProfile: {
      gatewayUrl: 'http://chat-api:8000/internal/dsh/tools',
      accessToken: 'tool-secret',
      tools: [],
    },
    bundleGatewayUrl: 'http://chat-api:8000/internal/dsh/skill-bundles',
    pluginGatewayUrl: 'http://chat-api:8000/internal/dsh/plugin-archives',
  }
  const rewritten = rewritePluginProfile(original, { lease_id: 'a'.repeat(32), token: 'scoped-token' })
  assert.equal(rewritten.accessToken, 'scoped-token')
  assert.equal(rewritten.toolProfile.accessToken, 'scoped-token')
  assert.match(rewritten.gatewayUrl, /sandbox-relay\/a{32}\/model$/)
  assert.match(rewritten.toolProfile.gatewayUrl, /sandbox-relay\/a{32}\/tools$/)
  assert.equal(original.accessToken, 'original-secret')
  assert.equal(original.toolProfile.accessToken, 'tool-secret')
})

test('refreshed credentials preserve the plugin relay and update the parent gateway token', () => {
  const entry = {
    lease_id: 'b'.repeat(32), token: 'scoped-token',
    profile: {
      gatewayUrl: 'http://chat-api:8000/internal/dsh/model/generate', accessToken: 'old-model-token',
      toolProfile: { gatewayUrl: 'http://chat-api:8000/internal/dsh/tools', accessToken: 'old-tool-token' },
    },
  }
  const model = preparePluginCredentialRefresh(entry, 'model', {
    gatewayUrl: 'http://chat-api:8000/internal/dsh/model/generate', accessToken: 'new-model-token',
  })
  assert.match(model.forwarded.gatewayUrl, /sandbox-relay\/b{32}\/model$/)
  assert.equal(model.forwarded.accessToken, 'scoped-token')
  assert.equal(model.profile.accessToken, 'new-model-token')
  assert.equal(entry.profile.accessToken, 'old-model-token')

  entry.profile = model.profile
  const tool = preparePluginCredentialRefresh(entry, 'tool', { accessToken: 'new-tool-token' })
  assert.equal(tool.forwarded.accessToken, 'scoped-token')
  assert.equal(tool.profile.toolProfile.accessToken, 'new-tool-token')
  assert.equal(entry.profile.toolProfile.accessToken, 'old-tool-token')
})

test('plugin Runtime forwards refreshed model credentials through its scoped relay', async () => {
  const received = []
  const child = createServer(async (request, response) => {
    let result = {}
    if (request.url === '/health') result = { ok: true, kernel: 'dsh' }
    else if (request.method === 'POST') result = { runtimeId: 'runtime-1' }
    else if (request.method === 'GET') result = { runtimeId: 'runtime-1', isolationKey: 'test', profileVersion: 'test' }
    else if (request.method === 'PUT') {
      let body = ''
      for await (const chunk of request) body += chunk
      received.push(JSON.parse(body))
      result = { refreshed: true }
    }
    response.writeHead(200, { 'content-type': 'application/json' })
    response.end(JSON.stringify(result))
  })
  await new Promise(resolve => child.listen(0, '127.0.0.1', resolve))
  const manager = createServer((request, response) => {
    response.writeHead(200, { 'content-type': 'application/json' })
    response.end(JSON.stringify(request.method === 'POST' ? {
      lease_id: 'c'.repeat(32), host: '127.0.0.1', port: child.address().port, token: 'scoped-token',
    } : { disposed: true }))
  })
  await new Promise(resolve => manager.listen(0, '127.0.0.1', resolve))
  const pool = new ContainerPluginRuntimePool({ managerUrl: `http://127.0.0.1:${manager.address().port}`, managerToken: 'manager-token' })
  let front
  try {
    const runtime = await pool.create({
      isolationKey: 'test', profileVersion: 'test',
      modelProfile: { gatewayUrl: 'http://chat-api:8000/internal/dsh/model/generate', accessToken: 'old-token' },
    })
    front = createServer((request, response) => pool.forward(pool.get(runtime.runtimeId), request, response))
    await new Promise(resolve => front.listen(0, '127.0.0.1', resolve))
    const response = await fetch(`http://127.0.0.1:${front.address().port}/v1/runtimes/runtime-1/model-credential`, {
      method: 'PUT', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ gatewayUrl: 'http://chat-api:8000/internal/dsh/model/generate', accessToken: 'fresh-token' }),
    })
    assert.equal(response.status, 200)
    assert.deepEqual(received, [{
      gatewayUrl: `http://sandbox-gateway:8101/v1/sandbox-relay/${'c'.repeat(32)}/model`,
      accessToken: 'scoped-token',
    }])
  } finally {
    await pool.disposeAll()
    if (front) await new Promise(resolve => front.close(resolve))
    await new Promise(resolve => manager.close(resolve))
    await new Promise(resolve => child.close(resolve))
  }
})

test('transient startup refusal retains the relay lease after the child becomes ready', async () => {
  const child = createServer((request, response) => {
    response.writeHead(200, { 'content-type': 'application/json' })
    response.end(JSON.stringify(request.url === '/health'
      ? { ok: true, kernel: 'dsh' }
      : { runtimeId: 'runtime-after-retry', isolationKey: 'startup-retry', profileVersion: 'test' }))
  })
  const reservation = createServer()
  await new Promise(resolve => reservation.listen(0, '127.0.0.1', resolve))
  const port = reservation.address().port
  await new Promise(resolve => reservation.close(resolve))
  const manager = createServer((request, response) => {
    response.writeHead(200, { 'content-type': 'application/json' })
    response.end(JSON.stringify(request.method === 'POST' ? {
      lease_id: 'd'.repeat(32), host: '127.0.0.1', port, token: 'scoped-token',
    } : { disposed: true }))
  })
  await new Promise(resolve => manager.listen(0, '127.0.0.1', resolve))
  const pool = new ContainerPluginRuntimePool({ managerUrl: `http://127.0.0.1:${manager.address().port}`, managerToken: 'manager-token' })
  let front
  const startChild = setTimeout(() => child.listen(port, '127.0.0.1'), 500)
  try {
    await pool.create({ isolationKey: 'startup-retry', profileVersion: 'test', modelProfile: {} })
    front = createServer((request, response) => pool.relay(request, response))
    await new Promise(resolve => front.listen(0, '127.0.0.1', resolve))
    const response = await fetch(`http://127.0.0.1:${front.address().port}/v1/sandbox-relay/${'d'.repeat(32)}/model`, {
      headers: { authorization: 'Bearer scoped-token' },
    })
    assert.equal(response.status, 405)
  } finally {
    clearTimeout(startChild)
    await pool.disposeAll()
    if (front) await new Promise(resolve => front.close(resolve))
    await new Promise(resolve => manager.close(resolve))
    if (child.listening) await new Promise(resolve => child.close(resolve))
  }
})
