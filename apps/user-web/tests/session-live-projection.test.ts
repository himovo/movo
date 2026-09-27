import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import test from 'node:test'
import {
  PRE_HEADER_BUFFER_MAX_BYTES,
  PRE_HEADER_BUFFER_MAX_ROWS,
  applyEffectiveUserMessageId,
  bufferPreHeaderEvent,
  createPreHeaderBufferState,
  drainPreHeaderEvents,
  hasFullyAllocatedSeq,
  isManualOnlyConflict,
  messageMergeKey,
  mergeAuthoritativeMessages,
  orderAuthoritativeMessages,
  shouldIgnoreSessionExecution,
  shouldReleaseToDurableRecovery,
  utf8ByteLength,
  withoutMessages,
  type ProjectionMessage,
} from '../src/composables/sessionLiveProjection'
import {
  ChatStreamHttpError,
  isChatStreamAccessRevokedEvent,
  startChatStream,
} from '../src/composables/useChatStream'
import { createExecutionStoreV3 } from '../src/features/execution-v3/stores/executionStore'
import type { ExecutionEventV3 } from '../src/features/execution-v3/domain/protocol'

// The store harness needs a require shim before its axios CJS chain is loaded.
;(globalThis as { require?: unknown }).require = createRequire(import.meta.url)

const T08_HALF = process.env.T08_HALF
function t08(half: 'happy' | 'failure', name: string, fn: () => void | Promise<void>) {
  const runner = !T08_HALF || T08_HALF === half ? test : test.skip
  runner(`[T08-${half}] ${name}`, fn)
}

const encoder = new TextEncoder()
function encode(text: string): Uint8Array {
  return encoder.encode(text)
}

function execEvent(eventId: string, streamSeq: number, type: ExecutionEventV3['type'] = 'item.delta'): ExecutionEventV3 {
  return {
    v: 3,
    event_id: eventId,
    id: eventId,
    ts: 1,
    type,
    item_kind: 'commentary',
    item_id: 'item-1',
    revision: 1,
    stream_seq: streamSeq,
    payload: {},
  }
}

type TestRow = ProjectionMessage & {
  _id?: string
  _execV3?: ReturnType<typeof createExecutionStoreV3>
}

function userRow(overrides: TestRow = {}): TestRow {
  return { role: 'user', content: '', ...overrides }
}

interface FetchCall {
  url: string
  headers: Record<string, string>
  signal: AbortSignal | null
}

function fetchHeaders(init?: RequestInit): Record<string, string> {
  const headers: Record<string, string> = {}
  const raw = init?.headers as Record<string, string> | undefined
  if (raw) for (const [key, value] of Object.entries(raw)) headers[key] = String(value)
  return headers
}

function ndjsonResponse(
  lines: string[],
  options: { headers?: Record<string, string>; status?: number; onCancel?: () => void; close?: boolean } = {},
): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) controller.enqueue(encode(`${line}\n`))
      if (options.close !== false) controller.close()
    },
    cancel() {
      options.onCancel?.()
    },
  })
  return new Response(body, {
    status: options.status ?? 200,
    headers: { 'Content-Type': 'text/plain', ...(options.headers || {}) },
  })
}

