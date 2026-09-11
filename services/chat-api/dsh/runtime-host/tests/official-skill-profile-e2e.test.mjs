import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdtemp, rm } from 'node:fs/promises'
import { createServer } from 'node:http'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { strToU8, zipSync } from 'fflate'

import { KernelRuntime } from '../src/kernel-runtime.mjs'

function ndjson(response, events) {
  response.writeHead(200, { 'content-type': 'application/x-ndjson' })
  response.end(events.map(event => JSON.stringify(event)).join('\n') + '\n')
}

async function bodyOf(request) {
  const chunks = []
  for await (const chunk of request) chunks.push(chunk)
  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}

async function waitFor(predicate, timeoutMs = 5000) {
  const started = Date.now()
  while (!predicate()) {
    if (Date.now() - started > timeoutMs) throw new Error('timed out waiting for Skill E2E')
    await new Promise(resolve => setTimeout(resolve, 20))
  }
}

function profile(gatewayUrl) {
  return {
    profileVersion: 'step7-profile', modelInstanceId: 'model-1', modelName: 'model-1',
    displayName: 'Model', gatewayUrl, accessToken: 'ephemeral',
    skillProfile: {
      skills: [{
        name: 'research-report-a1', version: 'skill-v1', source_id: 'workflow-1',
        source_scope: 'organization', kind: 'workflow', description: 'Research report',
        when_to_use: 'Research requests', content: '# Steps\nResearch then write from evidence.',
        capability_refs: [],
      }],
      writingStyles: [],
    },
  }
}

function profileWithResources(gatewayUrl) {
  const archive = Buffer.from(zipSync({
    'foshan/SKILL.md': strToU8('# Steps\nRead assets/contacts.json before answering.'),
    'foshan/assets/contacts.json': strToU8('{"admissions":"0757-123456"}'),
  }))
  const result = profile(gatewayUrl)
  result.skillProfile.skills[0] = {
    ...result.skillProfile.skills[0],
    name: 'foshan-guide',
    content: '# Steps\nRead assets/contacts.json before answering.',
    bundle_root: 'foshan/',
    bundle_digest: createHash('sha256').update(archive).digest('hex'),
    bundle_archive_base64: archive.toString('base64'),
  }
  return result
}

test('ASKAI Runtime Profile mounts its Skills through the official DSH skill tool', async () => {
  const root = await mkdtemp(join(tmpdir(), 'askai-step7-skill-'))
  const runtime = new KernelRuntime({
    runtimeId: 'step7-runtime', isolationKey: 'tenant:user:step7',
    profileVersion: 'step7-profile', storageRoot: root,
    modelProfile: profile('http://127.0.0.1:9/model'),
  })
  try {
    await runtime.start()
    const session = await runtime.createSession({ sessionId: 'step7-session' })
    assert.deepEqual(session.modelTools, ['skill'])
    assert.ok(session.capabilityTools.includes('skill'))
  } finally {
    await runtime.dispose()
    await rm(root, { recursive: true, force: true })
  }
})

