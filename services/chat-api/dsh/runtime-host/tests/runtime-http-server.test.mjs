import assert from 'node:assert/strict'
import { mkdir, mkdtemp, rename, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

import { ASKAI_DSH_HOST_PROTOCOL_VERSION, ASKAI_DSH_KERNEL_VERSION } from '../src/host-protocol.mjs'
import { RuntimeHttpServer } from '../src/runtime-http-server.mjs'

const TOKEN = 'runtime-test-token-0123456789abcdef'

test('local Runtime Host uses a random loopback port and authenticates health', async () => {
  const root = await mkdtemp(join(tmpdir(), 'askai-runtime-http-'))
  const runtime = new RuntimeHttpServer({ storageRoot: root, authToken: TOKEN })
  try {
    const address = await runtime.start()
    assert.equal(address.host, '127.0.0.1')
    assert.ok(address.port > 0)
    const url = `http://${address.host}:${address.port}/health`
    assert.equal((await fetch(url)).status, 401)
    assert.equal((await fetch(url, { headers: { authorization: 'Bearer wrong-token' } })).status, 401)
    const response = await fetch(url, { headers: { authorization: `Bearer ${TOKEN}` } })
    assert.equal(response.status, 200)
    const health = await response.json()
    assert.equal(health.kernel, 'dsh')
    assert.equal(health.version, ASKAI_DSH_KERNEL_VERSION)
    assert.equal(health.protocolVersion, ASKAI_DSH_HOST_PROTOCOL_VERSION)
  } finally {
    await runtime.stop()
    await rm(root, { recursive: true, force: true })
  }
})

test('Runtime Host refuses an unauthenticated non-loopback bind address', () => {
  assert.throws(
    () => new RuntimeHttpServer({ host: '0.0.0.0', storageRoot: '/tmp' }),
    /network binding requires an authentication token/,
  )
})

test('Runtime Host permits an authenticated container-network bind address', () => {
  const runtime = new RuntimeHttpServer({ host: '0.0.0.0', storageRoot: '/tmp', authToken: TOKEN })
  assert.equal(runtime.host, '0.0.0.0')
})

test('Runtime Host delegates workspace lifecycle and cwd binding to native DSH registry', async () => {
  const root = await mkdtemp(join(tmpdir(), 'askai-runtime-workspace-'))
  const project = join(root, 'project-a')
  await mkdir(project)
  const runtime = new RuntimeHttpServer({ storageRoot: join(root, 'storage'), authToken: TOKEN })
  const headers = { authorization: `Bearer ${TOKEN}`, 'content-type': 'application/json' }
  const request = async (base, path, init = {}) => {
    const response = await fetch(`${base}${path}`, { ...init, headers: { ...headers, ...init.headers } })
    const body = await response.json()
    if (response.status >= 400) throw new Error(`${response.status}: ${body.error?.message}`)
    return body
  }
  try {
    const address = await runtime.start()
    const base = `http://${address.host}:${address.port}`
    const createdRuntime = await request(base, '/v1/runtimes', {
      method: 'POST', body: JSON.stringify({ isolationKey: 'workspace-e2e', profileVersion: 'rp-test' }),
    })
    const runtimePath = `/v1/runtimes/${createdRuntime.runtimeId}`
    const workspace = await request(base, `${runtimePath}/workspaces`, {
      method: 'POST', body: JSON.stringify({ path: project, title: 'Project A' }),
    })
    const duplicate = await request(base, `${runtimePath}/workspaces`, {
      method: 'POST', body: JSON.stringify({ path: project, title: 'Ignored duplicate title' }),
    })
    assert.equal(duplicate.workspaceId, workspace.workspaceId)
    assert.equal(duplicate.title, 'Project A')

    const renamed = await request(base, `${runtimePath}/workspaces/${workspace.workspaceId}`, {
      method: 'PATCH', body: JSON.stringify({ title: 'Renamed Project' }),
    })
    assert.equal(renamed.title, 'Renamed Project')
    const session = await request(base, `${runtimePath}/sessions`, {
      method: 'POST', body: JSON.stringify({ sessionId: 'workspace-session', presetId: 'code', workspaceId: workspace.workspaceId }),
    })
    assert.equal(session.workspaceId, workspace.workspaceId)
    assert.equal(session.permissionPreset, 'workspace-write')
    const listed = await request(base, `${runtimePath}/workspaces`)
    assert.deepEqual(listed.workspaces[0].sessionIds, ['workspace-session'])

    const rawCwd = await fetch(`${base}${runtimePath}/sessions`, {
      method: 'POST', headers, body: JSON.stringify({ sessionId: 'unsafe-session', presetId: 'code', cwd: project }),
    })
    assert.equal(rawCwd.status, 400)
    assert.match((await rawCwd.json()).error.message, /raw cwd is forbidden/)

    await rename(project, `${project}-missing`)
    assert.equal((await request(base, `${runtimePath}/workspaces`)).workspaces[0].status, 'missing-dir')
    const missingSession = await fetch(`${base}${runtimePath}/sessions`, {
      method: 'POST', headers, body: JSON.stringify({ sessionId: 'missing-session', presetId: 'code', workspaceId: workspace.workspaceId }),
    })
    assert.equal(missingSession.status, 400)

    const deleted = await request(base, `${runtimePath}/workspaces/${workspace.workspaceId}`, { method: 'DELETE' })
    assert.equal(deleted.deleted, true)
    assert.deepEqual((await request(base, `${runtimePath}/workspaces`)).workspaces, [])
  } finally {
    await runtime.stop()
    await rm(root, { recursive: true, force: true })
  }
})
