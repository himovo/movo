import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import test from 'node:test'
// allow: SIZE_OK — T6's QA row mandates the happy + failure matrices in one harness.
import {
  SESSION_LIVE_CONTROL_FRAME_CAP,
  SessionLiveHttpError,
  noteSessionLiveControlFrame,
  noteSessionLiveData,
  sessionLiveReconnectDelayMs,
  startSessionLiveStream,
  type SessionLiveStreamOptions,
  type SessionLiveStreamHandle,
} from '../src/composables/useSessionLiveStream'

const PANE = 'pane-a'
const SESSION = 'sess-1'
const LIVE_URL = `/askai-api/api/sessions/${SESSION}/live`

type FetchStep = Response | Error | (() => Response | Promise<Response>)

interface FetchCall {
  url: string
  headers: Record<string, string>
  signal: AbortSignal | null
}

function scriptedFetch(steps: FetchStep[]) {
  const calls: FetchCall[] = []
  const impl = (async (input: any, init?: RequestInit) => {
    const headers: Record<string, string> = {}
    const raw = init?.headers as Record<string, string> | undefined
    if (raw) for (const [key, value] of Object.entries(raw)) headers[key] = String(value)
    calls.push({ url: String(input), headers, signal: (init?.signal as AbortSignal) || null })
    const step = steps.shift()
    if (step instanceof Error) throw step
    if (step === undefined) return new Promise<Response>(() => undefined)
    return typeof step === 'function' ? await step() : step
  }) as typeof fetch
  return { impl, calls }
}

const encoder = new TextEncoder()

function encode(text: string): Uint8Array {
  return encoder.encode(text)
}

function chunked(text: string, size: number): Uint8Array[] {
  const bytes = encode(text)
  const chunks: Uint8Array[] = []
  for (let index = 0; index < bytes.length; index += size) chunks.push(bytes.slice(index, index + size))
  return chunks
}

function sseBody(chunks: Uint8Array[], onCancel?: () => void): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk)
      controller.close()
    },
    cancel() {
      onCancel?.()
    },
  })
}

function sseResponse(text: string, size = Number.MAX_SAFE_INTEGER): Response {
  return new Response(sseBody(chunked(text, size)), {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

function openSseResponse(initial: string, onCancel?: () => void): Response {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encode(initial))
      },
      cancel() {
        onCancel?.()
      },
    }),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  )
}

function frame(event: string, data: unknown, id?: string): string {
  const lines: string[] = []
  if (id !== undefined) lines.push(`id: ${id}`)
  lines.push(`event: ${event}`)
  lines.push(`data: ${typeof data === 'string' ? data : JSON.stringify(data)}`)
  return `${lines.join('\n')}\n\n`
}

function executionPayload(overrides: Record<string, any> = {}): Record<string, any> {
  return {
    session_id: SESSION,
    message_id: 'msg-1',
    event_id: 'evt-1',
    stream_seq: 1,
    event: {
      v: 3,
      event_id: 'evt-1',
      id: 'evt-1',
      ts: 1,
      type: 'item.delta',
      item_kind: null,
      item_id: null,
      parent_item_id: null,
      revision: 1,
      stream_seq: 1,
      stream_seq_end: 1,
      payload: { text: '会话继续🙂' },
    },
    ...overrides,
  }
}

interface Recorded {
  thread: Array<any>
  turnStarted: Array<any>
  execution: Array<any>
  turnCompleted: Array<any>
  members: string[]
  accessLost: Array<{ paneKey: string; reason: string }>
  malformed: string[]
  errors: SessionLiveHttpError[]
  cursorAt: Record<string, string | null>
}

interface HarnessOptions extends Partial<SessionLiveStreamOptions> {
  fetchImpl: typeof fetch
}