test('official DSH discovers, loads, and follows an ASKAI Workflow Skill', async () => {
  const root = await mkdtemp(join(tmpdir(), 'askai-step7-skill-turn-'))
  const calls = []
  const server = createServer(async (request, response) => {
    calls.push(await bodyOf(request))
    if (calls.length === 1) {
      return ndjson(response, [
        { type: 'tool-call', id: 'load-skill', name: 'skill', arguments: JSON.stringify({ name: 'research-report-a1' }) },
        { type: 'finish', reason: { kind: 'tool-calls' } },
      ])
    }
    return ndjson(response, [
      { type: 'text-delta', text: 'Workflow Skill completed.' },
      { type: 'finish', reason: { kind: 'stop' } },
    ])
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  const runtime = new KernelRuntime({
    runtimeId: 'step7-skill-turn', isolationKey: 'tenant:user:step7-turn',
    profileVersion: 'step7-profile', storageRoot: root,
    modelProfile: profile(`http://127.0.0.1:${address.port}/model`),
  })
  try {
    await runtime.start()
    await runtime.createSession({ sessionId: 'step7-skill-session' })
    runtime.send({
      sessionId: 'step7-skill-session', mode: 'prompt',
      content: [{ type: 'text', data: { text: 'Research and write the report.' } }],
      temporalContext: {
        captured_at_utc: '2026-08-25T00:00:00Z', user_local_time: '2026-08-25T08:00:00+08:00',
        user_timezone: 'Asia/Shanghai',
      },
    })
    await waitFor(() => calls.length >= 2)
    await waitFor(() => runtime.events('step7-skill-session', -1).some(event => event.nativeType === 'turn/end'))
    assert.ok(calls[0].tools.some(tool => tool.name === 'skill'))
    assert.match(JSON.stringify(calls[0]), /available_skills/)
    assert.match(JSON.stringify(calls[1]), /Research then write from evidence/)
  } finally {
    await runtime.dispose()
    await new Promise(resolve => server.close(resolve))
    await rm(root, { recursive: true, force: true })
  }
})

test('official DSH reads a resource from an automatically selected Skill package', async () => {
  const root = await mkdtemp(join(tmpdir(), 'askai-step7-skill-resource-turn-'))
  const calls = []
  const server = createServer(async (request, response) => {
    calls.push(await bodyOf(request))
    if (calls.length === 1) {
      return ndjson(response, [
        { type: 'tool-call', id: 'load-skill', name: 'skill', arguments: JSON.stringify({ name: 'foshan-guide' }) },
        { type: 'finish', reason: { kind: 'tool-calls' } },
      ])
    }
    if (calls.length === 2) {
      return ndjson(response, [
        {
          type: 'tool-call', id: 'read-contacts', name: 'skill_resource_read',
          arguments: JSON.stringify({ path: 'assets/contacts.json' }),
        },
        { type: 'finish', reason: { kind: 'tool-calls' } },
      ])
    }
    return ndjson(response, [
      { type: 'text-delta', text: '招生电话是 0757-123456。' },
      { type: 'finish', reason: { kind: 'stop' } },
    ])
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  const runtime = new KernelRuntime({
    runtimeId: 'step7-resource-turn', isolationKey: 'tenant:user:step7-resource',
    profileVersion: 'step7-profile', storageRoot: root,
    modelProfile: profileWithResources(`http://127.0.0.1:${address.port}/model`),
  })
  try {
    await runtime.start()
    const session = await runtime.createSession({ sessionId: 'step7-resource-session' })
    assert.deepEqual(session.modelTools, ['skill', 'skill_resource_read'])
    runtime.send({
      sessionId: 'step7-resource-session', mode: 'prompt',
      content: [{ type: 'text', data: { text: '佛山大学招生电话是什么？' } }],
      temporalContext: {
        captured_at_utc: '2026-08-25T00:00:00Z', user_local_time: '2026-08-25T08:00:00+08:00',
        user_timezone: 'Asia/Shanghai',
      },
    })
    await waitFor(() => calls.length >= 3)
    await waitFor(() => runtime.events('step7-resource-session', -1).some(event => event.nativeType === 'turn/end'))
    assert.ok(calls[1].tools.some(tool => tool.name === 'skill_resource_read'))
    assert.match(JSON.stringify(calls[1]), /skill_resource_read/)
    assert.match(JSON.stringify(calls[2]), /0757-123456/)
    assert.ok(runtime.events('step7-resource-session', -1).some(event => (
      event.nativeType === 'skill/selected' && event.data?.selectionMode === 'automatic'
    )))
  } finally {
    await runtime.dispose()
    await new Promise(resolve => server.close(resolve))
    await rm(root, { recursive: true, force: true })
  }
})

test('manual ASKAI selection becomes an official DSH user Skill invocation', async () => {
  const root = await mkdtemp(join(tmpdir(), 'askai-step7-manual-skill-'))
  const calls = []
  const server = createServer(async (request, response) => {
    calls.push(await bodyOf(request))
    if (calls.length === 1) {
      return ndjson(response, [
        {
          type: 'tool-call', id: 'read-selected-contacts', name: 'skill_resource_read',
          arguments: JSON.stringify({ path: 'assets/contacts.json' }),
        },
        { type: 'finish', reason: { kind: 'tool-calls' } },
      ])
    }
    return ndjson(response, [
      { type: 'text-delta', text: 'Selected Workflow Skill completed.' },
      { type: 'finish', reason: { kind: 'stop' } },
    ])
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  const runtime = new KernelRuntime({
    runtimeId: 'step7-manual-turn', isolationKey: 'tenant:user:step7-manual',
    profileVersion: 'step7-profile', storageRoot: root,
    modelProfile: profileWithResources(`http://127.0.0.1:${address.port}/model`),
  })
  try {
    await runtime.start()
    await runtime.createSession({ sessionId: 'step7-manual-session' })
    runtime.send({
      sessionId: 'step7-manual-session', mode: 'prompt',
      content: [{ type: 'text', data: { text: 'Do this workflow.' } }],
      turnContext: { selected_skill_id: 'workflow-1' },
      temporalContext: {
        captured_at_utc: '2026-08-25T00:00:00Z', user_local_time: '2026-08-25T08:00:00+08:00',
        user_timezone: 'Asia/Shanghai',
      },
    })
    await waitFor(() => calls.length >= 2)
    await waitFor(() => runtime.events('step7-manual-session', -1).some(event => event.nativeType === 'turn/end'))
    const request = JSON.stringify(calls[0])
    assert.match(request, /skill-invocation/)
    assert.match(request, /Read assets\/contacts.json before answering/)
    assert.match(JSON.stringify(calls[1]), /0757-123456/)
  } finally {
    await runtime.dispose()
    await new Promise(resolve => server.close(resolve))
    await rm(root, { recursive: true, force: true })
  }
})
