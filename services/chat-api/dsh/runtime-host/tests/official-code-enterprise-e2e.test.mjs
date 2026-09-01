import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { access, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

import { KernelRuntime } from '../src/kernel-runtime.mjs'

const MODEL_TOKEN = 'model-token'
const TOOL_TOKEN = 'tool-token'

function ndjson(response, events) {
  const body = events.map(event => JSON.stringify(event)).join('\n') + '\n'
  response.writeHead(200, { 'content-type': 'application/x-ndjson' })
  response.end(body)
}

async function bodyOf(request) {
  const chunks = []
  for await (const chunk of request) chunks.push(chunk)
  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}

async function waitFor(predicate, timeoutMs = 5000) {
  const started = Date.now()
  while (!predicate()) {
    if (Date.now() - started > timeoutMs) throw new Error('timed out waiting for Code E2E')
    await new Promise(resolve => setTimeout(resolve, 20))
  }
}

function modelProfile(baseUrl) {
  const search = {
    name: 'askai_mcp_search', version: 'search-v1', source_type: 'mcp',
    external_tool_id: 'search', mcp_tool_name: 'search', description: 'Search enterprise records',
    input_schema: {
      type: 'object', properties: { query: { type: 'string' } }, required: ['query'], additionalProperties: false,
    },
    output_schema: {}, output_validation: 'none', risk_level: 'read', approval_required: false,
    required_scopes: ['tools:read'], timeout_ms: 15000,
  }
  return {
    profileVersion: 'profile-code-e2e', modelInstanceId: 'managed-model', modelName: 'managed-model',
    gatewayUrl: `${baseUrl}/model`, accessToken: MODEL_TOKEN,
    toolProfile: {
      gatewayUrl: `${baseUrl}/tools`, accessToken: TOOL_TOKEN,
      tools: [search], nativeReplacements: [],
    },
  }
}

test('one official Code turn searches enterprise data, reads, writes, and tests in DSH', async () => {
  const root = await mkdtemp(join(tmpdir(), 'askai-code-enterprise-e2e-'))
  await writeFile(join(root, 'input.txt'), 'workspace fact\n')
  await writeFile(join(root, 'AGENTS.md'), 'ASKAI_E2E_REPOSITORY_INSTRUCTION: preserve the verified behavior.\n')
  await mkdir(join(root, '.agents', 'skills', 'verified-workflow'), { recursive: true })
  await writeFile(
    join(root, '.agents', 'skills', 'verified-workflow', 'SKILL.md'),
    '---\nname: verified-workflow\ndescription: Use the verified repository workflow.\n---\n# Verified workflow\nFollow the repository checks.\n',
  )
  const modelCalls = []
  const enterpriseCalls = []
  const server = createServer(async (request, response) => {
    const body = await bodyOf(request)
    if (request.url === '/model') {
      assert.equal(request.headers.authorization, `Bearer ${MODEL_TOKEN}`)
      modelCalls.push(body)
      const calls = [
        ['initial', 'bash', { command: "node -e \"const fs=require('fs'); process.exit(fs.existsSync('output.txt') && fs.statSync('output.txt').size > 0 ? 0 : 1)\"", description: 'Reproduce missing output failure' }],
        ['search', 'askai_mcp_search', { query: 'policy' }],
        ['read', 'read', { file_path: 'input.txt' }],
        ['write', 'write', { file_path: 'output.txt', content: 'workspace fact\nenterprise fact\n' }],
        ['verify', 'bash', { command: "node -e \"const fs=require('fs'); process.exit(fs.existsSync('output.txt') && fs.statSync('output.txt').size > 0 ? 0 : 1)\"", description: 'Verify generated output' }],
      ]
      const next = calls[modelCalls.length - 1]
      if (next !== undefined) return ndjson(response, [
        { type: 'tool-call', id: next[0], name: next[1], arguments: JSON.stringify(next[2]) },
        { type: 'finish', reason: { kind: 'tool-calls' } },
      ])
      return ndjson(response, [
        { type: 'text-delta', text: 'Code workflow completed.' },
        { type: 'finish', reason: { kind: 'stop' } },
      ])
    }
    if (request.url === '/tools/execute') {
      assert.equal(request.headers.authorization, `Bearer ${TOOL_TOKEN}`)
      enterpriseCalls.push(body)
      response.writeHead(200, { 'content-type': 'application/json' })
      return response.end(JSON.stringify({ ok: true, result: { answer: 'enterprise fact' } }))
    }
    response.writeHead(404).end()
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  const baseUrl = `http://127.0.0.1:${address.port}`
  const runtime = new KernelRuntime({
    runtimeId: 'runtime-code-e2e', isolationKey: 'tenant:code-e2e', profileVersion: 'profile-code-e2e',
    storageRoot: root, modelProfile: modelProfile(baseUrl),
  })
  try {
    await runtime.start()
    const session = await runtime.createSession({ sessionId: 'code-e2e', presetId: 'code', cwd: root })
    for (const name of ['askai_mcp_search', 'read', 'write', 'bash']) assert.ok(session.modelTools.includes(name), name)
    assert.equal(session.modelTools.includes('run_code'), false)
    assert.equal(session.permissionPreset, 'workspace-write')
    assert.ok(session.capabilityTools.includes('read'))
    assert.ok(session.capabilityTools.includes('write'))
    assert.ok(session.capabilityTools.includes('bash'))
    assert.ok(session.capabilityTools.includes('skill'))
    runtime.send({
      sessionId: 'code-e2e', mode: 'prompt', content: [{ type: 'text', data: { text: 'Search, edit, and test.' } }],
      temporalContext: {
        captured_at_utc: '2026-08-20T00:00:00Z', user_local_time: '2026-08-20T08:00:00+08:00',
        user_timezone: 'Asia/Shanghai',
      },
    })
    await waitFor(() => modelCalls.length >= 6
      || runtime.events('code-e2e', -1).some(event => event.nativeType === 'turn/end'))
    assert.ok(modelCalls.length >= 6, JSON.stringify(runtime.events('code-e2e', -1), null, 2))
    await waitFor(() => runtime.events('code-e2e', -1).some(event => event.nativeType === 'turn/end'))
    assert.equal(await readFile(join(root, 'output.txt'), 'utf8'), 'workspace fact\nenterprise fact\n')
    assert.equal(enterpriseCalls.length, 1)
    assert.equal(enterpriseCalls[0].toolName, 'askai_mcp_search')
    assert.ok(modelCalls[0].tools.some(tool => tool.name === 'bash'))
    assert.equal(modelCalls[0].tools.some(tool => tool.name === 'run_code'), false)
    assert.equal(modelCalls[0].tools.some(tool => tool.name === 'code_task'), false)
    assert.match(JSON.stringify(modelCalls[0]), /ASKAI_E2E_REPOSITORY_INSTRUCTION/)
    assert.match(JSON.stringify(modelCalls[0]), /verified-workflow/)
    const verificationObservation = JSON.stringify(modelCalls.slice(1))
    assert.match(verificationObservation, /exit(?:Code| code)[^}\]]*[: ]1/i)
    assert.match(verificationObservation, /enterprise fact/)
  } finally {
    await runtime.dispose()
    await new Promise(resolve => server.close(resolve))
    await rm(root, { recursive: true, force: true })
  }
})

test('cancelling a Code Session terminates its official DSH background jobs', async () => {
  const root = await mkdtemp(join(tmpdir(), 'askai-code-cancel-e2e-'))
  const modelCalls = []
  const server = createServer(async (request, response) => {
    const body = await bodyOf(request)
    if (request.url !== '/model') return response.writeHead(404).end()
    modelCalls.push(body)
    if (modelCalls.length === 1) {
      return ndjson(response, [
        { type: 'tool-call', id: 'run-background', name: 'bash', arguments: JSON.stringify({
          description: 'Start cancellable background verification',
          command: "node -e \"setTimeout(() => require('fs').writeFileSync('should-not-exist.txt', 'leaked'), 3000)\"",
          run_in_background: true,
        }) },
        { type: 'finish', reason: { kind: 'tool-calls' } },
      ])
    }
    return ndjson(response, [
      { type: 'text-delta', text: 'Background job started.' },
      { type: 'finish', reason: { kind: 'stop' } },
    ])
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  const runtime = new KernelRuntime({
    runtimeId: 'runtime-cancel-e2e', isolationKey: 'tenant:cancel-e2e', profileVersion: 'profile-code-e2e',
    storageRoot: root, modelProfile: modelProfile(`http://127.0.0.1:${address.port}`),
  })
  try {
    await runtime.start()
    await runtime.createSession({ sessionId: 'cancel-e2e', presetId: 'code', cwd: root, permissionPreset: 'workspace-write' })
    runtime.send({
      sessionId: 'cancel-e2e', mode: 'prompt', content: [{ type: 'text', data: { text: 'Start the background verification.' } }],
      temporalContext: {
        captured_at_utc: '2026-08-20T00:00:00Z', user_local_time: '2026-08-20T08:00:00+08:00',
        user_timezone: 'Asia/Shanghai',
      },
    })
    await waitFor(() => modelCalls.length >= 2)
    const cancelled = await runtime.cancel('cancel-e2e', 'user_cancelled')
    assert.equal(cancelled.jobsPending, false)
    assert.equal(cancelled.jobs.length, 1)
    assert.equal(cancelled.jobs[0].status, 'killed')
    await new Promise(resolve => setTimeout(resolve, 3200))
    await assert.rejects(access(join(root, 'should-not-exist.txt')))
  } finally {
    await runtime.dispose()
    await new Promise(resolve => server.close(resolve))
    await rm(root, { recursive: true, force: true })
  }
})

test('official DSH rejects stale edits and Workspace escape without ASKAI file rules', async () => {
  const root = await mkdtemp(join(tmpdir(), 'askai-code-safety-e2e-'))
  await writeFile(join(root, 'tracked.txt'), 'before\n')
  const outside = join(root, '..', `askai-outside-${Date.now()}.txt`)
  await writeFile(outside, 'outside\n')
  const modelCalls = []
  const server = createServer(async (request, response) => {
    const body = await bodyOf(request)
    if (request.url !== '/model') return response.writeHead(404).end()
    modelCalls.push(body)
    if (modelCalls.length === 1) return ndjson(response, [
      { type: 'tool-call', id: 'observe', name: 'read', arguments: JSON.stringify({ file_path: 'tracked.txt' }) },
      { type: 'finish', reason: { kind: 'tool-calls' } },
    ])
    if (modelCalls.length === 2) {
      await writeFile(join(root, 'tracked.txt'), 'external\n')
      return ndjson(response, [
        { type: 'tool-call', id: 'stale-edit', name: 'edit', arguments: JSON.stringify({
          file_path: 'tracked.txt', old_string: 'before', new_string: 'agent',
        }) }, { type: 'finish', reason: { kind: 'tool-calls' } },
      ])
    }
    if (modelCalls.length === 3) return ndjson(response, [
      { type: 'tool-call', id: 'escaped-read', name: 'read', arguments: JSON.stringify({ file_path: outside }) },
      { type: 'finish', reason: { kind: 'tool-calls' } },
    ])
    return ndjson(response, [
      { type: 'text-delta', text: 'Safety checks complete.' },
      { type: 'finish', reason: { kind: 'stop' } },
    ])
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  const runtime = new KernelRuntime({
    runtimeId: 'runtime-safety-e2e', isolationKey: 'tenant:safety-e2e', profileVersion: 'profile-code-e2e',
    storageRoot: root, modelProfile: modelProfile(`http://127.0.0.1:${address.port}`),
  })
  try {
    await runtime.start()
    await runtime.createSession({ sessionId: 'safety-e2e', presetId: 'code', cwd: root, permissionPreset: 'workspace-write' })
    runtime.send({
      sessionId: 'safety-e2e', mode: 'prompt', content: [{ type: 'text', data: { text: 'Verify safe file editing.' } }],
      temporalContext: {
        captured_at_utc: '2026-08-20T00:00:00Z', user_local_time: '2026-08-20T08:00:00+08:00',
        user_timezone: 'Asia/Shanghai',
      },
    })
    await waitFor(() => modelCalls.length >= 4)
    const safetyResult = JSON.stringify(modelCalls.slice(2))
    assert.match(safetyResult, /changed|stale|observation/i)
    assert.match(safetyResult, /sandbox|outside|denied/i)
    assert.equal(await readFile(join(root, 'tracked.txt'), 'utf8'), 'external\n')
  } finally {
    await runtime.dispose()
    await new Promise(resolve => server.close(resolve))
    await rm(root, { recursive: true, force: true })
    await rm(outside, { force: true })
  }
})

test('official DSH bounds foreground timeout and large command output', async () => {
  const root = await mkdtemp(join(tmpdir(), 'askai-code-command-e2e-'))
  const modelCalls = []
  const server = createServer(async (request, response) => {
    const body = await bodyOf(request)
    if (request.url !== '/model') return response.writeHead(404).end()
    modelCalls.push(body)
    if (modelCalls.length === 1) return ndjson(response, [
      { type: 'tool-call', id: 'large-output', name: 'bash', arguments: JSON.stringify({
        command: "node -e \"process.stdout.write('X'.repeat(100000))\"", description: 'Generate bounded command output',
      }) }, { type: 'finish', reason: { kind: 'tool-calls' } },
    ])
    if (modelCalls.length === 2) return ndjson(response, [
      { type: 'tool-call', id: 'command-timeout', name: 'bash', arguments: JSON.stringify({
        command: "node -e \"setTimeout(() => {}, 1000)\"", description: 'Verify foreground timeout', timeout_ms: 50,
      }) }, { type: 'finish', reason: { kind: 'tool-calls' } },
    ])
    return ndjson(response, [
      { type: 'text-delta', text: 'Command bounds verified.' },
      { type: 'finish', reason: { kind: 'stop' } },
    ])
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  const runtime = new KernelRuntime({
    runtimeId: 'runtime-command-e2e', isolationKey: 'tenant:command-e2e', profileVersion: 'profile-code-e2e',
    storageRoot: root, modelProfile: modelProfile(`http://127.0.0.1:${address.port}`),
  })
  try {
    await runtime.start()
    await runtime.createSession({ sessionId: 'command-e2e', presetId: 'code', cwd: root, permissionPreset: 'workspace-write' })
    runtime.send({
      sessionId: 'command-e2e', mode: 'prompt', content: [{ type: 'text', data: { text: 'Verify command limits.' } }],
      temporalContext: {
        captured_at_utc: '2026-08-20T00:00:00Z', user_local_time: '2026-08-20T08:00:00+08:00',
        user_timezone: 'Asia/Shanghai',
      },
    })
    await waitFor(() => modelCalls.length >= 3)
    const observation = JSON.stringify(modelCalls.slice(1))
    assert.match(observation, /truncat|full output|saved to/i)
    assert.match(observation, /timeout|timed out|BASH_TIMEOUT/i)
    const toolText = modelCalls[1].messages.at(-1).content[0].content[0].text
    assert.match(toolText, /"truncated": true|Omitted \d+ bytes\. Full formatted result stored at:/)
    assert.ok(toolText.length <= 50_000, `bounded command result contains ${toolText.length} characters`)
  } finally {
    await runtime.dispose()
    await new Promise(resolve => server.close(resolve))
    await rm(root, { recursive: true, force: true })
  }
})