function harness(recorded: Recorded, options: HarnessOptions): SessionLiveStreamHandle {
  const ref: { current: SessionLiveStreamHandle | null } = { current: null }
  const handle = startSessionLiveStream({
    sessionId: SESSION,
    paneKey: PANE,
    authToken: 'token-a',
    sleep: async () => undefined,
    random: () => 0.5,
    ...options,
    onThreadChanged: (event) => {
      recorded.thread.push(event)
      recorded.cursorAt.threadChanged = ref.current?.cursor() ?? null
    },
    onTurnStarted: (event) => {
      recorded.turnStarted.push(event)
      recorded.cursorAt.turnStarted = ref.current?.cursor() ?? null
    },
    onExecution: (event) => {
      recorded.execution.push(event)
      recorded.cursorAt.execution = ref.current?.cursor() ?? null
    },
    onTurnCompleted: (event) => {
      recorded.turnCompleted.push(event)
      recorded.cursorAt.turnCompleted = ref.current?.cursor() ?? null
    },
    onMembersChanged: (paneKey) => {
      recorded.members.push(paneKey)
    },
    onAccessLost: (paneKey, reason) => {
      recorded.accessLost.push({ paneKey, reason })
      recorded.cursorAt.accessLost = ref.current?.cursor() ?? null
    },
    onMalformedFrame: (raw) => {
      recorded.malformed.push(raw)
    },
    onError: (error) => {
      recorded.errors.push(error)
    },
  })
  ref.current = handle
  return handle
}

function makeRecorded(): Recorded {
  return {
    thread: [],
    turnStarted: [],
    execution: [],
    turnCompleted: [],
    members: [],
    accessLost: [],
    malformed: [],
    errors: [],
    cursorAt: {},
  }
}

function threadChangedPayload(reason?: string): Record<string, any> {
  const payload: Record<string, any> = { session_id: SESSION, revision: 'rev-2', last_message_seq: 7 }
  if (reason) payload.reason = reason
  return payload
}

test('cold attach streams every event type across fragmented UTF-8 chunks and reopens fresh after a control frame', async () => {
  const recorded = makeRecorded()
  const transcript = [
    ': heartbeat\n\n',
    frame('turn.started', {
      session_id: SESSION,
      revision: 'rev-1',
      run_id: 'run-1',
      message_id: 'msg-1',
      initiator_user_id: 'user-1',
      status: 'running',
    }, 'cur-turn'),
    frame('execution', executionPayload({ stream_seq: 1 }), 'cur-exec'),
    frame('execution', executionPayload({ stream_seq: 2, event_id: 'evt-2' }), 'cur-exec'),
    'id: cur-done\nevent: turn.completed\ndata: {"session_id":"sess-1",\ndata: "message_id":"msg-1","run_id":"run-1","status":"completed","revision":"rev-2"}\n\n',
    frame('thread.changed', threadChangedPayload('cursor_gap')),
    ': trailing heartbeat\n\n',
  ].join('')
  const script = scriptedFetch([
    sseResponse(transcript, 5),
    sseResponse(frame('members.changed', { session_id: SESSION, revision: 'rev-3' })),
  ])
  const handle = harness(recorded, { fetchImpl: script.impl })
  await new Promise<void>((resolve) => setTimeout(resolve, 20))

  assert.equal(script.calls.length, 1, 'a control frame parks the stream until the caller reopens')
  assert.equal(script.calls[0]!.url, LIVE_URL, 'cold attach carries no query position')
  assert.equal(script.calls[0]!.headers.Authorization, 'Bearer token-a')
  assert.equal(script.calls[0]!.headers['Last-Event-ID'], undefined, 'cold attach sends no Last-Event-ID')
  assert.equal(recorded.turnStarted.length, 1)
  assert.equal(recorded.execution.length, 2, 'repeated event ids must not drop frames')
  assert.equal(recorded.turnCompleted.length, 1)
  assert.equal(recorded.thread.length, 1)
  assert.equal(recorded.thread[0]!.reason, 'cursor_gap')
  assert.equal(recorded.members.length, 0, 'onMembersChanged must not fire for thread.changed')
  assert.equal(recorded.accessLost.length, 0)
  assert.equal(recorded.malformed.length, 0)
  assert.equal(recorded.cursorAt.turnStarted, 'cur-turn', 'an accepted frame advances the cursor before its callback')
  assert.equal(recorded.cursorAt.execution, 'cur-exec')
  assert.equal(recorded.cursorAt.turnCompleted, 'cur-done')
  assert.equal(handle.cursor(), 'cur-done', 'a no-ID control frame advances no cursor')

  handle.openFreshStream('fresh-cursor-1')
  await new Promise<void>((resolve) => setTimeout(resolve, 20))
  assert.equal(script.calls.length, 2)
  assert.equal(script.calls[1]!.url, `${LIVE_URL}?after=fresh-cursor-1`)
  assert.equal(script.calls[1]!.headers['Last-Event-ID'], undefined, 'fresh stream drops the stale Last-Event-ID')
  assert.equal(script.calls[1]!.headers.Authorization, 'Bearer token-a')
  assert.deepEqual(recorded.members, [PANE], 'onMembersChanged receives the paneKey')
  assert.equal(recorded.accessLost.length, 0)
  assert.equal(handle.cursor(), null, 'fresh stream starts from the authoritative cursor, not the stale one')

  handle.stop()
  await handle.done
})

