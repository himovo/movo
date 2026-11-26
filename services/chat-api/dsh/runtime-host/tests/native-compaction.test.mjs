import assert from 'node:assert/strict'
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { KernelRuntime } from '../src/kernel-runtime.mjs'
import { modelProfile, ndjson, requestBody, sendText, waitFor, withModelServer } from './support/runtime-admission.mjs'

test('native compact command persists a summary, resumes, and continues the enterprise session', async () => {
  const root = await mkdtemp(join(tmpdir(), 'movo-native-compaction-'))
  const create = () => new KernelRuntime({
    runtimeId: 'compact-test', isolationKey: 'compact-test',
    profileVersion: 'compact-test', storageRoot: root,
  })
  let runtime = create()
  const sessionId = 'compact-session'
  async function send(text) {
    const head = runtime.headCursor(sessionId)
    const accepted = await sendText(runtime, sessionId, text)
    assert.ok(accepted.messageId)
    await waitFor(() => runtime.events(sessionId, head).some(event => event.nativeType === 'turn/end'),
      'turn did not finish', 20000)
    return runtime.events(sessionId, head)
  }
  try {
    await runtime.start()
    await runtime.createSession({ sessionId })
    const initialUsage = await runtime.contextUsage(sessionId)
    assert.equal(initialUsage.available, true)
    assert.equal(initialUsage.capacityTokens, 32768)
    const empty = await send('/compact')
    assert.ok(empty.some(event => event.nativeType === 'command/done' && event.data.text === 'No compactable history yet.'))
    for (let index = 0; index < 12; index++) await send(`History ${index}: ${'project detail '.repeat(400)}`)
    const beforeUsage = await runtime.contextUsage(sessionId)
    const compacted = await send('/compact')
    assert.ok(compacted.some(event => event.nativeType === 'compaction/start'))
    assert.ok(compacted.some(event => event.nativeType === 'compaction/end' && !event.data.error))
    assert.ok(compacted.some(event => event.nativeType === 'command/done' && event.data.kind === 'success'))
    const afterUsage = await runtime.contextUsage(sessionId)
    assert.ok(afterUsage.usedTokens < beforeUsage.usedTokens)
    assert.equal(afterUsage.compacting, false)
    await runtime.dispose()
    runtime = create()
    await runtime.start()
    await Promise.all(Array.from({ length: 8 }, () => runtime.resumeSession(sessionId)))
    const restoredUsage = await runtime.contextUsage(sessionId)
    assert.equal(restoredUsage.usedTokens, afterUsage.usedTokens)
    assert.equal(restoredUsage.capacityTokens, afterUsage.capacityTokens)
    assert.ok(runtime.events(sessionId, -1).some(event => event.nativeType === 'compaction/end'))
    const continued = await send('Continue after restart')
    assert.ok(continued.some(event => event.nativeType === 'assistant/message'))
    const files = await readdir(root, { recursive: true })
    const log = files.find(file => file.endsWith('session.v4.jsonl'))
    const persisted = await readFile(join(root, log), 'utf8')
    assert.ok(persisted.includes('"compaction/start"'))
    assert.ok(persisted.includes('"compaction/end"'))
  } finally {
    await runtime.dispose()
    await rm(root, { recursive: true, force: true })
  }
})

test('native context pressure and overflow recovery compact before continuing', async () => {
  const root = await mkdtemp(join(tmpdir(), 'movo-auto-compaction-'))
  let rejectNext = false
  let overflowInjected = false
  try {
    await withModelServer(async (request, response) => {
      const body = await requestBody(request)
      const lastUser = body.messages.findLast(message => message.role === 'user')
      const lastUserText = typeof lastUser?.content === 'string'
        ? lastUser.content
        : (lastUser?.content ?? []).filter(block => block.type === 'text').map(block => block.text).join('')
      if (rejectNext && lastUserText === 'Continue after overflow') {
        rejectNext = false
        overflowInjected = true
        ndjson(response, [{ type: 'error', error: { code: 'context_window_exceeded', message: 'Context window exceeded', retryable: false } }])
        return
      }
      ndjson(response, [
        { type: 'text-delta', text: 'Retain the project requirements and continue the task.' },
        { type: 'usage', usage: { inputTokens: Math.ceil(JSON.stringify(body.messages).length / 4), outputTokens: 20 } },
        { type: 'finish', reason: { kind: 'stop' } },
      ])
    }, async gatewayUrl => {
      const runtime = new KernelRuntime({
        runtimeId: 'auto-test', isolationKey: 'auto-test', profileVersion: 'auto-test', storageRoot: root,
        modelProfile: modelProfile(gatewayUrl, { contextWindow: 8192 }),
      })
      try {
        await runtime.start()
        await runtime.createSession({ sessionId: 'auto-session' })
        for (let index = 0; index < 12; index++) {
          const head = runtime.headCursor('auto-session')
          await sendText(runtime, 'auto-session', `History ${index}: ${'project detail '.repeat(400)}`)
          await waitFor(() => runtime.events('auto-session', head).some(event => event.nativeType === 'turn/end'),
            'automatic turn did not finish', 20000)
        }
        assert.ok(runtime.events('auto-session', -1).some(event => event.nativeType === 'compaction/end' && !event.data.error),
          JSON.stringify(runtime.events('auto-session', -1).filter(event => event.nativeType.includes('compaction') || event.nativeType === 'turn/end')))
        const head = runtime.headCursor('auto-session')
        rejectNext = true
        await sendText(runtime, 'auto-session', 'Continue after overflow')
        await waitFor(() => runtime.events('auto-session', head).some(event => event.nativeType === 'turn/end'),
          'overflow recovery did not finish', 20000)
        const recovered = runtime.events('auto-session', head)
        assert.ok(overflowInjected)
        assert.ok(recovered.some(event => event.nativeType === 'compaction/end' && !event.data.error))
        assert.ok(recovered.some(event => event.nativeType === 'assistant/message'))
        assert.equal(recovered.findLast(event => event.nativeType === 'turn/end').data.reason.kind, 'completed')
      } finally {
        await runtime.dispose()
      }
    })
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})
