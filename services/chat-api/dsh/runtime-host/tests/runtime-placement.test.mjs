import assert from 'node:assert/strict'
import { mkdtemp, rm } from 'node:fs/promises'
import { createServer } from 'node:http'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { setTimeout } from 'node:timers/promises'

import { RuntimeHttpServer } from '../src/runtime-http-server.mjs'
import { ndjson, TEMPORAL_CONTEXT } from './support/runtime-admission.mjs'

test('enterprise profile creates and restores a session without requesting a Docker lease', async () => {
  const root = await mkdtemp(join(tmpdir(), 'movo-host-placement-'))
  const previous = process.env.MOVO_SANDBOX_MANAGER_URL
  const previousToken = process.env.MOVO_SANDBOX_MANAGER_TOKEN
  process.env.MOVO_SANDBOX_MANAGER_TOKEN = 'test-token'
  const leases = []
  const dispatched = []
  let invokeTool = false
  let modelCall = 0
  const child = createServer(async (req, res) => {
    res.setHeader('content-type', 'application/json')
    if (req.url === '/health') return res.end(JSON.stringify({ ok: true, kernel: 'dsh' }))
    if (req.url.endsWith('/deferred-tool')) {
      let data = ''
      for await (const chunk of req) data += chunk
      dispatched.push(JSON.parse(data))
      return res.end(JSON.stringify({ value: { content: [{ type: 'text', text: 'ORDER_FOUND' }] } }))
    }
    req.resume()
    return res.end(JSON.stringify({ runtimeId: 'worker' }))
  })
  await new Promise(resolve => child.listen(0, '127.0.0.1', resolve))
  const manager = createServer((req, res) => {
    if (req.url === '/model') {
      req.resume()
      if (invokeTool) {
        invokeTool = false
        return ndjson(res, [{ type: 'tool-call', id: `lookup-call-${++modelCall}`, name: 'order_lookup', arguments: '{}' },
          { type: 'finish', reason: { kind: 'tool-calls' } }])
      }
      return ndjson(res, [{ type: 'text-delta', text: 'Hello from MOVO' },
        { type: 'finish', reason: { kind: 'stop' } }])
    }
    if (req.method === 'DELETE') return res.end('{}')
    leases.push(req.url)
    if (dispatched.length === 0 && leases.length === 1) {
      return res.end(JSON.stringify({
        lease_id: 'fixture', host: '127.0.0.1', port: child.address().port, token: 'child-token',
      }))
    }
    res.writeHead(503).end('lease unavailable')
  })
  await new Promise(resolve => manager.listen(0, '127.0.0.1', resolve))
  process.env.MOVO_SANDBOX_MANAGER_URL = `http://127.0.0.1:${manager.address().port}`
  let host
  const profile = {
    profileVersion: 'test', modelInstanceId: 'test', modelName: 'test',
    gatewayUrl: `http://127.0.0.1:${manager.address().port}/model`, accessToken: 'test', subjectUserId: 'test-user',
  }
  async function start() {
    host = new RuntimeHttpServer({ storageRoot: root })
    const { port } = await host.start()
    return async (path, body, status = 201) => {
      const response = await fetch(`http://127.0.0.1:${port}${path}`, {
        method: body === undefined ? 'GET' : 'POST',
        headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
      })
      const value = await response.json()
      assert.equal(response.status, status, JSON.stringify(value))
      return value
    }
  }
  try {
    let post = await start()
    const spec = {
      isolationKey: 'tenant:test:profile:test', profileVersion: 'test',
      modelProfile: { ...profile, runtimePlacement: 'enterprise-host', deferredPlugins: [{
        installation_id: 'fixture', name: 'fixture', version: '1.0.0', spec: 'fixture@1.0.0',
        source_scope: 'personal', tool_names: ['order_lookup'],
        deferred_tool_contracts: [{ name: 'order_lookup', description: 'Look up an order', schema: { type: 'object' } }],
      }] },
    }
    const runtime = await post('/v1/runtimes', spec)
    let path = `/v1/runtimes/${runtime.runtimeId}`
    const session = await post(`${path}/sessions`, { sessionId: 'hello', personalConversationKey: 'a'.repeat(64) })
    assert.equal(session.sessionId, 'hello')
    assert.ok(session.modelTools.includes('order_lookup'))
    for (const name of ['bash', 'write', 'edit', 'run_code']) assert.ok(!session.modelTools.includes(name), name)
    await post(`${path}/plugins/load`, { specifier: 'example' }, 403)
    await post(`${path}/sessions/hello/send`, {
      mode: 'prompt', temporalContext: TEMPORAL_CONTEXT,
      content: [{ type: 'text', data: { text: 'Hello' } }],
    }, 202)
    let events = []
    for (let attempt = 0; attempt < 100; attempt++) {
      const result = await post(`${path}/sessions/hello/events`, undefined, 200)
      events = result.events
      if (events.some(event => event.nativeType === 'turn/end')) break
      await setTimeout(50)
    }
    assert.ok(events.some(event => event.nativeType === 'assistant/chunk' &&
      event.data.chunk?.text === 'Hello from MOVO'))
    await host.stop()
    post = await start()
    const recovered = await post('/v1/runtimes', spec)
    path = `/v1/runtimes/${recovered.runtimeId}`
    assert.equal((await post(`${path}/sessions/hello/resume`, {}, 200)).sessionId, 'hello')
    assert.deepEqual(leases, [])
    for (let calls = 1; calls <= 2; calls++) {
      const previous = (await post(`${path}/sessions/hello/events`, undefined, 200))
        .events.filter(event => event.nativeType === 'turn/end').length
      invokeTool = true
      await post(`${path}/sessions/hello/send`, {
        mode: 'prompt', temporalContext: TEMPORAL_CONTEXT,
        content: [{ type: 'text', data: { text: 'Look up my order' } }],
      }, 202)
      let completed = false
      for (let attempt = 0; attempt < 100; attempt++) {
        const { events: current } = await post(`${path}/sessions/hello/events`, undefined, 200)
        if (current.filter(event => event.nativeType === 'turn/end').length > previous) {
          assert.ok(JSON.stringify(current).includes('ORDER_FOUND'))
          completed = true
          break
        }
        await setTimeout(50)
      }
      assert.equal(completed, true)
      assert.equal(dispatched.length, calls)
    }
    assert.deepEqual(dispatched, Array(2).fill({ name: 'order_lookup', args: {} }))
    assert.deepEqual(leases, ['/v1/plugin-runtimes'])
    await post('/v1/runtimes', { ...spec, isolationKey: 'legacy', modelProfile: profile }, 400)
    await post('/v1/runtimes', { ...spec, isolationKey: 'plugin',
      modelProfile: { ...profile, plugins: [{ name: 'fixture' }] },
    }, 400)
    assert.deepEqual(leases, Array(3).fill('/v1/plugin-runtimes'))
  } finally {
    await host?.stop()
    if (previous === undefined) delete process.env.MOVO_SANDBOX_MANAGER_URL
    else process.env.MOVO_SANDBOX_MANAGER_URL = previous
    if (previousToken === undefined) delete process.env.MOVO_SANDBOX_MANAGER_TOKEN
    else process.env.MOVO_SANDBOX_MANAGER_TOKEN = previousToken
    await new Promise(resolve => manager.close(resolve))
    await new Promise(resolve => child.close(resolve))
    await rm(root, { recursive: true, force: true })
  }
})