test('transient disconnect retries with Last-Event-ID and capped exponential backoff', async () => {
  const recorded = makeRecorded()
  const sleeps: number[] = []
  const script = scriptedFetch([
    sseResponse(frame('execution', executionPayload(), 'cur-9')),
    openSseResponse(': heartbeat\n\n'),
  ])
  const handle = startSessionLiveStream({
    sessionId: SESSION,
    paneKey: PANE,
    authToken: 'token-a',
    fetchImpl: script.impl,
    random: () => 0.5,
    sleep: async (ms) => {
      sleeps.push(ms)
    },
    onExecution: (event) => recorded.execution.push(event),
  })
  await new Promise<void>((resolve) => setTimeout(resolve, 20))

  assert.equal(script.calls.length, 2, 'an EOF without a control frame reconnects')
  assert.equal(script.calls[0]!.headers['Last-Event-ID'], undefined)
  assert.equal(script.calls[1]!.headers['Last-Event-ID'], 'cur-9', 'same-stream resume replays from the last id')
  assert.equal(script.calls[1]!.url, LIVE_URL, 'same-stream resume uses the header, not a query value')
  assert.deepEqual(sleeps, [1000], 'first retry waits the 1s backoff step')

  handle.stop()
  await handle.done
})

test('5xx responses retry with escalating backoff and reset after progress', async () => {
  const recorded = makeRecorded()
  const sleeps: number[] = []
  const script = scriptedFetch([
    new Response('overloaded', { status: 503 }),
    new Response('still down', { status: 502 }),
    sseResponse(frame('execution', executionPayload(), 'cur-1')),
    openSseResponse(': heartbeat\n\n'),
  ])
  const handle = startSessionLiveStream({
    sessionId: SESSION,
    paneKey: PANE,
    fetchImpl: script.impl,
    random: () => 0.5,
    sleep: async (ms) => {
      sleeps.push(ms)
    },
    onExecution: (event) => recorded.execution.push(event),
  })
  await new Promise<void>((resolve) => setTimeout(resolve, 30))

  assert.equal(script.calls.length, 4)
  assert.equal(recorded.errors.length, 0, '5xx is transient, not a terminal typed error')
  assert.deepEqual(sleeps, [1000, 2000, 1000], 'backoff escalates then resets after a data frame')
  assert.equal(handle.cursor(), 'cur-1')

  handle.stop()
  await handle.done
})

test('malformed frames are typed, delivered nowhere, and never advance the cursor', async () => {
  const recorded = makeRecorded()
  const transcript = [
    'id: bad-1\nevent: execution\ndata: {not json}\n\n',
    `event: execution\ndata: ${JSON.stringify(executionPayload())}\n\n`,
    'id: bad-2\nevent: mystery\ndata: {}\n\n',
    'event: thread.changed\ndata: }}\n\n',
    `id: bad-3\nevent: thread.changed\ndata: ${JSON.stringify({ ...threadChangedPayload(), reason: 'not_a_reason' })}\n\n`,
    frame('execution', executionPayload(), 'ok-1'),
    frame('thread.changed', threadChangedPayload('cursor_gap')),
  ].join('')
  const script = scriptedFetch([sseResponse(transcript)])
  const handle = harness(recorded, { fetchImpl: script.impl })
  await new Promise<void>((resolve) => setTimeout(resolve, 20))

  assert.equal(recorded.malformed.length, 5, 'every malformed frame is reported once')
  assert.equal(recorded.execution.length, 1, 'only the well-formed execution frame is delivered')
  assert.equal(recorded.thread.length, 1)
  assert.equal(recorded.thread[0]!.reason, 'cursor_gap')
  assert.equal(handle.cursor(), 'ok-1', 'malformed frames never advance the cursor')
  assert.equal(script.calls.length, 1, 'malformed frames never trigger a retry')
  handle.stop()
  await handle.done
})

