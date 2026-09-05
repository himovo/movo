import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import test from 'node:test'
import { stopChatGeneration, type StoppableChatPane } from '../src/composables/chatCancellation'
import { cancelChat, startChatStream } from '../src/composables/useChatStream'

const root = process.cwd()
const runtime = readFileSync(resolve(root, 'src/composables/useChatRuntimeStore.ts'), 'utf8')
const cancellation = readFileSync(resolve(root, 'src/composables/chatCancellation.ts'), 'utf8')
const app = readFileSync(resolve(root, 'src/App.vue'), 'utf8')

assert.ok(runtime.includes('stopChatGeneration(pane'), 'runtime store must delegate cancellation')
assert.ok(cancellation.includes('pane.stopping = true'), 'stop must expose a stopping phase')
assert.ok(cancellation.includes('const cancelled = await cancelChat'), 'stop must await server acknowledgement')
assert.ok(!cancellation.includes('1200'), 'stop must not optimistically time out after 1.2 seconds')
assert.ok(!cancellation.includes("type: 'run.cancelled'"), 'frontend must not forge a terminal cancellation event')
assert.ok(cancellation.includes('await handle.ready'), 'stop must wait for authoritative response headers')
assert.ok(!cancellation.includes('attempt < 50'), 'stop must not poll for a server identity')
assert.ok(
  cancellation.indexOf('const cancelled = await cancelChat') < cancellation.lastIndexOf('releaseStoppedPane(pane, setRunning)'),
  'the composer may unlock only after cancellation is acknowledged',
)
assert.ok(app.includes(':stopping="pane.stopping"'), 'stopping state must reach the visible composer')

test('stream readiness waits for authoritative response headers', async () => {
  const originalFetch = globalThis.fetch
  let resolveFetch!: (response: Response) => void
  globalThis.fetch = (() => new Promise<Response>((resolve) => { resolveFetch = resolve })) as typeof fetch
  try {
    const handle = startChatStream({ messages: [] }, () => undefined)
    let ready = false
    handle.ready.then(() => { ready = true })
    await Promise.resolve()
    assert.equal(ready, false)

    resolveFetch(new Response('', {
      status: 200,
      headers: { 'X-Session-Id': 'conversation-a', 'X-Message-Id': 'message-a' },
    }))
    await handle.ready
    assert.equal(handle.sessionId, 'conversation-a')
    assert.equal(handle.messageId, 'message-a')
    await handle.done
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('stream readiness also settles when request setup fails', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = (async () => { throw new Error('offline') }) as typeof fetch
  try {
    const handle = startChatStream({ messages: [] }, () => undefined)
    const done = handle.done.catch(() => undefined)
    await handle.ready
    await done
    assert.equal(handle.sessionId, null)
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('cancellation requires the API business acknowledgement', async () => {
  const originalFetch = globalThis.fetch
  try {
    globalThis.fetch = (async () => new Response(
      JSON.stringify({ code: 404, message: 'session_not_found' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    )) as typeof fetch
    assert.equal(await cancelChat('conversation-a'), false)

    globalThis.fetch = (async () => new Response(
      JSON.stringify({ code: 0, message: 'ok' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    )) as typeof fetch
    assert.equal(await cancelChat('conversation-a'), true)
  } finally {
    globalThis.fetch = originalFetch
  }
})

function makePane() {
  let aborted = false
  const handle = {
    sessionId: 'conversation-a',
    messageId: 'message-a',
    ready: Promise.resolve(),
    done: Promise.resolve(),
    abort: () => { aborted = true },
  }
  const pane: StoppableChatPane = {
    sessionId: 'conversation-a',
    messages: [{ _id: 'assistant-a', role: 'assistant', _backendSid: 'conversation-a' }],
    stopping: false,
    operationId: 1,
    activeStream: handle,
    abortController: new AbortController(),
    authResumeController: null,
    activeAssistantMessageId: 'assistant-a',
    activeAuthToken: 'token-a',
  }
  return { pane, handle, wasAborted: () => aborted }
}

test('acknowledged cancellation unlocks the pane and aborts its local stream', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = (async () => new Response(
    JSON.stringify({ code: 0, message: 'ok' }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  )) as typeof fetch
  try {
    const { pane, wasAborted } = makePane()
    const runningStates: boolean[] = []
    assert.equal(await stopChatGeneration(pane, (running) => runningStates.push(running)), true)
    assert.equal(pane.activeStream, null)
    assert.equal(pane.stopping, false)
    assert.equal(wasAborted(), true)
    assert.deepEqual(runningStates, [false])
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('rejected cancellation preserves the active pane lock for a safe retry', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = (async () => new Response(
    JSON.stringify({ code: 503, message: 'turn_still_stopping' }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  )) as typeof fetch
  try {
    const { pane, handle, wasAborted } = makePane()
    const runningStates: boolean[] = []
    assert.equal(await stopChatGeneration(pane, (running) => runningStates.push(running)), false)
    assert.equal(pane.activeStream, handle)
    assert.equal(pane.stopping, false)
    assert.equal(wasAborted(), false)
    assert.deepEqual(runningStates, [])
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('stopping preflight work invalidates the pending operation without calling the API', async () => {
  const originalFetch = globalThis.fetch
  let fetched = false
  globalThis.fetch = (async () => {
    fetched = true
    throw new Error('unexpected fetch')
  }) as typeof fetch
  try {
    const { pane } = makePane()
    pane.activeStream = null
    const runningStates: boolean[] = []
    assert.equal(await stopChatGeneration(pane, (running) => runningStates.push(running)), true)
    assert.equal(pane.operationId, 2)
    assert.equal(pane.stopping, false)
    assert.equal(fetched, false)
    assert.deepEqual(runningStates, [false])
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('a failed stream without a server identity releases local running state', async () => {
  const { pane, wasAborted } = makePane()
  pane.sessionId = null
  pane.messages = [{ _id: 'assistant-a', role: 'assistant' }]
  pane.activeStream!.sessionId = null
  const runningStates: boolean[] = []
  assert.equal(await stopChatGeneration(pane, (running) => runningStates.push(running)), true)
  assert.equal(pane.operationId, 2)
  assert.equal(pane.activeStream, null)
  assert.equal(pane.stopping, false)
  assert.equal(wasAborted(), true)
  assert.deepEqual(runningStates, [false])
})