function jsonResponse(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function scriptedFetch(steps: Response[]) {
  const calls: FetchCall[] = []
  const impl = (async (input: unknown, init?: RequestInit) => {
    calls.push({ url: String(input), headers: fetchHeaders(init), signal: (init?.signal as AbortSignal) || null })
    const step = steps.shift()
    if (!step) return new Promise<Response>(() => undefined)
    return step
  }) as typeof fetch
  return { impl, calls }
}

async function until(predicate: () => boolean, label: string, tries = 400): Promise<void> {
  for (let attempt = 0; attempt < tries; attempt += 1) {
    if (predicate()) return
    await new Promise<void>((settle) => setTimeout(settle, 1))
  }
  assert.fail(`timed out waiting for ${label}`)
}

async function settleTicks(count = 4): Promise<void> {
  for (let tick = 0; tick < count; tick += 1) await new Promise<void>((settle) => setTimeout(settle, 0))
}

// ---------------------------------------------------------------------------
// Happy half (plan L150)
// ---------------------------------------------------------------------------

t08('happy', 'merge consumes the server legacy_key verbatim and keeps unsequenced rows distinct', () => {
  assert.equal(messageMergeKey({ message_id: 'm-remote', legacy_key: 'legacy:user:9' }), 'message:m-remote')
  assert.equal(messageMergeKey({ legacy_key: 'legacy:user:1' }), 'legacy:user:1')
  assert.equal(messageMergeKey({}), null, 'never synthesize a key')
  assert.equal(messageMergeKey({ message_id: '', legacy_key: '' }), null)
  assert.notEqual(messageMergeKey({ message_id: 'undefined' }), undefined)

  const incoming: ProjectionMessage[] = [
    userRow({ content: 'legacy only', legacy_key: 'legacy:user:0' }),
    userRow({ content: 'remote', message_id: 'm-remote', legacy_key: 'message:m-remote', seq: 2 }),
    userRow({ content: 'legacy A', legacy_key: 'legacy:user:1' }),
    userRow({ content: 'legacy B', legacy_key: 'legacy:user:2' }),
  ]
  const merged = mergeAuthoritativeMessages([], incoming)
  const keys = merged.messages.map((row) => messageMergeKey(row))
  assert.deepEqual(keys, ['legacy:user:0', 'message:m-remote', 'legacy:user:1', 'legacy:user:2'])
  assert.equal(new Set(keys).size, 4, 'distinct legacy rows never collapse')
  assert.ok(!keys.some((key) => key?.includes('undefined')), 'no synthesized undefined key')

  const again = mergeAuthoritativeMessages(merged.messages, incoming)
  assert.deepEqual(again.messages.map((row) => messageMergeKey(row)), keys, 'keys are stable across reloads')
})

t08('happy', 'seq orders rows only when fully allocated; a degraded response keeps server order', () => {
  const allocated = [userRow({ seq: 3 }), userRow({ seq: 1 }), userRow({ seq: 2 })]
  assert.equal(hasFullyAllocatedSeq(allocated), true)
  assert.deepEqual(orderAuthoritativeMessages(allocated).map((row) => row.seq), [1, 2, 3])

  const degraded = [
    userRow({ legacy_key: 'legacy:user:0', seq: 0 }),
    userRow({ seq: 1 }),
    userRow({ seq: 2 }),
  ]
  assert.equal(hasFullyAllocatedSeq(degraded), false)
  assert.deepEqual(orderAuthoritativeMessages(degraded), degraded, 'a degraded response is never re-sorted')

  const shuffled = mergeAuthoritativeMessages([], [userRow({ content: 'third', seq: 3 }), userRow({ content: 'first', seq: 1 })])
  assert.deepEqual(shuffled.messages.map((row) => row.content), ['first', 'third'])
})

t08('happy', 'snapshot reconciliation keeps one ordered user row per message and one assistant row', () => {
  const execStore = createExecutionStoreV3()
  execStore.applyEvent(execEvent('exec-1', 4))
  const viewerAuthor = { user_id: 'viewer-1', display_name: 'Viewer', avatar_url: null }
  const existing = [
    userRow({ _id: 'u-opt', message_id: 'loc-1', user_id: 'viewer-1', author: viewerAuthor, content: 'hello' }),
    userRow({ _id: 'a-local', role: 'assistant', message_id: 'asst-1', content: 'partial', _execV3: execStore }),
  ]
  assert.equal(applyEffectiveUserMessageId(existing[0], 'srv-1'), true)

  const snapshot: ProjectionMessage[] = [
    { role: 'assistant', content: 'final answer', message_id: 'asst-1', legacy_key: 'message:asst-1', seq: 3 },
    {
      role: 'user',
      content: 'hello',
      message_id: 'srv-1',
      legacy_key: 'message:srv-1',
      seq: 2,
      author: { user_id: 'viewer-1', display_name: 'Viewer', avatar_url: null },
    },
    { role: 'user', content: 'legacy only', legacy_key: 'legacy:user:1' },
  ]
  const merged = mergeAuthoritativeMessages(existing, snapshot)
  const users = merged.messages.filter((row) => row.role === 'user')
  const assistants = merged.messages.filter((row) => row.role === 'assistant')
  assert.equal(users.length, 2)
  assert.deepEqual(users.map((row) => row.content), ['hello', 'legacy only'], 'user rows keep the authoritative order')
  assert.equal(assistants.length, 1, 'the local assistant stream and its snapshot row are one row')
  assert.equal(assistants[0].content, 'final answer')
  assert.strictEqual(assistants[0]._execV3, execStore, 'the execution store survives the snapshot')
  assert.equal(assistants[0]._execV3?.state.rawEvents.length, 1)
  assert.equal((existing[0] as { _id?: string })._id, 'u-opt', 'the optimistic row keeps its runtime identity')
})

t08('happy', 'execution dedupes by event_id alone and the effective id maps the optimistic row', () => {
  const store = createExecutionStoreV3()
  store.applyEvent(execEvent('e1', 1, 'run.started'))
  store.applyEvent(execEvent('e2', 5, 'run.completed'))
  store.applyEvent(execEvent('e2', 9, 'run.completed'))
  assert.deepEqual(store.state.rawEvents.map((event) => event.event_id), ['e1', 'e2'])
  assert.equal(store.state.rawEvents.filter((event) => event.type === 'run.completed').length, 1, 'one terminal state')
  store.applyEvent(execEvent('e3', 5))
  assert.equal(store.state.rawEvents.length, 3, 'stream_seq is never the dedupe key')

  const optimistic = { message_id: 'loc-1' }
  assert.equal(applyEffectiveUserMessageId(optimistic, 'srv-1'), true)
  assert.equal(optimistic.message_id, 'srv-1')
  assert.equal(applyEffectiveUserMessageId(optimistic, 'srv-1'), false, 're-mapping is idempotent')
  const merged = mergeAuthoritativeMessages(
    [userRow({ _id: 'u-opt', message_id: optimistic.message_id, content: 'hello' })],
    [userRow({ content: 'hello', message_id: 'srv-1', legacy_key: 'message:srv-1', seq: 1 })],
  )
  assert.equal(merged.messages.length, 1)
  assert.deepEqual(merged.matchedKeys, ['message:srv-1'])
})

t08('happy', 'pre-header buffer holds frames until the local header, then drops only the POST frames', () => {
  const state = createPreHeaderBufferState<{ message_id: string; event_id: string }>()
  const frame = (messageId: string, eventId: string) => ({ message_id: messageId, event_id: eventId })
  for (const item of [frame('asst-1', 'own-before'), frame('other-9', 'foreign'), frame('asst-1', 'own-after')]) {
    bufferPreHeaderEvent(state, item, utf8ByteLength(JSON.stringify(item)))
  }
  assert.equal(state.rows.length, 3)
  const drained = drainPreHeaderEvents(state, 'asst-1')
  assert.deepEqual(drained.map((item) => item.event_id), ['foreign'], 'only foreign frames are consumed')
  assert.equal(state.rows.length, 0)
  assert.equal(state.bytes, 0)
  assert.equal(state.overflowed, false)

  assert.equal(shouldIgnoreSessionExecution('asst-1', 'asst-1'), true)
  assert.equal(shouldIgnoreSessionExecution('asst-1', 'other-9'), false)
  assert.equal(shouldIgnoreSessionExecution(null, 'asst-1'), false)
})

t08('happy', 'typed access-revoked NDJSON line fires one access-loss callback and closes without cancel', async () => {
  let cancelled = false
  const revoked = { type: 'session.access.revoked', session_id: 'sess-1', reason: 'participant_removed' }
  const script = scriptedFetch([
    ndjsonResponse([JSON.stringify(execEvent('wire-1', 1)), JSON.stringify(revoked)], { onCancel: () => { cancelled = true } }),
  ])
  const previousFetch = globalThis.fetch
  ;(globalThis as { fetch: typeof fetch }).fetch = script.impl
  try {
    const events: ExecutionEventV3[] = []
    const losses: Array<{ reason: string }> = []
    const handle = startChatStream({ messages: [] }, (event) => events.push(event), {
      onAccessRevoked: (event) => losses.push(event),
    })
    await handle.ready
    await handle.done
    assert.equal(events.length, 1, 'the revoked line never leaks as an execution event')
    assert.equal(losses.length, 1, 'one access-loss callback')
    assert.equal(losses[0].reason, 'participant_removed')
    assert.equal(cancelled, false, 'the reader is closed without cancel')
    assert.equal(script.calls.length, 1, 'no automatic retry')
    assert.equal(isChatStreamAccessRevokedEvent(revoked), true)
    assert.equal(isChatStreamAccessRevokedEvent(execEvent('wire-2', 2)), false)
  } finally {
    ;(globalThis as { fetch: typeof fetch }).fetch = previousFetch
  }
})

t08('happy', 'X-User-Message-Id is sent and the effective user-message id surfaces on the handle', async () => {
  const script = scriptedFetch([
    ndjsonResponse([], { headers: { 'X-Session-Id': 'sess-1', 'X-Message-Id': 'asst-1', 'X-User-Message-Id': 'srv-user-1' } }),
    ndjsonResponse([], { headers: { 'X-Session-Id': 'sess-2' } }),
  ])
  const previousFetch = globalThis.fetch
  ;(globalThis as { fetch: typeof fetch }).fetch = script.impl
  try {
    const userIds: string[] = []
    const first = startChatStream({ messages: [] }, () => undefined, {
      userMessageId: 'local-user-1',
      onUserMessageId: (id) => userIds.push(id),
    })
    await first.done
    assert.equal(script.calls[0].headers['X-User-Message-Id'], 'local-user-1')
    assert.equal(first.userMessageId, 'srv-user-1')
    assert.deepEqual(userIds, ['srv-user-1'])

    const fallbackIds: string[] = []
    const second = startChatStream({ messages: [] }, () => undefined, {
      userMessageId: 'local-user-2',
      onUserMessageId: (id) => fallbackIds.push(id),
    })
    await second.done
    assert.equal(second.userMessageId, 'local-user-2', 'the requested id is the effective fallback')
    assert.deepEqual(fallbackIds, ['local-user-2'])
  } finally {
    ;(globalThis as { fetch: typeof fetch }).fetch = previousFetch
  }
})

// ---------------------------------------------------------------------------
// Failure half (plan L151)
// ---------------------------------------------------------------------------

t08('failure', 'duplicate events before/after the local header converge to one row', () => {
  const optimistic = userRow({ _id: 'u-opt', message_id: 'loc-1', content: 'hello' })
  const snapshot = [userRow({ content: 'hello', message_id: 'srv-1', legacy_key: 'message:srv-1', seq: 1 })]

  const beforeHeader = mergeAuthoritativeMessages([optimistic], snapshot)
  assert.equal(beforeHeader.messages.length, 2, 'pre-header snapshot appends the authoritative row')
  assert.deepEqual(beforeHeader.appendedKeys, ['message:srv-1'])

  assert.equal(applyEffectiveUserMessageId(beforeHeader.messages[0], 'srv-1'), true)
  const afterHeader = mergeAuthoritativeMessages(beforeHeader.messages, snapshot)
  assert.equal(afterHeader.messages.filter((row) => row.role === 'user').length, 1, 'the collision collapses')
  assert.equal(afterHeader.messages[0].message_id, 'srv-1')
  assert.deepEqual(afterHeader.matchedKeys, ['message:srv-1'])

  const third = mergeAuthoritativeMessages(afterHeader.messages, snapshot)
  assert.deepEqual(third.messages, afterHeader.messages, 'reconciliation is deterministic and idempotent')
})

t08('failure', 'server id differing from the optimistic id reconciles; a lost stream releases to durable recovery', () => {
  const row = { message_id: 'loc-optimistic' }
  assert.equal(applyEffectiveUserMessageId(row, 'srv-different'), true)
  assert.equal(row.message_id, 'srv-different')
  const merged = mergeAuthoritativeMessages(
    [userRow({ _id: 'u-opt', message_id: 'srv-different', content: 'hi' })],
    [userRow({ message_id: 'srv-different', legacy_key: 'message:srv-different', content: 'hi', seq: 1 })],
  )
  assert.equal(merged.messages.length, 1)
  assert.equal(merged.appendedKeys.length, 0)

  assert.equal(shouldReleaseToDurableRecovery({ accessLost: false, paneAlive: true, aborted: false }), true)
  assert.equal(shouldReleaseToDurableRecovery({ accessLost: true, paneAlive: true, aborted: false }), false)
  assert.equal(shouldReleaseToDurableRecovery({ accessLost: false, paneAlive: false, aborted: false }), false)
  assert.equal(shouldReleaseToDurableRecovery({ accessLost: false, paneAlive: true, aborted: true }), false)
})

t08('failure', '200-row and 256-KiB pre-header overflow drops the whole buffer', () => {
  const rows = createPreHeaderBufferState<{ message_id: string }>()
  for (let index = 0; index < PRE_HEADER_BUFFER_MAX_ROWS; index += 1) {
    bufferPreHeaderEvent(rows, { message_id: `m-${index}` }, 2)
  }
  assert.equal(rows.rows.length, PRE_HEADER_BUFFER_MAX_ROWS)
  bufferPreHeaderEvent(rows, { message_id: 'm-overflow' }, 2)
  assert.equal(rows.overflowed, true)
  assert.equal(rows.rows.length, 0)
  assert.deepEqual(drainPreHeaderEvents(rows, null), [])
  assert.equal(rows.overflowed, false)

  const bytes = createPreHeaderBufferState<{ message_id: string }>()
  const frameBytes = utf8ByteLength(JSON.stringify({ message_id: 'big', payload: 'x'.repeat(100_000) }))
  bufferPreHeaderEvent(bytes, { message_id: 'a' }, frameBytes)
  bufferPreHeaderEvent(bytes, { message_id: 'b' }, frameBytes)
  assert.equal(bytes.overflowed, false)
  bufferPreHeaderEvent(bytes, { message_id: 'c' }, frameBytes)
  assert.equal(bytes.overflowed, true)
  assert.deepEqual(drainPreHeaderEvents(bytes, 'asst-1'), [])
  assert.equal(PRE_HEADER_BUFFER_MAX_BYTES, 262144)
})

t08('failure', 'manual-only 409 removes both bubbles, shows the neutral state, and never retries', async () => {
  assert.equal(isManualOnlyConflict('session_already_running'), true)
  assert.equal(isManualOnlyConflict('user_message_id_conflict'), true)
  assert.equal(isManualOnlyConflict('message_sequence_conflict'), false)
  assert.equal(isManualOnlyConflict(null), false)

  const bubbles = [{ _id: 'user-1' }, { _id: 'assistant-1' }, { _id: 'older' }]
  assert.deepEqual(withoutMessages(bubbles, ['user-1', 'assistant-1']).map((row) => row._id), ['older'])

  for (const code of ['session_already_running', 'user_message_id_conflict']) {
    const script = scriptedFetch([jsonResponse(409, { detail: { code, message: 'busy' } })])
    const previousFetch = globalThis.fetch
    ;(globalThis as { fetch: typeof fetch }).fetch = script.impl
    try {
      const handle = startChatStream({ messages: [] }, () => undefined, {})
      await assert.rejects(
        handle.done,
        (error: unknown) => error instanceof ChatStreamHttpError && error.status === 409 && error.code === code,
      )
      assert.equal(script.calls.length, 1, 'zero automatic POST retries for a manual-only 409')
    } finally {
      ;(globalThis as { fetch: typeof fetch }).fetch = previousFetch
    }
  }
})

t08('failure', 'revoked line twice plus a session-SSE frame latches access loss exactly once', async () => {
  let cancelled = false
  const liveCalls: Array<{ signal: AbortSignal | null; push: (text: string) => void }> = []
  const fetchCalls: string[] = []
  const impl = (async (input: unknown, init?: RequestInit) => {
    const url = String(input)
    fetchCalls.push(url)
    if (url.includes('/live')) {
      let stream: ReadableStreamDefaultController<Uint8Array> | null = null
      const body = new ReadableStream<Uint8Array>({ start(controller) { stream = controller } })
      liveCalls.push({
        signal: (init?.signal as AbortSignal) || null,
        push: (text) => { try { stream?.enqueue(encode(text)) } catch { stream = null } },
      })
      return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    }
    if (url.includes('/chat/completions')) {
      const revoked = JSON.stringify({ type: 'session.access.revoked', session_id: 'sess-f5', reason: 'participant_removed' })
      return ndjsonResponse([revoked, revoked], { onCancel: () => { cancelled = true } })
    }
    return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
  }) as typeof fetch
  const previousFetch = globalThis.fetch
  ;(globalThis as { fetch: typeof fetch }).fetch = impl

  const axios = (await import('axios')).default
  ;(axios.defaults as unknown as { adapter: (config: { url?: string }) => Promise<unknown> }).adapter = async (config) => ({
    data: {
      data: {
        id: 'sess-f5',
        title: 'Shared session',
        messages: [],
        access: 'shared',
        owner_user_id: 'owner-1',
        participant_count: 2,
      },
    },
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
    request: null,
  })
  // allow: SIZE_OK — T8 failure evidence needs the store + transport in one harness.
  const { useChatRuntimeStore } = await import('../src/composables/useChatRuntimeStore')
  const runtime = useChatRuntimeStore({})
  try {
    runtime.reset()
    const pane = await runtime.selectSession('sess-f5', 'user-1', 'main-1', 'token-1')
    assert.equal(pane.shared, true, 'shared panes are flagged from authoritative detail')
    await until(() => liveCalls.length === 1, 'session-SSE stream start')

    const losses: string[] = []
    const handle = startChatStream({ messages: [] }, () => undefined, {
      onAccessRevoked: (event) => {
        losses.push(event.reason)
        runtime.markAccessLost(pane.key, event.reason)
      },
    })
    await handle.done
    assert.equal(losses.length, 1, 'the repeated revoked line fires one callback')
    assert.equal(cancelled, false, 'the POST reader is closed without cancel')
    assert.equal(fetchCalls.filter((url) => url.includes('/cancel')).length, 0, 'no backend cancel request')
    assert.equal(pane.accessLost, true)
    assert.equal(pane.accessLostReason, 'participant_removed')
    assert.equal(liveCalls[0].signal?.aborted, true, 'the latch aborts the session-SSE stream')

    liveCalls[0].push('event: session.access.revoked\ndata: {"session_id":"sess-f5","reason":"participant_left"}\n\n')
    await settleTicks()
    assert.equal(losses.length, 1)
    assert.equal(pane.accessLostReason, 'participant_removed', 'later triggers are no-ops')
    assert.equal(liveCalls.length, 1, 'no stream is restarted for a latched pane')

    runtime.markAccessLost(pane.key, 'participant_left')
    assert.equal(pane.accessLostReason, 'participant_removed')
    assert.equal(liveCalls.length, 1)
  } finally {
    runtime.removeSession('sess-f5')
    runtime.reset()
    ;(globalThis as { fetch: typeof fetch }).fetch = previousFetch
  }
})