for (const status of [401, 403, 404, 410]) {
  test(`status ${status} is terminal and never retried`, async () => {
    const recorded = makeRecorded()
    const script = scriptedFetch([new Response('denied', { status })])
    const handle = harness(recorded, { fetchImpl: script.impl })
    await handle.done

    assert.equal(script.calls.length, 1, `status ${status} must not retry`)
    assert.equal(recorded.errors.length, 1)
    assert.ok(recorded.errors[0] instanceof SessionLiveHttpError)
    assert.equal(recorded.errors[0]!.status, status)
    assert.equal(handle.cursor(), null)
    const delivered = recorded.execution.length + recorded.thread.length + recorded.turnStarted.length +
      recorded.turnCompleted.length + recorded.members.length + recorded.accessLost.length
    assert.equal(delivered, 0, 'a failed handshake delivers no events')
  })
}

test('access revoke without an id is terminal: cursor cleared, typed callback, no reconnect', async () => {
  const recorded = makeRecorded()
  const transcript = [
    frame('execution', executionPayload(), 'cur-a'),
    `event: session.access.revoked\ndata: ${JSON.stringify({ session_id: SESSION, reason: 'participant_removed' })}\n\n`,
  ].join('')
  const script = scriptedFetch([sseResponse(transcript)])
  const handle = harness(recorded, { fetchImpl: script.impl })
  await handle.done

  assert.deepEqual(recorded.accessLost, [{ paneKey: PANE, reason: 'participant_removed' }], 'revoke without an id still reaches onAccessLost')
  assert.equal(recorded.cursorAt.accessLost, null, 'the cursor is cleared before the callback')
  assert.equal(handle.cursor(), null)
  assert.equal(script.calls.length, 1, 'revocation never reconnects')
  handle.openFreshStream('must-not-open')
  await new Promise<void>((resolve) => setTimeout(resolve, 10))
  assert.equal(script.calls.length, 1, 'openFreshStream is inert after revocation')
  assert.equal(recorded.execution.length, 1, 'no frame is delivered after the terminal revoke')
})

test('all control invalidation reasons reload authoritatively without a cursor skip or stale Last-Event-ID', async () => {
  const recorded = makeRecorded()
  const script = scriptedFetch([
    sseResponse(frame('execution', executionPayload(), 'cur-x') + frame('thread.changed', threadChangedPayload('replay_overflow'))),
    sseResponse(frame('thread.changed', threadChangedPayload('cursor_invalid'))),
  ])
  const handle = harness(recorded, { fetchImpl: script.impl })
  await new Promise<void>((resolve) => setTimeout(resolve, 20))

  assert.equal(handle.cursor(), 'cur-x', 'a control frame leaves the data cursor untouched')
  assert.equal(script.calls.length, 1, 'no automatic reopen; the authoritative reload must mint the fresh cursor')
  handle.openFreshStream('fresh-a')
  await new Promise<void>((resolve) => setTimeout(resolve, 20))
  assert.equal(script.calls[1]!.url, `${LIVE_URL}?after=fresh-a`)
  assert.equal(script.calls[1]!.headers['Last-Event-ID'], undefined)
  assert.deepEqual(recorded.thread.map((event) => event.reason), ['replay_overflow', 'cursor_invalid'])
  assert.equal(handle.cursor(), null, 'a fresh stream carries no stale cursor until its first ID frame')
  handle.stop()
  await handle.done
})

