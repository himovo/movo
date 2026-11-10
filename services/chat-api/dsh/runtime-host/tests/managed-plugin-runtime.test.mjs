import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { createServer } from 'node:http'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

import { RuntimeHttpServer } from '../src/runtime-http-server.mjs'

const fixture = join(dirname(fileURLToPath(import.meta.url)), 'fixtures', 'managed-plugin')

async function request(base, path, method = 'GET', body) {
  const response = await fetch(`${base}${path}`, {
    method,
    headers: { 'content-type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  const value = await response.json()
  assert.ok(response.ok, `${response.status}: ${JSON.stringify(value)}`)
  return value
}

test('managed plugin activates only for its Runtime and preserves Session handoff', async () => {
  const root = await mkdtemp(join(tmpdir(), 'movo-managed-plugin-'))
  const source = join(root, 'package')
  const archive = join(root, 'movo-dsh-test-bundle-1.0.0.tgz')
  await mkdir(source)
  await cp(fixture, source, { recursive: true })
  execFileSync('tar', ['-czf', archive, 'package'], { cwd: root })
  const archiveBytes = await readFile(archive)
  const digest = createHash('sha256').update(archiveBytes).digest('hex')
  const archiveId = 'a'.repeat(32)
  const gateway = createServer((request, response) => {
    if (request.url === '/model') {
      assert.equal(request.headers.authorization, 'Bearer test')
      response.writeHead(200, { 'content-type': 'application/x-ndjson' })
      response.end(`${JSON.stringify({ type: 'text-delta', text: 'MODEL_GATEWAY_OK' })}\n${JSON.stringify({ type: 'finish', reason: { kind: 'stop' } })}\n`)
      return
    }
    if (request.url?.startsWith(`/${archiveId}?digest=${digest}`)) {
      response.writeHead(200, { 'content-type': 'application/gzip' })
      response.end(archiveBytes)
    } else { response.writeHead(404); response.end() }
  })
  await new Promise(resolve => gateway.listen(0, '127.0.0.1', resolve))
  const gatewayUrl = `http://127.0.0.1:${gateway.address().port}`
  const host = new RuntimeHttpServer({ storageRoot: join(root, 'storage') })
  try {
    const { port } = await host.start()
    const base = `http://127.0.0.1:${port}`
    const materialized = await request(base, '/v1/plugin-archives/materialize', 'POST', {
      archiveId, digest, gatewayUrl,
    })
    assert.equal((await readFile(materialized.spec)).compare(archiveBytes), 0)
    await writeFile(materialized.spec, 'damaged cache')
    const repaired = await request(base, '/v1/plugin-archives/materialize', 'POST', {
      archiveId, digest, gatewayUrl,
    })
    assert.equal((await readFile(repaired.spec)).compare(archiveBytes), 0)
    await rm(materialized.spec)
    const plain = await request(base, '/v1/runtimes', 'POST', {
      isolationKey: 'plain-user', profileVersion: 'test',
    })
    const managed = await request(base, '/v1/runtimes', 'POST', {
      isolationKey: 'managed-user', profileVersion: 'test',
      modelProfile: {
        profileVersion: 'test', modelInstanceId: 'test', modelName: 'test',
        gatewayUrl: `${gatewayUrl}/model`, accessToken: 'test',
        pluginGatewayUrl: gatewayUrl,
        plugins: [{
          installation_id: 'b'.repeat(24),
          name: 'movo-dsh-test-bundle', version: '1.0.0',
          spec: 'uploaded-plugin', archive_id: archiveId, archive_digest: digest,
          source_scope: 'personal', tool_names: ['movo_plugin_smoke'],
          commands: [{ name: 'movo-smoke', definitionId: 'movo-plugin-smoke-command' }],
          web_routes: [{ kind: 'prefix', path: '/movo-fixture' }],
          client_modules: [{ id: 'movo-dsh-test-bundle', rev: 'fixture' }],
        }],
      },
    })
    const managedPath = `/v1/runtimes/${managed.runtimeId}`
    const plainPath = `/v1/runtimes/${plain.runtimeId}`
    const discovered = await request(base, '/v1/runtimes?isolationKey=managed-user')
    assert.equal(discovered.runtime.modelInstanceId, 'test')
    const active = await request(base, `${managedPath}/managed-plugins`)
    assert.ok(active.bundles.some(bundle => bundle.name === 'movo-dsh-test-bundle' && bundle.enabled))
    assert.ok(active.globalTools.includes('movo_plugin_smoke'))
    assert.ok(active.capabilities?.webRoutes?.some(route => route.path === '/movo-fixture') ||
      active.webRoutes?.some(route => route.path === '/movo-fixture'))
    const uiBase = `${base}${managedPath}/plugin-ui/${'b'.repeat(24)}`
    const uiRoute = await fetch(`${uiBase}/movo-fixture/ready`)
    assert.equal(uiRoute.status, 200)
    assert.deepEqual(await uiRoute.json(), { marker: 'FIXTURE_UI_READY' })
    {
      const nativePage = await fetch(`${uiBase}/`)
      assert.equal(nativePage.status, 200)
      const html = await nativePage.text()
      const match = html.match(/globalThis\["__DSH_BOOT__"\] = (.*?)<\/script>/s)
      assert.ok(match, 'official DSH boot manifest is present')
      const boot = JSON.parse(match[1])
      assert.ok(boot.entries.some(entry => entry.id === '@deepseek-ai/dsh-client-ui-renderer'))
      assert.ok(boot.entries.some(entry => entry.id === 'movo-dsh-test-bundle'))
      assert.ok(boot.entries.some(entry => entry.id === 'movo-plugin-client-shell'))
      assert.ok(!boot.entries.some(entry => entry.id === '@deepseek-ai/dsh-client-ui-plugin-manager'))
    }
    const modelResponse = await fetch(`${uiBase}/movo-fixture/model`)
    const modelBody = await modelResponse.text()
    assert.equal(modelResponse.status, 200, modelBody)
    assert.deepEqual(JSON.parse(modelBody), {
      text: 'MODEL_GATEWAY_OK', selection: { provider: 'askai-model-gateway', model: 'test' },
    })
    const uiIndex = await fetch(`${uiBase}/`)
    assert.equal(uiIndex.status, 200)
    const uiHtml = await uiIndex.text()
    assert.match(uiHtml, /DeepSeek Harness/)
    assert.match(uiHtml, /movo-plugin-client-shell/)
    assert.equal((await fetch(`${uiBase}/movo-client-shell.js`)).status, 200)
    assert.equal((await fetch(`${uiBase}/unapproved-client-module.js`)).status, 403)
    assert.equal((await fetch(`${uiBase}/api/session.create`)).status, 403)
    const other = await request(base, `${plainPath}/managed-plugins`)
    assert.ok(other.bundles.every(bundle => bundle.name !== 'movo-dsh-test-bundle'))

    const plainSession = await request(base, `${plainPath}/sessions`, 'POST', { sessionId: 'plain-session' })
    assert.ok(!plainSession.capabilityTools.includes('movo_plugin_smoke'))
    const continued = await request(base, `${managedPath}/sessions`, 'POST', {
      sessionId: 'managed-session', seedRuntimeId: plain.runtimeId, seedSessionId: 'plain-session',
    })
    assert.equal(continued.sessionId, 'managed-session')
    assert.ok(continued.capabilityTools.includes('movo_plugin_smoke'), JSON.stringify(continued.capabilityTools))
    const commandId = `dsh_plugin_command:${'b'.repeat(24)}:${Buffer.from('movo-smoke').toString('base64url')}`
    const command = await request(base, `${managedPath}/sessions/managed-session/plugin-command`, 'POST', {
      selectedId: commandId, line: '/movo-smoke hello',
    })
    assert.equal(command.result.kind, 'success')
    assert.equal(command.result.text, 'MOVO_COMMAND_EXECUTED hello')
    const commandEvents = await request(base, `${managedPath}/sessions/managed-session/events`)
    assert.ok(commandEvents.events.some(event => event.nativeType === 'command/run'))
    assert.ok(commandEvents.events.some(event => event.nativeType === 'command/done'))
    const wrongProfile = await fetch(`${base}${plainPath}/sessions/plain-session/plugin-command`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ selectedId: commandId, line: '/movo-smoke hello' }),
    })
    assert.equal(wrongProfile.ok, false)
    const back = await request(base, `${plainPath}/sessions`, 'POST', {
      sessionId: 'plain-successor', seedRuntimeId: managed.runtimeId, seedSessionId: 'managed-session',
    })
    assert.equal(back.sessionId, 'plain-successor')
  } finally {
    await host.stop()
    await new Promise(resolve => gateway.close(resolve))
    await rm(root, { recursive: true, force: true })
  }
})