test('Last-Event-ID wins over a supplied after cursor, and a cold attach sends neither', async () => {
  const recorded = makeRecorded()
  const resume = scriptedFetch([openSseResponse(': heartbeat\n\n')])
  const resumeHandle = harness(recorded, { fetchImpl: resume.impl, lastEventId: 'resume-1', afterCursor: 'after-1' })
  await new Promise<void>((resolve) => setTimeout(resolve, 10))
  assert.equal(resume.calls[0]!.url, LIVE_URL, 'Last-Event-ID suppresses the after query')
  assert.equal(resume.calls[0]!.headers['Last-Event-ID'], 'resume-1')
  resumeHandle.stop()
  await resumeHandle.done

  const cold = scriptedFetch([openSseResponse(': heartbeat\n\n')])
  const coldHandle = harness(recorded, { fetchImpl: cold.impl })
  await new Promise<void>((resolve) => setTimeout(resolve, 10))
  assert.equal(cold.calls[0]!.url, LIVE_URL, 'a cold attach carries no position at all')
  assert.equal(cold.calls[0]!.headers['Last-Event-ID'], undefined)
  coldHandle.stop()
  await coldHandle.done
})

test('LF-only frames survive arbitrary byte boundaries, split multibyte characters, and repeated id lines', async () => {
  const recorded = makeRecorded()
  const payload = executionPayload()
  payload.event = { ...payload.event, payload: { text: '汉字🙂' } }
  const transcript = [
    'id: first\nid: second\nevent: execution\n',
    `data: ${JSON.stringify(payload)}\n\n`,
    ': heartbeat\n\n',
    frame('turn.completed', { session_id: SESSION, message_id: 'msg-1', run_id: 'run-1', status: 'completed', revision: 'rev-9' }, 'cur-fin'),
  ].join('')
  const script = scriptedFetch([sseResponse(transcript, 1), openSseResponse(': heartbeat\n\n')])
  const handle = harness(recorded, { fetchImpl: script.impl })
  await new Promise<void>((resolve) => setTimeout(resolve, 40))

  assert.equal(recorded.execution.length, 1)
  assert.equal(recorded.execution[0]!.event.payload.text, '汉字🙂', 'multibyte characters survive byte splits')
  assert.equal(recorded.turnCompleted.length, 1)
  assert.equal(handle.cursor(), 'cur-fin', 'the last id line within a frame wins')
  handle.stop()
  await handle.done
})

test('stop aborts the request and releases the reader without further retries', async () => {
  const recorded = makeRecorded()
  let cancelCalled = false
  const script = scriptedFetch([
    openSseResponse(frame('execution', executionPayload(), 'cur-c'), () => { cancelCalled = true }),
  ])
  const handle = harness(recorded, { fetchImpl: script.impl })
  await new Promise<void>((resolve) => setTimeout(resolve, 20))
  assert.equal(recorded.execution.length, 1)

  handle.stop()
  handle.stop()
  await handle.done
  assert.equal(cancelCalled, true, 'the reader is cancelled')
  assert.equal(script.calls[0]!.signal?.aborted, true, 'the AbortController is aborted')
  assert.equal(script.calls.length, 1, 'stopping suppresses the retry loop')
  handle.openFreshStream('nope')
  await new Promise<void>((resolve) => setTimeout(resolve, 10))
  assert.equal(script.calls.length, 1, 'a stopped handle never reopens')
})

test('four consecutive control-frame responses engage escalating backoff before the fourth immediate reopen', () => {
  noteSessionLiveData(PANE)
  const random = () => 0.5
  const delays = [1, 2, 3, 4, 5].map(() => noteSessionLiveControlFrame(PANE, random))
  assert.deepEqual(delays.slice(0, SESSION_LIVE_CONTROL_FRAME_CAP), [0, 0, 0], 'the first three control responses may reopen immediately')
  assert.deepEqual(delays.slice(SESSION_LIVE_CONTROL_FRAME_CAP), [1000, 2000], 'the fourth control response backs off 1s, then 2s')
  noteSessionLiveData(PANE)
  assert.equal(noteSessionLiveControlFrame(PANE, random), 0, 'forward progress resets the streak')
  noteSessionLiveData(PANE)
})

test('reconnect schedule is 1s, 2s, 4s, 8s, 15s capped with bounded jitter', () => {
  const attempts = [0, 1, 2, 3, 4, 5]
  assert.deepEqual(attempts.map((attempt) => sessionLiveReconnectDelayMs(attempt, () => 0.5)), [1000, 2000, 4000, 8000, 15_000, 15_000])
  assert.deepEqual([sessionLiveReconnectDelayMs(0, () => 0), sessionLiveReconnectDelayMs(0, () => 1)], [800, 1200])
})

test('network failures retry with backoff instead of failing the pane', async () => {
  const recorded = makeRecorded()
  const sleeps: number[] = []
  const script = scriptedFetch([new Error('offline'), openSseResponse(': heartbeat\n\n')])
  const handle = harness(recorded, {
    fetchImpl: script.impl,
    sleep: async (ms) => { sleeps.push(ms) },
  })
  await new Promise<void>((resolve) => setTimeout(resolve, 20))

  assert.equal(script.calls.length, 2, 'a network failure reconnects')
  assert.deepEqual(sleeps, [1000])
  assert.equal(recorded.errors.length, 0, 'a network failure is transient, not terminal')
  handle.stop()
  await handle.done
})

// ---------------------------------------------------------------------------
// T7: pane-lifecycle binding against the real store. Bundling axios into ESM
// needs a require shim, installed before the store's dynamic import; the live
// SSE endpoint uses global fetch while the authoritative GET is served by a
// custom axios adapter installed before module init.
// ---------------------------------------------------------------------------
;(globalThis as { require?: unknown }).require = createRequire(import.meta.url)

interface LiveCall {
  url: string
  headers: Record<string, string>
  signal: AbortSignal | null
  push: (text: string) => void
}

function liveHub() {
  const calls: LiveCall[] = []
  const impl = (async (input: unknown, init?: RequestInit) => {
    const url = String(input)
    if (!url.includes('/live')) return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
    let stream: ReadableStreamDefaultController<Uint8Array> | null = null
    const body = new ReadableStream<Uint8Array>({ start(controller) { stream = controller } })
    const headers: Record<string, string> = {}
    const raw = init?.headers as Record<string, string> | undefined
    if (raw) for (const [key, value] of Object.entries(raw)) headers[key] = String(value)
    calls.push({
      url,
      headers,
      signal: (init?.signal as AbortSignal) || null,
      push: (text) => { try { stream?.enqueue(encode(text)) } catch { stream = null } },
    })
    return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
  }) as typeof fetch
  return { impl, calls }
}

interface SessionApi {
  adapter: (config: { url?: string }) => Promise<unknown>
  gets: string[]
  cursorBySession: Map<string, string>
  holdNextGet: (sessionId: string) => void
  releaseGet: () => void
}

function createSessionApi(): SessionApi {
  const gets: string[] = []
  const cursorBySession = new Map<string, string>()
  let held: { sessionId: string; wait: Promise<void> } | null = null
  let releaseHeld: (() => void) | null = null
  const adapter = async (config: { url?: string }) => {
    const url = String(config.url || '')
    const sessionId = decodeURIComponent(url.split('/sessions/')[1]?.split('?')[0] || '')
    gets.push(sessionId)
    if (held && held.sessionId === sessionId) {
      const pending = held
      held = null
      await pending.wait
    }
    return {
      data: {
        data: {
          id: sessionId,
          title: `Session ${sessionId}`,
          messages: [],
          access: 'shared',
          owner_user_id: 'owner-1',
          participant_count: 2,
          live_cursor: cursorBySession.get(sessionId),
        },
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      request: null,
    }
  }
  return {
    adapter,
    gets,
    cursorBySession,
    holdNextGet(sessionId: string) {
      let release: () => void = () => undefined
      const wait = new Promise<void>((settle) => { release = settle })
      held = { sessionId, wait }
      releaseHeld = release
    },
    releaseGet() { releaseHeld?.() },
  }
}

let activeApi: SessionApi | null = null
const storeAdapter = async (config: { url?: string }): Promise<unknown> => {
  if (!activeApi) throw new Error('no session api armed for the store harness')
  return await activeApi.adapter(config)
}

async function loadStore(api: SessionApi) {
  activeApi = api
  const axios = (await import('axios')).default
  ;(axios.defaults as any).adapter = storeAdapter
  const { useChatRuntimeStore } = await import('../src/composables/useChatRuntimeStore')
  return useChatRuntimeStore({})
}

async function until(predicate: () => boolean, label: string, tries = 400): Promise<void> {
  for (let attempt = 0; attempt < tries; attempt += 1) {
    if (predicate()) return
    await new Promise<void>((settle) => setTimeout(settle, 1))
  }
  assert.fail(`timed out waiting for ${label}`)
}

async function settleTicks(count = 3): Promise<void> {
  for (let tick = 0; tick < count; tick += 1) await new Promise<void>((settle) => setTimeout(settle, 0))
}

test('T7 store: one stream per viewed pane, one snapshot refresh per invalidation, pane-switch cleanup', async () => {
  const live = liveHub()
  ;(globalThis as { fetch?: typeof fetch }).fetch = live.impl
  const api = createSessionApi()
  api.cursorBySession.set('sess-a', 'cursor-a-2')
  api.cursorBySession.set('sess-b', 'cursor-b-1')
  const runtime = await loadStore(api)
  runtime.reset()

  const paneA = await runtime.selectSession('sess-a', 'user-1', 'main-1', 'token-1')
  await until(() => live.calls.length === 1, 'first pane stream start')
  assert.match(live.calls[0].url, /\/sessions\/sess-a\/live/)
  assert.equal(live.calls[0].headers.Authorization, 'Bearer token-1')
  assert.equal(api.gets.filter((id) => id === 'sess-a').length, 1)
  assert.equal(runtime.membersRevisionFor('sess-a'), 0)

  live.calls[0].push(frame('members.changed', { session_id: 'sess-a', revision: 'rev-2' }))
  await until(() => runtime.membersRevisionFor('sess-a') === 1, 'members revision bump')
  await until(() => live.calls.length === 2, 'control-frame reopen')
  assert.equal(api.gets.filter((id) => id === 'sess-a').length, 2, 'exactly one authoritative snapshot per invalidation')
  assert.match(live.calls[1].url, /after=cursor-a-2/)
  await settleTicks()
  assert.equal(live.calls.length, 2, 'no refresh storm and no duplicate reopen')

  await runtime.selectSession('sess-b', 'user-1', 'main-1', 'token-1')
  await until(() => live.calls.length === 3, 'second pane stream start')
  assert.equal(live.calls[1].signal?.aborted, true, 'inactive pane aborts its in-flight stream')
  assert.match(live.calls[2].url, /\/sessions\/sess-b\/live/)

  const revisionA = runtime.membersRevisionFor('sess-a')
  live.calls[0].push(frame('members.changed', { session_id: 'sess-a', revision: 'rev-3' }))
  await settleTicks()
  assert.equal(runtime.membersRevisionFor('sess-a'), revisionA, 'stale stream callbacks are rejected')
  assert.equal(runtime.membersRevisionFor('sess-b'), 0, 'no cross-pane mutation')

  await runtime.selectSession('sess-a', 'user-1', 'main-1', 'token-1')
  await until(() => live.calls.length === 4, 're-viewed pane stream start')
  assert.equal(live.calls[2].signal?.aborted, true, 'the superseded pane aborted too')
  assert.ok(!live.calls[3].url.includes('after='), 'a re-viewed pane cold-attaches')
  assert.equal(runtime.activeChatPane.value?.key, paneA.key)

  runtime.removeSession('sess-a')
  runtime.removeSession('sess-b')
  runtime.reset()
})

test('T7 store: access-loss latch closes once; a refresh aborted by pane removal mutates nothing', async () => {
  const unhandled: unknown[] = []
  const capture = (reason: unknown) => { unhandled.push(reason) }
  process.on('unhandledRejection', capture)
  try {
    const live = liveHub()
    ;(globalThis as { fetch?: typeof fetch }).fetch = live.impl
    const api = createSessionApi()
    api.cursorBySession.set('sess-c', 'cursor-c-9')
    api.cursorBySession.set('sess-d', 'cursor-d-4')
    const runtime = await loadStore(api)
    runtime.reset()

    const paneC = await runtime.selectSession('sess-c', 'user-1', 'main-1', 'token-1')
    await until(() => live.calls.length === 1, 'pane C stream start')
    runtime.markAccessLost(paneC.key, 'participant_removed')
    assert.equal(paneC.accessLost, true)
    assert.equal(paneC.accessLostReason, 'participant_removed')
    assert.equal(paneC.liveStream, null)
    assert.equal(live.calls[0].signal?.aborted, true, 'the latch aborts the session stream')
    assert.doesNotThrow(() => runtime.markAccessLost(paneC.key, 'participant_left'))
    assert.equal(paneC.accessLostReason, 'participant_removed', 'the latch never flips after the first write')
    assert.equal(live.calls.length, 1, 'a second close never touches a dead handle')

    await runtime.selectSession('sess-d', 'user-1', 'main-1', 'token-1')
    await until(() => live.calls.length === 2, 'pane D stream start')
    api.holdNextGet('sess-d')
    live.calls[1].push(frame('thread.changed', { session_id: 'sess-d', revision: 'r2', last_message_seq: 4 }, 'evt-7'))
    await until(() => api.gets.filter((id) => id === 'sess-d').length === 2, 'refresh started')
    runtime.removeSession('sess-d')
    api.releaseGet()
    await settleTicks(6)
    assert.equal(live.calls.length, 2, 'no reopen after the pane was removed mid-refresh')

    live.calls[1].push(frame('members.changed', { session_id: 'sess-d', revision: 'r3' }))
    await settleTicks(3)
    assert.equal(runtime.membersRevisionFor('sess-d'), 0)
    assert.equal(live.calls.length, 2, 'no duplicate stream for a dead pane')
    assert.equal(unhandled.length, 0, 'no unhandled rejection from the aborted refresh')
  } finally {
    process.off('unhandledRejection', capture)
  }
})

test('T7 threading contract: single stream constructor, single latch writer, closed prop/watch edges', () => {
  const root = process.cwd()
  const store = readFileSync(resolve(root, 'src/composables/useChatRuntimeStore.ts'), 'utf8')
  const dialog = readFileSync(resolve(root, 'src/components/session/SessionShareDialog.vue'), 'utf8')
  const header = readFileSync(resolve(root, 'src/components/chat/ChatSessionHeader.vue'), 'utf8')
  const app = readFileSync(resolve(root, 'src/App.vue'), 'utf8')
  const sessions = readFileSync(resolve(root, 'src/api/sessions.ts'), 'utf8')

  assert.equal(store.match(/startSessionLiveStream\(\{/g)?.length, 1, 'T7 is the ONLY stream constructor')
  assert.match(store, /if \(!pane \|\| pane\.accessLost\) return/, 'the latch is idempotent per pane key')
  assert.match(store, /pane\.activeStream\?\.abort\(\)/, 'the latch aborts the local POST handle')
  assert.match(store, /pane\.authResumeController\?\.abort\(\)/, 'the latch aborts the recovery controller')
  assert.match(store, /noteSessionLiveControlFrame\(pane\.key\)/, 'control frames engage the T6 cap')
  assert.match(store, /detail\.live_cursor/, 'the reopen cursor comes from the authoritative GET')
  assert.match(store, /membersRevisionFor/, 'the store exposes the single-instance selector')
  assert.match(dialog, /membersRevision\?: number/, 'the dialog closed prop set is extended')
  assert.match(dialog, /props\.sessionId, props\.mode, props\.membersRevision/, 'the dialog watch key is extended')
  assert.match(header, /refreshToken\?: number/, 'the header gains the optional counter prop')
  assert.match(header, /watch\(\(\) => props\.refreshToken/, 'the header refetches its own detail on the counter')
  assert.match(app, /:refresh-token="chatRuntime\.membersRevisionFor\(currentSessionId\)"/, 'the single-instance call site threads the counter by session id')
  assert.match(sessions, /live_cursor\?: string/, 'SessionDetail closed shape is extended')
})
